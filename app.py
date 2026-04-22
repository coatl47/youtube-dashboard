"""
유튜브 실시간 여론 분석 대시보드
- 구조: config / data / ai / ui 레이어 분리
- 안정성: 세밀한 예외처리 및 입력 검증
- 성능: 모델 선택 캐싱, 분석 결과 캐싱
- UX: 단계별 진행 상황, 실패 시 구체적 안내
"""

import io
import re
import time
import hashlib
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# 0. 페이지 설정 (반드시 최상단에 위치)
# ============================================================
st.set_page_config(
    page_title="유튜브 여론 분석",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# 1. CONFIG 레이어
# ============================================================
class Config:
    """앱 전역 설정값을 한 곳에서 관리합니다."""

    # Gemini: 실제 존재하는 모델만, 할당량 넉넉한 순서로 정렬
    GEMINI_MODEL_PRIORITY = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]

    # 댓글 수집
    COMMENT_LIMIT = 50          # 분석할 최대 댓글 수
    COMMENT_MIN_LENGTH = 5      # 너무 짧은 댓글(이모지만 등) 제외

    # AI 재시도
    MAX_RETRIES = 3
    RETRY_BASE_WAIT = 15        # 초 (429 시 15 -> 30 -> 45초)

    # 감성 레이블 (AI가 이 값만 쓰도록 강제)
    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {"긍정": "#00CC96", "부정": "#EF553B", "중립": "#AB63FA"}


# ============================================================
# 2. DATA 레이어 — YouTube API
# ============================================================

@st.cache_resource
def _build_youtube_client():
    """YouTube 클라이언트를 한 번만 생성합니다."""
    return build("youtube", "v3", developerKey=st.secrets["YOUTUBE_API_KEY"])


