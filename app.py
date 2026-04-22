"""
유튜브 실시간 여론 분석 대시보드
- Gemini 무료 할당량 최적화 버전
  · list_models() API 호출 제거 → 모델 직접 fallback 시도
  · genai.configure() 모듈 레벨 1회 실행
  · 댓글 배치(20개) 분할 처리로 RPM·토큰 부담 분산
  · 분석 결과 24시간 캐싱으로 재분석 방지
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
# 0. 페이지 설정 (최상단 필수)
# ============================================================
st.set_page_config(
    page_title="유튜브 여론 분석",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# 1. CONFIG
# ============================================================
class Config:
    # ── Gemini ──────────────────────────────────────────────
    # list_models()를 쓰지 않고 직접 시도할 모델 순서
    # Flash 계열만 사용 (Pro 계열은 할당량 소진 빠름)
    GEMINI_MODEL_PRIORITY = [
        "gemini-2.0-flash",       # 1순위: 최신 Flash, 무료 할당량 가장 넉넉
        "gemini-1.5-flash",       # 2순위: 안정적인 Flash
        "gemini-1.5-flash-8b",    # 3순위: 경량 Flash (토큰 한도 낮지만 빠름)
    ]

    # ── 댓글 수집 ───────────────────────────────────────────
    COMMENT_LIMIT = 40            # 분석 댓글 수 (50→40으로 축소해 토큰 절약)
    COMMENT_MIN_LENGTH = 5        # 이 글자 수 미만 댓글 제외
    BATCH_SIZE = 20               # 배치당 댓글 수 (한 번에 너무 많으면 RPM 초과)

    # ── AI 재시도 ───────────────────────────────────────────
    MAX_RETRIES = 3
    RETRY_BASE_WAIT = 20          # 429 시 20→40→60초 대기

    # ── 감성 레이블 ─────────────────────────────────────────
    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {"긍정": "#00CC96", "부정": "#EF553B", "중립": "#AB63FA"}


# ============================================================
# 2. Gemini 초기화 (모듈 레벨 1회 실행)
# ============================================================
# genai.configure()를 함수 안에서 반복 호출하면
# 세션마다 인증 오버헤드가 발생하므로 최상위에서 1회만 실행합니다.
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as _cfg_err:
    st.error(f"❌ Gemini API 키 설정 오류: {_cfg_err}")


@st.cache_resource(show_spinner=False)
def _get_gemini_model():
    """
    list_models() API를 호출하지 않고,
    우선순위 모델을 순서대로 직접 인스턴스화해 동작하는 모델을 반환합니다.
    캐싱(cache_resource)으로 앱 기동 후 1회만 실행됩니다.
    """
    for model_name in Config.GEMINI_MODEL_PRIORITY:
        try:
            model = genai.GenerativeModel(model_name)
            # 빈 프롬프트로 실제 연결 가능 여부를 확인합니다
            model.generate_content("ping", generation_config={"max_output_tokens": 1})
            return model, model_name
        except Exception as e:
            err = str(e)
            # 모델이 존재하지 않는 경우 → 다음 후보로 넘어감
            if "not found" in err.lower() or "404" in err:
                continue
            # 할당량 초과인 경우 → 해당 모델은 쓸 수 없으므로 다음으로
            if "429" in err or "quota" in err.lower():
                continue
            # 그 외 오류 → 일단 다음으로
            continue

    return None, None


# ============================================================
# 3. YouTube DATA 레이어
# ============================================================

@st.cache_resource
def _build_youtube_client():
    return build("youtube", "v3", developerKey=st.secrets["YOUTUBE_API_KEY"])


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:embed\/)([0-9A-Za-z_-]{11})",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_video_info(video_id: str) -> dict | None:
    try:
        yt = _build_youtube_client()
        resp = yt.videos().list(part="snippet,statistics", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            st.error("❌ 영상을 찾을 수 없습니다. URL을 확인하세요.")
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
        code = e.resp.status
        if code == 403:
            st.error("❌ YouTube API 키 오류 또는 할당량 초과")
        elif code == 404:
            st.error("❌ 영상을 찾을 수 없습니다.")
        else:
            st.error(f"❌ YouTube API 오류 ({code}): {e}")
        return None
    except Exception as e:
        st.error(f"❌ 영상 정보 수집 오류: {e}")
        return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(video_id: str, limit: int = Config.COMMENT_LIMIT) -> pd.DataFrame:
    try:
        yt = _build_youtube_client()
        resp = yt.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=min(limit * 2, 100),
            order="relevance",
        ).execute()
    except HttpError as e:
        code = e.resp.status
        if code == 403:
            st.warning("⚠️ 댓글이 비활성화된 영상입니다.")
        else:
            st.error(f"❌ 댓글 수집 오류 ({code}): {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 댓글 수집 중 오류: {e}")
        return pd.DataFrame()

    rows, seen = [], set()
    for item in resp.get("items", []):
        snip = item["snippet"]["topLevelComment"]["snippet"]
        raw = snip.get("textDisplay", "")
        clean = re.sub(r"<[^>]+>", "", raw)
        clean = re.sub(r"https?://\S+", "", clean).replace("\n", " ").strip()
        if len(clean) < Config.COMMENT_MIN_LENGTH or clean in seen:
            continue
        seen.add(clean)
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
# 4. AI 레이어 — 배치 처리 + 할당량 보호
# ============================================================

def _build_prompt(comment_texts: list) -> str:
    """
    토큰을 최소화한 프롬프트.
    - 댓글을 120자로 절삭
    - 불필요한 설명 제거, 규칙만 명시
    """
    labels = "/".join(Config.SENTIMENT_LABELS)
    lines = "\n".join([f"{i+1}. {t[:120]}" for i, t in enumerate(comment_texts)])
    return (
        f"다음 댓글을 분석해 CSV로 출력하세요.\n"
        f"헤더: 감성|분류|키워드|내용\n"
        f"규칙: 감성={labels} 중 하나만. 다른 언어 금지. 설명 없이 CSV만 출력.\n\n"
        f"{lines}"
    )


def _parse_response(text: str) -> pd.DataFrame:
    text = re.sub(r"```[a-z]*", "", text).replace("```", "").strip()
    match = re.search(r"감성\s*\|\s*분류", text)
    if not match:
        return pd.DataFrame()
    try:
        df = pd.read_csv(
            io.StringIO(text[match.start():]),
            sep="|", on_bad_lines="skip",
            engine="python", dtype=str,
        )
    except Exception:
        return pd.DataFrame()

    df.columns = [c.strip() for c in df.columns]
    required = {"감성", "분류", "키워드", "내용"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df = df[list(required)].copy().dropna(subset=["감성", "분류"])
    df["감성"] = df["감성"].str.strip()
    valid = set(Config.SENTIMENT_LABELS)
    df.loc[~df["감성"].isin(valid), "감성"] = "중립"
    df = df[df["내용"].str.strip().str.len() > 0]
    return df.reset_index(drop=True)


def _call_gemini_with_retry(model, prompt: str) -> str | None:
    """
    단일 Gemini 호출 + 429 재시도.
    성공 시 응답 텍스트, 실패 시 None 반환.
    """
    for attempt in range(Config.MAX_RETRIES):
        try:
            resp = model.generate_content(prompt)
            return resp.text
        except Exception as e:
            err = str(e)
            is_quota = any(k in err for k in [
                "429", "quota", "RESOURCE_EXHAUSTED", "Resource has been exhausted"
            ])
            if is_quota:
                wait = Config.RETRY_BASE_WAIT * (attempt + 1)
                st.warning(
                    f"⚠️ Gemini 할당량 초과 — {wait}초 대기 후 재시도 "
                    f"({attempt + 1}/{Config.MAX_RETRIES})"
                )
                time.sleep(wait)
            else:
                st.error(f"❌ Gemini 호출 오류: {e}")
                return None
    return None


@st.cache_data(ttl=86400, show_spinner=False)  # 24시간 캐싱
def analyze_comments(comment_hash: str, comment_texts: list) -> pd.DataFrame:
    """
    댓글을 BATCH_SIZE 단위로 나눠 분석합니다.
    - 한 번에 보내는 토큰 수를 줄여 RPM·TPM 한도 보호
    - 배치 간 1초 대기로 분당 요청 수 조절
    - 24시간 캐싱으로 동일 영상 재분석 방지
    comment_hash는 캐시 키 역할만 하며 내부에서 직접 사용하지 않습니다.
    """
    model, model_name = _get_gemini_model()
    if model is None:
        st.error(
            "❌ 사용 가능한 Gemini 모델이 없습니다.\n"
            "가능한 원인:\n"
            "- 모든 Flash 모델의 무료 할당량 소진\n"
            "- GEMINI_API_KEY가 잘못됨\n"
            "👉 https://aistudio.google.com/ 에서 사용량 확인"
        )
        return pd.DataFrame()

    st.caption(f"🤖 사용 모델: `{model_name}`")

    batches = [
        comment_texts[i: i + Config.BATCH_SIZE]
        for i in range(0, len(comment_texts), Config.BATCH_SIZE)
    ]

    all_results = []
    for idx, batch in enumerate(batches):
        # 배치 진행 상황 표시
        st.caption(f"  📦 배치 {idx + 1}/{len(batches)} 분석 중... ({len(batch)}개 댓글)")

        prompt = _build_prompt(batch)
        raw_text = _call_gemini_with_retry(model, prompt)

        if raw_text is None:
            st.warning(f"⚠️ 배치 {idx + 1} 분석 실패, 건너뜀")
            continue

        parsed = _parse_response(raw_text)
        if not parsed.empty:
            all_results.append(parsed)

        # 배치 간 1초 대기: 분당 요청 수(RPM) 보호
        if idx < len(batches) - 1:
            time.sleep(1)

    if not all_results:
        st.error(
            "❌ 모든 배치 분석에 실패했습니다.\n"
            "- 무료 할당량 소진 시 1분 후 재시도하세요.\n"
            "- 유료 API 키 사용 시 할당량이 크게 늘어납니다."
        )
        return pd.DataFrame()

    return pd.concat(all_results, ignore_index=True)


# ============================================================
# 5. UI 레이어
# ============================================================

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
        trend = (
            raw_df.set_index("time").resample("H")
            .size().reset_index(name="댓글 수")
        )
        st.plotly_chart(
            px.line(trend, x="time", y="댓글 수", markers=True,
                    labels={"time": "시간"}),
            use_container_width=True,
        )

    with col2:
        st.subheader("😊 감성 분석 비율")
        s_counts = (
            result_df["감성"].value_counts()
            .rename_axis("감성").reset_index(name="count")
        )
        st.plotly_chart(
            px.pie(s_counts, names="감성", values="count",
                   color="감성", color_discrete_map=Config.SENTIMENT_COLORS,
                   hole=0.35),
            use_container_width=True,
        )


def render_topic_chart(result_df: pd.DataFrame):
    st.subheader("📁 주제별 여론 분석")
    b_data = result_df.groupby(["분류", "감성"]).size().reset_index(name="댓글 수")
    order = (
        b_data.groupby("분류")["댓글 수"]
        .sum().sort_values(ascending=True).index.tolist()
    )
    st.plotly_chart(
        px.bar(b_data, x="댓글 수", y="분류", color="감성", orientation="h",
               color_discrete_map=Config.SENTIMENT_COLORS,
               category_orders={"분류": order}),
        use_container_width=True,
    )


def render_data_table(result_df: pd.DataFrame, video_id: str):
    st.subheader("📋 분석 데이터")
    selected = st.selectbox("감성 필터", ["전체"] + Config.SENTIMENT_LABELS)
    filtered = result_df if selected == "전체" else result_df[result_df["감성"] == selected]
    st.dataframe(filtered, use_container_width=True, height=400)
    st.download_button(
        "⬇️ CSV 다운로드",
        filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"analysis_{video_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ============================================================
# 6. 메인
# ============================================================

def main():
    st.title("📊 유튜브 실시간 여론 분석")
    st.caption("YouTube 댓글을 수집하고 Gemini Flash 모델로 감성 · 주제 분석을 수행합니다.")

    url = st.text_input(
        "유튜브 URL을 입력하세요",
        placeholder="https://www.youtube.com/watch?v=...",
    )

    if not url:
        st.info("📌 분석할 유튜브 영상 URL을 입력하면 자동으로 분석을 시작합니다.")
        return

    video_id = extract_video_id(url)
    if not video_id:
        st.error(
            "❌ 유효하지 않은 유튜브 URL입니다.\n"
            "지원 형식: watch?v=... / youtu.be/... / shorts/..."
        )
        return

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
        st.write("🤖 AI 분석 중 (배치 처리)...")

        comment_hash = hashlib.md5(
            "".join(raw_df["text"].tolist()).encode()
        ).hexdigest()
        result_df = analyze_comments(comment_hash, raw_df["text"].tolist())

        if result_df.empty:
            status.update(label="❌ AI 분석 실패", state="error")
            return

        status.update(label="✅ 분석 완료!", state="complete", expanded=False)

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
