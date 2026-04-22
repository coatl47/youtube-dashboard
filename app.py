"""
유튜브 실시간 여론 분석 대시보드
- google-genai (신규 공식 SDK) 사용
  · 구 SDK(google-generativeai)는 2025년 12월 이후 비활성 상태
  · 신규 SDK는 gemini-2.5-flash 등 최신 모델을 v1 API로 정상 호출
"""

import io
import re
import time
import hashlib
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from google import genai                        # ← 신규 SDK
from google.genai import errors as genai_errors # ← 신규 SDK 예외
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# 0. 페이지 설정
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
    # 신규 SDK에서 사용 가능한 모델 (v1 API 기준)
    GEMINI_MODEL_PRIORITY = [
        "gemini-2.5-flash",       # 1순위: 최신 안정 모델
        "gemini-2.5-flash-lite",  # 2순위: 경량 고처리량
        "gemini-2.0-flash",       # 3순위: 이전 세대 fallback
    ]

    COMMENT_LIMIT     = 40
    COMMENT_MIN_LEN   = 5
    BATCH_SIZE        = 20
    MAX_RETRIES       = 2
    RETRY_WAIT        = 15   # 일시 오류 재시도 대기(초)

    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {"긍정": "#00CC96", "부정": "#EF553B", "중립": "#AB63FA"}


# ============================================================
# 2. Gemini 클라이언트 (신규 SDK)
# ============================================================

@st.cache_resource(show_spinner=False)
def _gemini_client() -> genai.Client:
    """
    google-genai 신규 SDK 클라이언트를 앱 기동 시 1회 생성합니다.
    client.models.generate_content() 형태로 호출합니다.
    """
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


def _is_quota_error(err: str) -> bool:
    keywords = ["429", "RESOURCE_EXHAUSTED", "quota", "rate limit", "RateLimitError"]
    return any(k.lower() in err.lower() for k in keywords)


def _is_not_found_error(err: str) -> bool:
    return any(k in err.lower() for k in ["not found", "404", "does not exist", "unsupported"])


# ============================================================
# 3. YouTube 데이터 레이어
# ============================================================

@st.cache_resource
def _yt_client():
    return build("youtube", "v3", developerKey=st.secrets["YOUTUBE_API_KEY"])