def extract_video_id(url: str) -> str | None:
    """다양한 형태의 유튜브 URL에서 영상 ID를 추출합니다."""
    patterns = [
        r"(?:v=)([0-9A-Za-z_-]{11})",          # ?v=XXXXX
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",  # 단축 URL
        r"(?:embed\/)([0-9A-Za-z_-]{11})",       # 임베드 URL
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",      # Shorts URL
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_video_info(video_id: str) -> dict | None:
    """영상 기본 정보(제목, 조회수, 좋아요, 댓글 수)를 가져옵니다."""
    try:
        yt = _build_youtube_client()
        resp = yt.videos().list(part="snippet,statistics", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return None
        item = items[0]
        stats = item["statistics"]
        return {
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "published": item["snippet"]["publishedAt"][:10],
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
        }
    except HttpError as e:
        if e.resp.status == 403:
            st.error("❌ YouTube API 키가 유효하지 않거나 할당량이 초과되었습니다.")
        elif e.resp.status == 404:
            st.error("❌ 영상을 찾을 수 없습니다. URL을 확인하세요.")
        else:
            st.error(f"❌ YouTube API 오류 ({e.resp.status}): {e}")
        return None
    except Exception as e:
        st.error(f"❌ 예상치 못한 오류: {e}")
        return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(video_id: str, limit: int = Config.COMMENT_LIMIT) -> pd.DataFrame:
    """
    최신 댓글을 수집하고 전처리합니다.
    - HTML 태그 제거
    - 너무 짧은 댓글 필터링
    - 중복 댓글 제거
    """
    try:
        yt = _build_youtube_client()
        resp = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=min(limit * 2, 100),  # 중복/단문 필터 여유분 확보
            order="relevance",               # 인기 댓글 우선 (대표성 높음)
        ).execute()
    except HttpError as e:
        if e.resp.status == 403:
            st.warning("⚠️ 이 영상은 댓글이 비활성화되어 있습니다.")
        else:
            st.error(f"❌ 댓글 수집 오류 ({e.resp.status}): {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 댓글 수집 중 오류: {e}")
        return pd.DataFrame()

    rows = []
    seen_texts = set()

    for item in resp.get("items", []):
        snip = item["snippet"]["topLevelComment"]["snippet"]
        raw_text = snip.get("textDisplay", "")

        # 전처리
        clean = re.sub(r"<[^>]+>", "", raw_text)    # HTML 태그 제거
        clean = re.sub(r"https?://\S+", "", clean)   # URL 제거
        clean = clean.replace("\n", " ").strip()

        # 필터: 너무 짧거나 중복 제거
        if len(clean) < Config.COMMENT_MIN_LENGTH:
            continue
        if clean in seen_texts:
            continue
        seen_texts.add(clean)

        rows.append({
            "time": snip["publishedAt"],
            "text": clean,
            "likes": int(snip.get("likeCount", 0)),
        })

        if len(rows) >= limit:
            break

    if not rows:
        st.warning("⚠️ 수집된 유효 댓글이 없습니다.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df


# ============================================================
# 3. AI 레이어 — Gemini API
# ============================================================

@st.cache_resource(show_spinner=False)
def _get_gemini_model():
    """
    Gemini 모델을 앱 기동 시 한 번만 선택합니다 (cache_resource).
    매 분석마다 list_models()를 호출하던 비효율을 제거합니다.
    """
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        available = {m.name.replace("models/", "") for m in genai.list_models()}

        for target in Config.GEMINI_MODEL_PRIORITY:
            if target in available:
                return genai.GenerativeModel(target), target

        # fallback: 목록에서 flash 포함 모델 자동 탐색
        flash_candidates = sorted(
            [m for m in available if "flash" in m], reverse=True
        )
        if flash_candidates:
            return genai.GenerativeModel(flash_candidates[0]), flash_candidates[0]

    except Exception as e:
        st.error(f"❌ Gemini 초기화 오류: {e}")

    return None, None


def _build_prompt(comment_texts: list) -> str:
    """분석 프롬프트를 생성합니다. 감성 레이블을 명시적으로 고정합니다."""
    labels = ", ".join(Config.SENTIMENT_LABELS)
    sample = "\n".join([f"- {t[:120]}" for t in comment_texts])
    return f"""당신은 한국어 SNS 여론 분석 전문가입니다. 아래 유튜브 댓글들을 분석하세요.

[규칙]
1. 감성은 반드시 {labels} 중 하나만 사용하세요. 영어나 다른 값은 절대 사용하지 마세요.
2. 분류(주제)는 댓글 내용을 기반으로 최대 9개까지 생성하세요.
3. 키워드는 핵심 단어 1~3개를 쉼표로 구분하세요.
4. 내용은 댓글 원문을 30자 이내로 요약하세요.
5. 출력은 반드시 '|' 구분자 CSV 형식만 사용하고, 헤더와 데이터 외 다른 텍스트는 절대 쓰지 마세요.
6. 첫 줄은 반드시 정확히 이 헤더여야 합니다: 감성|분류|키워드|내용

[댓글]
{sample}"""


def _parse_ai_response(text: str) -> pd.DataFrame:
    """
    AI 응답을 파싱합니다.
    - 코드블록 제거
    - 헤더 위치 탐색 (앞뒤 여분 텍스트 제거)
    - 컬럼명 공백 정규화
    - 감성 값 강제 정규화 (영어 혼입 방지)
    """
    # 코드블록 마커 제거
    text = re.sub(r"```[a-z]*", "", text).replace("```", "").strip()

    # 헤더 탐색 (공백 무관)
    header_match = re.search(r"감성\s*\|\s*분류", text)
    if not header_match:
        return pd.DataFrame()

    csv_text = text[header_match.start():]

    try:
        df = pd.read_csv(
            io.StringIO(csv_text),
            sep="|",
            on_bad_lines="skip",
            engine="python",
            dtype=str,
        )
    except Exception:
        return pd.DataFrame()

    # 컬럼명 공백 정규화
    df.columns = [c.strip() for c in df.columns]

    required_cols = {"감성", "분류", "키워드", "내용"}
    if not required_cols.issubset(df.columns):
        return pd.DataFrame()

    df = df[list(required_cols)].copy()
    df = df.dropna(subset=["감성", "분류"])

    # 감성 값 정규화: 영어나 예상 외 값은 '중립'으로 교정
    valid = set(Config.SENTIMENT_LABELS)
    df["감성"] = df["감성"].str.strip()
    df.loc[~df["감성"].isin(valid), "감성"] = "중립"

    # 빈 내용 행 제거
    df = df[df["내용"].str.strip().str.len() > 0]

    return df.reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def analyze_comments(comment_hash: str, comment_texts: list) -> pd.DataFrame:
    """
    댓글을 AI로 분석합니다.
    - comment_hash: 동일 댓글 재분석 방지용 캐시 키 (실제 사용 인자)
    - 429 오류 시 지수 대기 재시도
    """
    model, model_name = _get_gemini_model()
    if model is None:
        st.error("❌ 사용 가능한 Gemini 모델이 없습니다.")
        return pd.DataFrame()

    prompt = _build_prompt(comment_texts)

    for attempt in range(Config.MAX_RETRIES):
        try:
            response = model.generate_content(prompt)
            result = _parse_ai_response(response.text)

            if not result.empty:
                return result

            st.warning(f"⚠️ AI 응답 파싱 실패 (시도 {attempt + 1}/{Config.MAX_RETRIES}). 재시도 중...")

        except Exception as e:
            err = str(e)
            is_quota_error = any(k in err for k in [
                "429", "quota", "Resource has been exhausted", "RESOURCE_EXHAUSTED"
            ])

            if is_quota_error:
                wait = Config.RETRY_BASE_WAIT * (attempt + 1)
                st.warning(
                    f"⚠️ Gemini API 할당량 초과. {wait}초 후 재시도합니다. "
                    f"({attempt + 1}/{Config.MAX_RETRIES})\n"
                    f"👉 사용량 확인: https://aistudio.google.com/"
                )
                time.sleep(wait)
            else:
                st.error(f"❌ AI 분석 오류: {e}")
                return pd.DataFrame()

    st.error(
        "❌ 분석에 최종 실패했습니다. 가능한 원인:\n"
        "- Gemini 무료 할당량 소진 (잠시 후 재시도)\n"
        "- API 키 오류 (Secrets 설정 확인)\n"
        "- 네트워크 문제"
    )
    return pd.DataFrame()


# ============================================================
# 4. UI 레이어
# ============================================================

def render_header():
    st.title("📊 유튜브 실시간 여론 분석")
    st.caption(
        "YouTube 댓글을 수집하고 Gemini Flash 모델로 감성 · 주제 분석을 수행합니다."
    )


def render_metrics(info: dict, analyzed_count: int):
    cols = st.columns(5)
    cols[0].metric("조회수", f"{info['view_count']:,}")
    cols[1].metric("좋아요", f"{info['like_count']:,}")
    cols[2].metric("전체 댓글", f"{info['comment_count']:,}")
    cols[3].metric("분석한 댓글", f"{analyzed_count}개")
    cols[4].metric("업데이트", datetime.now().strftime("%H:%M"))


def render_charts(raw_df: pd.DataFrame, result_df: pd.DataFrame):
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 시간대별 댓글 추이")
        if not raw_df.empty:
            trend = (
                raw_df.set_index("time")
                .resample("H")
                .size()
                .reset_index(name="댓글 수")
            )
            fig = px.line(
                trend, x="time", y="댓글 수",
                markers=True,
                labels={"time": "시간"},
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("댓글 데이터가 없습니다.")

    with col2:
        st.subheader("😊 감성 분석 비율")
        s_counts = (
            result_df["감성"]
            .value_counts()
            .rename_axis("감성")
            .reset_index(name="count")
        )
        fig = px.pie(
            s_counts,
            names="감성",
            values="count",
            color="감성",
            color_discrete_map=Config.SENTIMENT_COLORS,
            hole=0.35,
        )
        st.plotly_chart(fig, use_container_width=True)


def render_topic_chart(result_df: pd.DataFrame):
    st.subheader("📁 주제별 여론 분석")
    b_data = (
        result_df.groupby(["분류", "감성"])
        .size()
        .reset_index(name="댓글 수")
    )
    # 주제를 총 댓글 수 기준으로 내림차순 정렬
    order = (
        b_data.groupby("분류")["댓글 수"]
        .sum()
        .sort_values(ascending=True)
        .index.tolist()
    )
    fig = px.bar(
        b_data,
        x="댓글 수",
        y="분류",
        color="감성",
        orientation="h",
        color_discrete_map=Config.SENTIMENT_COLORS,
        category_orders={"분류": order},
    )
    fig.update_layout(legend_title_text="감성")
    st.plotly_chart(fig, use_container_width=True)


def render_data_table(result_df: pd.DataFrame, video_id: str):
    st.subheader("📋 분석 데이터")

    # 감성 필터 UI
    sentiments = ["전체"] + Config.SENTIMENT_LABELS
    selected = st.selectbox("감성 필터", sentiments)
    filtered = result_df if selected == "전체" else result_df[result_df["감성"] == selected]

    st.dataframe(filtered, use_container_width=True, height=400)

    st.download_button(
        label="⬇️ CSV 다운로드",
        data=filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"analysis_{video_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ============================================================
# 5. 메인 실행
# ============================================================

def main():
    render_header()

    url = st.text_input(
        "유튜브 URL을 입력하세요",
        placeholder="https://www.youtube.com/watch?v=...",
    )

    if not url:
        st.info("📌 분석할 유튜브 영상 URL을 입력하면 자동으로 분석을 시작합니다.")
        return

    # URL 유효성 검사
    video_id = extract_video_id(url)
    if not video_id:
        st.error(
            "❌ 유효하지 않은 유튜브 URL입니다.\n\n"
            "지원 형식:\n"
            "- https://www.youtube.com/watch?v=XXXXXXXXXXX\n"
            "- https://youtu.be/XXXXXXXXXXX\n"
            "- https://www.youtube.com/shorts/XXXXXXXXXXX"
        )
        return

    # 분석 실행
    with st.status("분석 중...", expanded=True) as status:
        st.write("📡 영상 정보 수집 중...")
        info = fetch_video_info(video_id)
        if not info:
            status.update(label="❌ 영상 정보 수집 실패", state="error")
            return

        st.write(f"✅ 영상: **{info['title']}**")
        st.write("💬 댓글 수집 중...")
        raw_df = fetch_comments(video_id)

        if raw_df.empty:
            status.update(label="❌ 댓글 수집 실패", state="error")
            return

        st.write(f"✅ {len(raw_df)}개 댓글 수집 완료")
        st.write("🤖 AI 분석 중...")

        # 동일 댓글 세트 재분석 방지: 댓글 내용으로 해시 생성
        comment_hash = hashlib.md5(
            "".join(raw_df["text"].tolist()).encode()
        ).hexdigest()
        result_df = analyze_comments(comment_hash, raw_df["text"].tolist())

        if result_df.empty:
            status.update(label="❌ AI 분석 실패", state="error")
            return

        status.update(label="✅ 분석 완료!", state="complete", expanded=False)

    # 결과 렌더링
    st.divider()
    st.subheader(f"🎬 {info['title']}")
    st.caption(f"채널: {info['channel']}  |  게시일: {info['published']}")

    render_metrics(info, len(result_df))
    st.divider()
    render_charts(raw_df, result_df)
    render_topic_chart(result_df)
    render_data_table(result_df, video_id)


if __name__ == "__main__":
    main()
