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
        "gemini-2.5-flash",       # 1순위: 안정적, Tier1 시 RPM 대폭 상승
        "gemini-2.5-flash-lite",  # 2순위: 무료 RPD 1,000 (단, 2026.06.01 종료 예정)
        "gemini-1.5-flash",       # 3순위: fallback용
    ]
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
# 2. Gemini 초기화
# ============================================================
# genai.configure()는 모듈 레벨에서 1회만 실행합니다.
# GenerativeModel 인스턴스화는 API 호출이 없으므로 할당량을 소비하지 않습니다.
# ping 테스트 호출은 완전히 제거합니다 — 모델 유효성은 실제 분석 시 검증합니다.
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as _cfg_err:
    st.error(f"❌ Gemini API 키 설정 오류: {_cfg_err}")


@st.cache_resource(show_spinner=False)
def _build_gemini_models() -> list:
    """
    API 호출 없이 모델 인스턴스만 생성해 우선순위 리스트로 반환합니다.
    GenerativeModel() 생성자는 네트워크 요청을 하지 않으므로 할당량 소비 없음.
    실제 할당량 소비는 generate_content() 호출 시에만 발생합니다.
    """
    models = []
    for name in Config.GEMINI_MODEL_PRIORITY:
        try:
            models.append((genai.GenerativeModel(name), name))
        except Exception:
            pass
    return models


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


def _is_quota_error(err: str) -> bool:
    return any(k in err for k in [
        "429", "quota", "RESOURCE_EXHAUSTED", "Resource has been exhausted",
        "rate limit", "RateLimitError",
    ])


def _is_model_not_found(err: str) -> bool:
    return any(k in err.lower() for k in ["not found", "404", "does not exist"])


def _call_with_model_fallback(prompt: str) -> tuple[str | None, str | None, str | None]:
    """
    모델 우선순위 리스트를 순회하며 호출합니다.
    반환: (응답텍스트 or None, 모델명 or None, 마지막오류 or None)

    ※ st.* 호출 없음 — cache_data 내부에서 호출되므로
      오류 정보를 반환값으로 전달해 호출부에서 표시합니다.
    """
    model_list = _build_gemini_models()
    if not model_list:
        return None, None, "GenerativeModel 인스턴스 생성 실패 — API 키를 확인하세요."

    last_error = ""
    for model, model_name in model_list:
        for attempt in range(Config.MAX_RETRIES):
            try:
                resp = model.generate_content(prompt)
                return resp.text, model_name, None   # ✅ 성공

            except Exception as e:
                err = str(e)
                last_error = f"[{model_name}] {err}"

                if _is_quota_error(err):
                    last_error = f"[{model_name}] 할당량 초과(429): {err}"
                    break   # 다음 모델로

                if _is_model_not_found(err):
                    last_error = f"[{model_name}] 모델 없음(404): {err}"
                    break   # 다음 모델로

                # 그 외: 재시도
                wait = Config.RETRY_BASE_WAIT * (attempt + 1)
                time.sleep(wait)

    return None, None, last_error


@st.cache_data(ttl=86400, show_spinner=False)
def _analyze_batch_cached(comment_hash: str, comment_texts: list) -> tuple[list, list]:
    """
    ※ cache_data 함수 안에서는 st.* 절대 호출 금지.
    반환: (성공한 CSV 텍스트 리스트, 오류 메시지 리스트)
    """
    batches = [
        comment_texts[i: i + Config.BATCH_SIZE]
        for i in range(0, len(comment_texts), Config.BATCH_SIZE)
    ]

    raw_results = []
    errors = []

    for idx, batch in enumerate(batches):
        prompt = _build_prompt(batch)
        raw_text, used_model, err_msg = _call_with_model_fallback(prompt)

        if raw_text is None:
            errors.append(f"배치 {idx + 1}: {err_msg}")
        else:
            raw_results.append((raw_text, used_model))
            time.sleep(1)   # RPM 보호

    return raw_results, errors


def analyze_comments(comment_hash: str, comment_texts: list) -> pd.DataFrame:
    """
    UI 출력(st.*)은 여기서 담당하고,
    실제 API 호출은 캐싱된 _analyze_batch_cached()에 위임합니다.
    """
    total_batches = (len(comment_texts) + Config.BATCH_SIZE - 1) // Config.BATCH_SIZE
    st.caption(f"🤖 총 {total_batches}개 배치로 분석합니다...")

    raw_results, errors = _analyze_batch_cached(comment_hash, comment_texts)

    # 오류가 있었으면 실제 오류 메시지를 화면에 표시
    if errors:
        with st.expander("⚠️ 일부 배치 오류 상세 (클릭해서 확인)", expanded=True):
            for e in errors:
                st.code(e)

            # 원인 분류해서 해결책 안내
            all_err_text = " ".join(errors)
            if _is_quota_error(all_err_text):
                st.warning(
                    "**원인: 할당량 초과**\n\n"
                    "유료 키인데도 발생한다면:\n"
                    "1. [aistudio.google.com/apikey](https://aistudio.google.com/apikey) 접속\n"
                    "2. 사용 중인 키 옆 **Plan** 컬럼이 `Paid`인지 확인\n"
                    "3. `Free`이면 → 결제 연결된 프로젝트에서 키를 새로 발급\n"
                    "4. Streamlit Cloud Secrets 값 교체 후 앱 **Reboot**"
                )
            elif "API_KEY_INVALID" in all_err_text or "401" in all_err_text:
                st.error(
                    "**원인: API 키 인증 실패**\n\n"
                    "secrets.toml 의 GEMINI_API_KEY 값이 잘못됐습니다.\n"
                    "AI Studio에서 키를 복사해 Streamlit Secrets에 다시 붙여넣고 Reboot 하세요."
                )
            elif "404" in all_err_text or "not found" in all_err_text.lower():
                st.error("**원인: 모델을 찾을 수 없음** — 모델명 또는 지역 문제")

    all_results = []
    for raw_text, used_model in raw_results:
        st.caption(f"  ✅ 완료 (모델: `{used_model}`)")
        parsed = _parse_response(raw_text)
        if not parsed.empty:
            all_results.append(parsed)

    if not all_results:
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