def extract_video_id(url: str) -> str | None:
    for pat in [
        r"(?:v=)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:embed\/)([0-9A-Za-z_-]{11})",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_video_info(video_id: str) -> dict | None:
    try:
        resp = _yt_client().videos().list(
            part="snippet,statistics", id=video_id
        ).execute()
        items = resp.get("items", [])
        if not items:
            st.error("❌ 영상을 찾을 수 없습니다.")
            return None
        item  = items[0]
        stats = item["statistics"]
        return {
            "title":         item["snippet"]["title"],
            "channel":       item["snippet"]["channelTitle"],
            "published":     item["snippet"]["publishedAt"][:10],
            "view_count":    int(stats.get("viewCount",    0)),
            "like_count":    int(stats.get("likeCount",    0)),
            "comment_count": int(stats.get("commentCount", 0)),
        }
    except HttpError as e:
        msgs = {403: "API 키 오류 또는 할당량 초과", 404: "영상 없음"}
        st.error(f"❌ YouTube 오류: {msgs.get(e.resp.status, str(e))}")
    except Exception as e:
        st.error(f"❌ 영상 정보 수집 오류: {e}")
    return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(video_id: str, limit: int = Config.COMMENT_LIMIT) -> pd.DataFrame:
    try:
        resp = _yt_client().commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=min(limit * 2, 100),
            order="relevance",
        ).execute()
    except HttpError as e:
        st.error(f"❌ 댓글 수집 오류 ({e.resp.status}): {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 댓글 수집 중 오류: {e}")
        return pd.DataFrame()

    rows, seen = [], set()
    for item in resp.get("items", []):
        snip  = item["snippet"]["topLevelComment"]["snippet"]
        clean = re.sub(r"<[^>]+>", "", snip.get("textDisplay", ""))
        clean = re.sub(r"https?://\S+", "", clean).replace("\n", " ").strip()
        if len(clean) < Config.COMMENT_MIN_LEN or clean in seen:
            continue
        seen.add(clean)
        rows.append({
            "time":  snip["publishedAt"],
            "text":  clean,
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
# 4. AI 레이어
# ============================================================

def _build_prompt(texts: list) -> str:
    labels = "/".join(Config.SENTIMENT_LABELS)
    lines  = "\n".join(f"{i+1}. {t[:120]}" for i, t in enumerate(texts))
    return (
        f"다음 댓글을 분석해 CSV로 출력하세요.\n"
        f"헤더: 감성|분류|키워드|내용\n"
        f"규칙: 감성={labels} 중 하나만. 영어 금지. CSV만 출력.\n\n"
        f"{lines}"
    )


def _parse_response(text: str) -> pd.DataFrame:
    text  = re.sub(r"```[a-z]*", "", text).replace("```", "").strip()
    match = re.search(r"감성\s*\|\s*분류", text)
    if not match:
        return pd.DataFrame()
    try:
        df = pd.read_csv(
            io.StringIO(text[match.start():]),
            sep="|", on_bad_lines="skip", engine="python", dtype=str,
        )
    except Exception:
        return pd.DataFrame()

    df.columns = [c.strip() for c in df.columns]
    required   = {"감성", "분류", "키워드", "내용"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df = df[list(required)].copy().dropna(subset=["감성", "분류"])
    df["감성"] = df["감성"].str.strip()
    df.loc[~df["감성"].isin(set(Config.SENTIMENT_LABELS)), "감성"] = "중립"
    df = df[df["내용"].str.strip().str.len() > 0]
    return df.reset_index(drop=True)


def _call_api(prompt: str) -> tuple[str | None, str | None, str | None]:
    """
    신규 SDK(google-genai)로 모델을 순서대로 시도합니다.
    반환: (응답텍스트, 사용모델명, 오류메시지) — 성공 시 오류=None
    """
    client     = _gemini_client()
    last_error = "모든 모델 실패"

    for model_name in Config.GEMINI_MODEL_PRIORITY:
        for attempt in range(Config.MAX_RETRIES):
            try:
                resp = client.models.generate_content(
                    model    = model_name,
                    contents = prompt,
                )
                return resp.text, model_name, None  # ✅ 성공

            except Exception as e:
                err        = str(e)
                last_error = f"[{model_name}] {err}"

                if _is_quota_error(err):
                    last_error = f"[{model_name}] 할당량 초과: {err}"
                    break  # 다음 모델로

                if _is_not_found_error(err):
                    last_error = f"[{model_name}] 모델 없음: {err}"
                    break  # 다음 모델로

                # 일시적 오류 → 잠깐 대기 후 재시도
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_WAIT)

    return None, None, last_error


@st.cache_data(ttl=86400, show_spinner=False)
def _run_batches(comment_hash: str, comment_texts: list) -> tuple[list, list]:
    """
    캐시 함수 — st.* 호출 없음.
    반환: ([(raw_text, model_name), ...], [error_msg, ...])
    """
    batches = [
        comment_texts[i: i + Config.BATCH_SIZE]
        for i in range(0, len(comment_texts), Config.BATCH_SIZE)
    ]
    results, errors = [], []
    for idx, batch in enumerate(batches):
        raw, model, err = _call_api(_build_prompt(batch))
        if raw:
            results.append((raw, model))
            if idx < len(batches) - 1:
                time.sleep(1)
        else:
            errors.append(f"배치 {idx + 1}: {err}")
    return results, errors


def analyze_comments(comment_hash: str, comment_texts: list) -> pd.DataFrame:
    """UI 출력 담당 — 실제 API 호출은 _run_batches()에 위임."""
    n = (len(comment_texts) + Config.BATCH_SIZE - 1) // Config.BATCH_SIZE
    st.caption(f"🤖 {n}개 배치로 분석 중...")

    raw_results, errors = _run_batches(comment_hash, comment_texts)

    if errors:
        with st.expander("⚠️ 오류 상세 (클릭)", expanded=True):
            for e in errors:
                st.code(e)
            joined = " ".join(errors)
            if _is_quota_error(joined):
                st.warning(
                    "**할당량 초과** — 유료 키인데도 발생한다면:\n"
                    "1. [aistudio.google.com/apikey](https://aistudio.google.com/apikey) 에서 키 옆 Plan이 `Paid`인지 확인\n"
                    "2. `Free`면 → 결제 연결된 프로젝트에서 키를 새로 발급\n"
                    "3. Streamlit Cloud Secrets 교체 후 **Reboot**"
                )
            elif _is_not_found_error(joined):
                st.error(
                    "**모델 없음(404)** — `google-generativeai` 구 SDK 사용 중일 수 있습니다.\n"
                    "`requirements.txt`를 확인하고 아래 내용으로 교체한 뒤 재배포하세요."
                )
                st.code("google-genai\ngoogle-api-python-client\nstreamlit\npandas\nplotly", language="text")

    all_frames = []
    for raw, model in raw_results:
        st.caption(f"  ✅ 완료 (모델: `{model}`)")
        parsed = _parse_response(raw)
        if not parsed.empty:
            all_frames.append(parsed)

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()


# ============================================================
# 5. UI 레이어
# ============================================================

def render_metrics(info: dict, count: int):
    c = st.columns(5)
    c[0].metric("조회수",      f"{info['view_count']:,}")
    c[1].metric("좋아요",      f"{info['like_count']:,}")
    c[2].metric("전체 댓글",   f"{info['comment_count']:,}")
    c[3].metric("분석한 댓글", f"{count}개")
    c[4].metric("업데이트",    datetime.now().strftime("%H:%M"))


def render_charts(raw_df: pd.DataFrame, res_df: pd.DataFrame):
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 시간대별 댓글 추이")
        trend = raw_df.set_index("time").resample("H").size().reset_index(name="댓글 수")
        st.plotly_chart(
            px.line(trend, x="time", y="댓글 수", markers=True),
            use_container_width=True,
        )
    with c2:
        st.subheader("😊 감성 분석 비율")
        sc = res_df["감성"].value_counts().rename_axis("감성").reset_index(name="count")
        st.plotly_chart(
            px.pie(sc, names="감성", values="count", color="감성",
                   color_discrete_map=Config.SENTIMENT_COLORS, hole=0.35),
            use_container_width=True,
        )


def render_topic_chart(res_df: pd.DataFrame):
    st.subheader("📁 주제별 여론 분석")
    bd    = res_df.groupby(["분류", "감성"]).size().reset_index(name="댓글 수")
    order = bd.groupby("분류")["댓글 수"].sum().sort_values().index.tolist()
    st.plotly_chart(
        px.bar(bd, x="댓글 수", y="분류", color="감성", orientation="h",
               color_discrete_map=Config.SENTIMENT_COLORS,
               category_orders={"분류": order}),
        use_container_width=True,
    )


def render_table(res_df: pd.DataFrame, video_id: str):
    st.subheader("📋 분석 데이터")
    sel      = st.selectbox("감성 필터", ["전체"] + Config.SENTIMENT_LABELS)
    filtered = res_df if sel == "전체" else res_df[res_df["감성"] == sel]
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
    st.caption("Gemini 신규 SDK(google-genai)로 댓글 감성·주제를 분석합니다.")

    url = st.text_input("유튜브 URL 입력", placeholder="https://www.youtube.com/watch?v=...")
    if not url:
        st.info("📌 분석할 유튜브 영상 URL을 입력하세요.")
        return

    video_id = extract_video_id(url)
    if not video_id:
        st.error("❌ 유효하지 않은 URL입니다. (watch?v= / youtu.be / shorts 형식 지원)")
        return

    with st.status("분석 중...", expanded=True) as status:
        st.write("📡 영상 정보 수집 중...")
        info = fetch_video_info(video_id)
        if not info:
            status.update(label="❌ 영상 정보 수집 실패", state="error"); return

        st.write(f"✅ **{info['title']}**")
        st.write("💬 댓글 수집 중...")
        raw_df = fetch_comments(video_id)
        if raw_df.empty:
            status.update(label="❌ 댓글 수집 실패", state="error"); return

        st.write(f"✅ {len(raw_df)}개 댓글 수집 완료")
        st.write("🤖 AI 분석 중...")

        h      = hashlib.md5("".join(raw_df["text"].tolist()).encode()).hexdigest()
        res_df = analyze_comments(h, raw_df["text"].tolist())
        if res_df.empty:
            status.update(label="❌ AI 분석 실패", state="error"); return

        status.update(label="✅ 분석 완료!", state="complete", expanded=False)

    st.divider()
    st.subheader(f"🎬 {info['title']}")
    st.caption(f"채널: {info['channel']}  |  게시일: {info['published']}")
    render_metrics(info, len(res_df))
    st.divider()
    render_charts(raw_df, res_df)
    render_topic_chart(res_df)
    render_table(res_df, video_id)


if __name__ == "__main__":
    main()
