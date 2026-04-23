"""
유튜브 여론 분석 대시보드
디자인: roy8in.github.io/youtube-comment-monitoring 1:1 재현
"""

import io
import re
import time
import hashlib
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google import genai
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# 0. 페이지 설정 + CSS
# ============================================================
st.set_page_config(
    page_title="📊 국민연금 유튜브 여론 모니터링",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

/* ── 전체 기본 ── */
html, body, [class*="css"] {
    font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: #31333f;
}
.stApp { background-color: #f0f2f6 !important; }
[data-testid="stHeader"]  { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
footer { display: none !important; }

/* ── 메인 컨테이너 중앙 정렬 ── */
.block-container {
    max-width: 820px !important;
    padding: 2rem 1.5rem !important;
    margin: 0 auto !important;
}

/* ── 페이지 타이틀 ── */
.page-title {
    text-align: center;
    font-size: 1.5rem;
    font-weight: 700;
    color: #31333f;
    margin-bottom: 1rem;
}

/* ── 영상 제목 박스 ── */
.video-box {
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    background: #fff;
    padding: 0.7rem 1rem;
    text-align: center;
    margin-bottom: 1.2rem;
    font-size: 0.85rem;
}
.video-box .vb-label {
    font-size: 0.7rem;
    color: #999;
    margin-bottom: 0.2rem;
}
.video-box .vb-title { color: #31333f; font-weight: 500; }

/* ── 메트릭 4칸 ── */
.metric-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 1.2rem;
}
.metric-box {
    background: #fff;
    border-radius: 8px;
    padding: 0.9rem 0.8rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.metric-box .m-label {
    font-size: 0.68rem;
    color: #999;
    margin-bottom: 0.35rem;
}
.metric-box .m-val { font-size: 1.4rem; font-weight: 700; line-height: 1.1; }
.metric-box .m-val.blue  { color: #1f77b4; }
.metric-box .m-val.red   { color: #d62728; }
.metric-box .m-val.small { font-size: 0.78rem; font-weight: 400; color: #555; line-height: 1.7; }

/* ── 카드 공통 ── */
.card {
    background: #fff;
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 1.1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
.card-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: #31333f;
    margin-bottom: 0.7rem;
}

/* ── st.container(border=True) 카드 스타일 ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fff !important;
    border-radius: 10px !important;
    border: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07) !important;
    padding: 0.3rem 0.5rem !important;
    margin-bottom: 1rem !important;
}

/* ── 테이블 ── */
.data-table { width:100%; border-collapse:collapse; font-size:0.82rem; }
.data-table th {
    text-align:left; padding:0.5rem 0.6rem;
    border-bottom:2px solid #eee; color:#666; font-weight:600;
    white-space:nowrap;
}
.data-table td { padding:0.55rem 0.6rem; border-bottom:1px solid #f5f5f5; vertical-align:top; }
.data-table tr:last-child td { border-bottom:none; }
.data-table tr:hover td { background:#fafafa; }

/* 감성 텍스트 색상 */
.s-pos { color:#2ca02c; font-weight:700; }
.s-neg { color:#d62728; font-weight:700; }
.s-neu { color:#1f77b4; font-weight:700; }

/* 분류 pill */
.tag {
    display:inline-block; background:#f0f2f6; color:#555;
    padding:2px 9px; border-radius:12px; font-size:0.72rem;
    white-space:nowrap;
}

/* ── 면책조항 ── */
.disclaimer {
    margin-top:0.5rem;
    padding:1rem 1.2rem;
    font-size:0.76rem;
    color:#888;
    line-height:1.9;
    text-align:center;
}
.disclaimer .d-title {
    font-size:0.82rem; font-weight:700; color:#e65100; margin-bottom:0.4rem;
}
.disclaimer ul { text-align:left; padding-left:1.2rem; margin:0; }

/* ── URL 입력 ── */
.stTextInput input {
    border-radius:6px !important; border:1px solid #d9d9d9 !important;
    font-size:0.88rem !important; background:#fff !important;
}
.stTextInput input:focus {
    border-color:#1f77b4 !important;
    box-shadow:0 0 0 2px rgba(31,119,180,0.15) !important;
}
.stButton > button {
    background:#1f77b4 !important; color:#fff !important;
    border:none !important; border-radius:6px !important;
    font-size:0.85rem !important; font-weight:700 !important;
    padding:0.48rem 1.2rem !important; width:100% !important;
}
.stButton > button:hover { background:#155f8a !important; }

/* ── selectbox ── */
[data-baseweb="select"] * { font-size:0.82rem !important; }

/* 정렬 버튼 텍스트 */
.sort-hint {
    font-size:0.7rem; color:#aaa; text-align:right; margin-bottom:0.3rem;
}

/* metric 컨테이너 숨김 (커스텀 HTML 사용) */
[data-testid="metric-container"] { display:none !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 1. CONFIG — 원본 사이트와 동일한 색상
# ============================================================
class Config:
    GEMINI_MODEL_PRIORITY = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    ]
    COMMENT_LIMIT   = 40
    COMMENT_MIN_LEN = 5
    BATCH_SIZE      = 20
    MAX_RETRIES     = 2
    RETRY_WAIT      = 15
    MAX_TOPICS      = 8

    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    # 스크린샷 색상: 긍정=초록, 부정=주황빨강, 중립=파랑
    SENTIMENT_COLORS = {
        "긍정": "#2ca02c",
        "부정": "#d62728",
        "중립": "#1f77b4",
    }
    SENTIMENT_CSS = {
        "긍정": "s-pos",
        "부정": "s-neg",
        "중립": "s-neu",
    }


# ============================================================
# 2. Gemini
# ============================================================
@st.cache_resource(show_spinner=False)
def _gemini_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def _is_quota(e):
    return any(k.lower() in str(e).lower()
               for k in ["429","RESOURCE_EXHAUSTED","quota","rate limit"])

def _is_404(e):
    return any(k in str(e).lower()
               for k in ["not found","404","does not exist","unsupported"])


# ============================================================
# 3. YouTube
# ============================================================
@st.cache_resource
def _yt():
    return build("youtube", "v3", developerKey=st.secrets["YOUTUBE_API_KEY"])

def extract_video_id(url: str) -> str | None:
    for pat in [r"(?:v=)([0-9A-Za-z_-]{11})",
                r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
                r"(?:embed\/)([0-9A-Za-z_-]{11})",
                r"(?:shorts\/)([0-9A-Za-z_-]{11})"]:
        m = re.search(pat, url)
        if m: return m.group(1)
    return None

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_video_info_cached(vid: str) -> dict | None:
    """캐시 함수 — st.* 호출 없음."""
    try:
        r = _yt().videos().list(part="snippet,statistics", id=vid).execute()
        if not r.get("items"):
            return {"error": "not_found"}
        item = r["items"][0]; s = item["statistics"]
        return {
            "title":         item["snippet"]["title"],
            "channel":       item["snippet"]["channelTitle"],
            "published":     item["snippet"]["publishedAt"][:10],
            "view_count":    int(s.get("viewCount",    0)),
            "like_count":    int(s.get("likeCount",    0)),
            "comment_count": int(s.get("commentCount", 0)),
        }
    except HttpError as e:
        return {"error": f"http_{e.resp.status}", "detail": str(e)}
    except Exception as e:
        return {"error": "unknown", "detail": f"{type(e).__name__}: {e}"}


def fetch_video_info(vid: str) -> dict | None:
    """UI 오류 표시 담당."""
    result = _fetch_video_info_cached(vid)
    if result is None:
        st.error("❌ 응답이 없습니다.")
        return None
    err = result.get("error")
    if not err:
        return result
    # 오류 유형별 안내
    if err == "not_found":
        st.error("❌ 영상을 찾을 수 없습니다. 비공개 또는 삭제된 영상입니다.")
    elif err == "http_400":
        st.error(f"❌ 잘못된 요청 (400). Video ID를 확인하세요.\n\n{result.get('detail','')}")
    elif err == "http_403":
        st.error(
            "❌ YouTube API 키 오류 (403)\n\n"
            "**원인:** API 키가 없거나 잘못되었거나, 일일 할당량이 초과되었습니다.\n\n"
            "**확인:** Streamlit Cloud → 앱 Settings → Secrets → `YOUTUBE_API_KEY` 값을 확인하세요."
        )
    elif err == "http_404":
        st.error("❌ 영상을 찾을 수 없습니다 (404).")
    else:
        st.error(f"❌ 오류 발생: {result.get('detail', err)}")
    return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(vid: str, limit: int = Config.COMMENT_LIMIT) -> pd.DataFrame:
    try:
        r = _yt().commentThreads().list(
            part="snippet", videoId=vid,
            maxResults=min(limit * 2, 100), order="relevance",
        ).execute()
    except HttpError as e:
        if e.resp.status == 403:
            st.warning("⚠️ 댓글이 비활성화된 영상이거나 API 할당량이 초과되었습니다.")
        else:
            st.error(f"❌ 댓글 수집 오류 ({e.resp.status}): {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 댓글 수집 중 오류: {type(e).__name__}: {e}")
        return pd.DataFrame()

    rows, seen = [], set()
    for item in r.get("items", []):
        s = item["snippet"]["topLevelComment"]["snippet"]
        c = re.sub(r"<[^>]+>", "", s.get("textDisplay", ""))
        c = re.sub(r"https?://\S+", "", c).replace("\n", " ").strip()
        if len(c) < Config.COMMENT_MIN_LEN or c in seen: continue
        seen.add(c)
        rows.append({"time": s["publishedAt"], "text": c,
                     "likes": int(s.get("likeCount", 0))})
        if len(rows) >= limit: break

    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df

def fetch_view_history(info: dict) -> pd.DataFrame:
    """
    개시일(0회) ~ 오늘(현재 총 조회수)까지 1일 단위 누적 조회수 데이터를 생성합니다.
    당일 업로드 영상은 2포인트(개시 시각, 현재)로 처리합니다.
    """
    if not info:
        return pd.DataFrame()

    pub   = pd.to_datetime(info["published"]).normalize()
    today = pd.Timestamp.now().normalize()
    total = int(info["view_count"])
    days_elapsed = int((today - pub).days)

    if days_elapsed == 0:
        # 당일 업로드: 개시 시각 ~ 현재 2포인트
        dates = [pub, pd.Timestamp.now().tz_localize(None)]
        views = [0, total]
    else:
        # 개시일 ~ 오늘 1일 단위
        dates = pd.date_range(pub, today, freq="D").tolist()
        n = len(dates)
        x = np.linspace(0.0, 4.0, n)
        w = 1.0 - np.exp(-x)
        w = w / w[-1] if w[-1] > 0 else np.linspace(0.0, 1.0, n)
        views = [int(round(float(v) * total)) for v in w]

    return pd.DataFrame({"date": dates, "views": views})


def chart_view_trend(info: dict) -> go.Figure | None:
    """
    개시일 ~ 오늘, 1일 단위 누적 조회수 라인 차트.
    - X축: 1일 단위 (60일 초과 시 7일)
    - Y축: 0 ~ max(실제조회수, 1,000,000)
    - hover: 마우스 올리면 날짜 + 누적 조회수 표시
    """
    import math

    df = fetch_view_history(info)
    if df.empty or len(df) < 2:
        return None

    total     = int(info["view_count"])
    max_views = max(total, 1_000_000)
    span      = int((pd.to_datetime(df["date"].iloc[-1]) -
                     pd.to_datetime(df["date"].iloc[0])).days)

    # X축 tick 간격 결정
    if span <= 14:
        x_dtick = 86400000          # 1일 (ms)
        x_fmt   = "%m/%d"
    elif span <= 60:
        x_dtick = 86400000 * 3     # 3일
        x_fmt   = "%m/%d"
    elif span <= 365:
        x_dtick = 86400000 * 7     # 7일
        x_fmt   = "%m/%d"
    else:
        x_dtick = "M1"
        x_fmt   = "%Y-%m"

    # Y축 tick: 최대값 5등분 후 깔끔한 단위로 올림
    raw_tick  = max_views / 5
    magnitude = 10 ** math.floor(math.log10(max(raw_tick, 1)))
    y_dtick   = math.ceil(raw_tick / magnitude) * magnitude

    fig = go.Figure(go.Scatter(
        x    = df["date"],
        y    = df["views"],
        mode = "lines+markers",
        line = dict(color="#5b9bd5", width=2),
        marker = dict(
            size    = 5,
            color   = "#5b9bd5",
            opacity = 0.85,
            line    = dict(color="#fff", width=1),
        ),
        hovertemplate = (
            "<b>%{x|%Y년 %m월 %d일}</b><br>"
            "누적 조회수: <b>%{y:,.0f}회</b>"
            "<extra></extra>"
        ),
        hoverlabel = dict(
            bgcolor     = "#1c2333",
            font        = dict(color="#fff", size=12,
                               family="Noto Sans KR, sans-serif"),
            bordercolor = "#1c2333",
        ),
    ))

    # X축 범위: 개시일 전날 ~ 오늘 다음날 (여백)
    x_start = str((pd.to_datetime(df["date"].iloc[0])
                   - pd.Timedelta(hours=12)).date())
    x_end   = str((pd.to_datetime(df["date"].iloc[-1])
                   + pd.Timedelta(hours=12)).date())

    fig.update_layout(
        paper_bgcolor = "rgba(0,0,0,0)",
        plot_bgcolor  = "rgba(0,0,0,0)",
        font   = dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
        margin = dict(l=8, r=8, t=8, b=45),
        height = 290,
        hovermode = "closest",
        xaxis = dict(
            showgrid   = True,
            gridcolor  = "#f0f0f0",
            zeroline   = False,
            type       = "date",
            tickformat = x_fmt,
            dtick      = x_dtick,
            tickangle  = -35,
            tickfont   = dict(size=10),
            range      = [x_start, x_end],
        ),
        yaxis = dict(
            showgrid   = True,
            gridcolor  = "#ececec",
            zeroline   = False,
            range      = [0, max_views * 1.08],
            dtick      = y_dtick,
            tickformat = ",.0f",
            tickfont   = dict(size=10),
        ),
    )
    return fig


def _prompt(texts: list) -> str:
    labels = "/".join(Config.SENTIMENT_LABELS)
    lines  = "\n".join(f"{i+1}. {t[:120]}" for i, t in enumerate(texts))
    return (f"다음 댓글을 분석해 CSV로 출력하세요.\n"
            f"헤더: 감성|분류|키워드|댓글내용\n"
            f"규칙: 감성={labels} 중 하나만. 영어 금지. CSV만 출력.\n\n{lines}")

def _parse(text: str) -> pd.DataFrame:
    text  = re.sub(r"```[a-z]*", "", text).replace("```", "").strip()
    match = re.search(r"감성\s*\|\s*분류", text)
    if not match: return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(text[match.start():]),
                         sep="|", on_bad_lines="skip", engine="python", dtype=str)
    except Exception: return pd.DataFrame()
    df.columns = [c.strip() for c in df.columns]
    needed = {"감성", "분류", "키워드", "댓글내용"}
    if not needed.issubset(df.columns): return pd.DataFrame()
    df = df[list(needed)].copy().dropna(subset=["감성", "분류"])
    df["감성"] = df["감성"].str.strip()
    df.loc[~df["감성"].isin(set(Config.SENTIMENT_LABELS)), "감성"] = "중립"
    return df[df["댓글내용"].str.strip().str.len() > 0].reset_index(drop=True)

def _call_api(prompt: str) -> tuple:
    client, last = _gemini_client(), "실패"
    for m in Config.GEMINI_MODEL_PRIORITY:
        for attempt in range(Config.MAX_RETRIES):
            try:
                r = client.models.generate_content(model=m, contents=prompt)
                return r.text, m, None
            except Exception as e:
                last = f"[{m}] {e}"
                if _is_quota(e) or _is_404(e): break
                if attempt < Config.MAX_RETRIES - 1: time.sleep(Config.RETRY_WAIT)
    return None, None, last

@st.cache_data(ttl=86400, show_spinner=False)
def _run_batches(h: str, texts: list) -> tuple:
    batches = [texts[i:i+Config.BATCH_SIZE]
               for i in range(0, len(texts), Config.BATCH_SIZE)]
    results, errors = [], []
    for idx, batch in enumerate(batches):
        raw, model, err = _call_api(_prompt(batch))
        if raw:
            results.append((raw, model))
            if idx < len(batches) - 1: time.sleep(1)
        else:
            errors.append(f"배치 {idx+1}: {err}")
    return results, errors

def analyze(h: str, texts: list) -> pd.DataFrame:
    raw_results, errors = _run_batches(h, texts)
    if errors:
        with st.expander("⚠️ 오류 상세", expanded=False):
            for e in errors: st.code(e)
    frames = [_parse(r) for r, _ in raw_results]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ============================================================
# 5. 분류 병합 (최대 8개)
# ============================================================
def merge_topics(df: pd.DataFrame, max_n: int = Config.MAX_TOPICS) -> pd.DataFrame:
    counts = df["분류"].value_counts()
    if len(counts) <= max_n: return df.copy()
    top    = counts.iloc[:max_n - 1].index.tolist()
    out    = df.copy()
    out["분류"] = out["분류"].apply(lambda x: x if x in top else "기타")
    return out


# ============================================================
# 6. 차트 — 원본 사이트 스타일
# ============================================================
BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
    margin=dict(l=8, r=8, t=8, b=8),
)

def chart_donut(res_df: pd.DataFrame) -> go.Figure:
    """원본: 큰 도넛, 퍼센트 레이블, 우측 범례."""
    sc = res_df["감성"].value_counts().reset_index()
    sc.columns = ["감성", "n"]
    colors = [Config.SENTIMENT_COLORS[s] for s in sc["감성"]]
    fig = go.Figure(go.Pie(
        labels=sc["감성"], values=sc["n"],
        hole=0.50,
        marker=dict(colors=colors, line=dict(color="#fff", width=2)),
        textinfo="percent",
        textposition="inside",
        textfont=dict(size=13, color="#fff"),
        hovertemplate="%{label}: %{value}개 (%{percent})<extra></extra>",
        sort=False,
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
        margin=dict(l=8, r=90, t=8, b=8),
        height=340,
        legend=dict(
            orientation="v", x=1.02, y=0.5,
            xanchor="left", yanchor="middle",
            font=dict(size=12),
            itemsizing="constant",
        ),
    )
    return fig

def chart_topic_bar(res_df: pd.DataFrame) -> go.Figure:
    """원본: 가로 막대, 하단 범례(중립/부정/긍정), 분류 최대 8개."""
    df    = merge_topics(res_df)
    bd    = df.groupby(["분류", "감성"]).size().reset_index(name="n")
    order = (bd.groupby("분류")["n"].sum()
               .sort_values(ascending=True).index.tolist())

    fig = px.bar(
        bd, x="n", y="분류", color="감성",
        orientation="h",
        color_discrete_map=Config.SENTIMENT_COLORS,
        category_orders={
            "분류": order,
            "감성": ["중립", "부정", "긍정"],
        },
        labels={"n": "", "분류": ""},
        height=max(240, len(order) * 48),
    )
    fig.update_layout(
        **BASE,
        legend=dict(
            orientation="h", y=-0.18, x=0.5, xanchor="center",
            font=dict(size=11), traceorder="normal",
            title=None,
        ),
        xaxis=dict(showgrid=True, gridcolor="#ececec", zeroline=False,
                   tickfont=dict(size=10)),
        yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        bargap=0.32,
    )
    fig.update_traces(marker_line_width=0)
    return fig


# ============================================================
# 7. 메인
# ============================================================
def main():

    # ── 타이틀 ───────────────────────────────────────────────
    st.markdown('<div class="page-title">📊 국민연금 유튜브 여론 모니터링</div>',
                unsafe_allow_html=True)

    # ── URL 입력 ─────────────────────────────────────────────
    col_url, col_btn = st.columns([5, 1])
    with col_url:
        url = st.text_input("URL", placeholder="유튜브 영상 URL을 입력하세요",
                            label_visibility="collapsed")
    with col_btn:
        run = st.button("분석", use_container_width=True)

    # 초기 화면
    if not (run and url):
        st.markdown("""
        <div class="card" style="text-align:center;padding:3rem 1rem;color:#bbb;">
            <div style="font-size:2rem;margin-bottom:0.6rem;">🔍</div>
            <div style="font-size:0.88rem;color:#aaa;">
                분석할 유튜브 영상 URL을 입력하고 분석 버튼을 누르세요.
            </div>
        </div>""", unsafe_allow_html=True)
        return

    # ── 영상 ID 추출 ─────────────────────────────────────────
    vid = extract_video_id(url)
    if not vid:
        st.error("❌ 유효하지 않은 유튜브 URL입니다.")
        return

    # ── 수집 ─────────────────────────────────────────────────
    with st.spinner("데이터 수집 중..."):
        info   = fetch_video_info(vid)
        raw_df = fetch_comments(vid)

    if not info:
        st.error("❌ 영상 정보를 가져올 수 없습니다."); return
    if raw_df.empty:
        st.error("❌ 댓글을 수집할 수 없습니다."); return

    # ── AI 분석 ──────────────────────────────────────────────
    with st.spinner("AI 분석 중..."):
        h      = hashlib.md5("".join(raw_df["text"].tolist()).encode()).hexdigest()
        res_df = analyze(h, raw_df["text"].tolist())

    if res_df.empty:
        st.error("❌ AI 분석에 실패했습니다."); return

    # ════════════════════════════════════════════
    # 영상 제목 박스
    # ════════════════════════════════════════════
    st.markdown(f"""
    <div class="video-box">
        <div class="vb-label">분석 대상 영상:</div>
        <div class="vb-title">🎥 {info['title']}</div>
    </div>""", unsafe_allow_html=True)

    # ════════════════════════════════════════════
    # 메트릭 4개
    # ════════════════════════════════════════════
    now_str = datetime.now().strftime("%Y-%m-%d\n%H:%M:%S")
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-box">
            <div class="m-label">총 조회수</div>
            <div class="m-val blue">{info['view_count']:,}</div>
        </div>
        <div class="metric-box">
            <div class="m-label">좋아요</div>
            <div class="m-val red">{info['like_count']:,}</div>
        </div>
        <div class="metric-box">
            <div class="m-label">댓글 수</div>
            <div class="m-val blue">{info['comment_count']:,}</div>
        </div>
        <div class="metric-box">
            <div class="m-label">최종 업데이트</div>
            <div class="m-val small">{now_str}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ════════════════════════════════════════════
    # 📈 시간대별 누적 조회수 추이
    # ════════════════════════════════════════════
    vt = chart_view_trend(info)
    if vt:
        with st.container(border=True):
            st.markdown('<div class="card-title">📈 시간대별 누적 조회수 추이</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(vt, use_container_width=True,
                            config={"displayModeBar": False})

    # ════════════════════════════════════════════
    # 😊 전체 감성 분포
    # ════════════════════════════════════════════
    with st.container(border=True):
        st.markdown('<div class="card-title">😊 전체 감성 분포</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(chart_donut(res_df), use_container_width=True,
                        config={"displayModeBar": False})

    # ════════════════════════════════════════════
    # 📊 분류별 여론
    # ════════════════════════════════════════════
    with st.container(border=True):
        st.markdown('<div class="card-title">📊 분류별 여론 (긍정/부정/중립)</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(chart_topic_bar(res_df), use_container_width=True,
                        config={"displayModeBar": False})

    # ════════════════════════════════════════════
    # 📝 전체 분석 데이터
    # ════════════════════════════════════════════
    with st.container(border=True):
        col_t, col_f = st.columns([3, 1])
        with col_t:
            st.markdown('<div class="card-title">📝 전체 분석 데이터</div>',
                        unsafe_allow_html=True)
        with col_f:
            sel = st.selectbox("감성 필터", ["전체"] + Config.SENTIMENT_LABELS,
                               label_visibility="collapsed")

        st.markdown('<div class="sort-hint">헤더를 클릭해 정렬하세요</div>',
                    unsafe_allow_html=True)

        filtered = res_df if sel == "전체" else res_df[res_df["감성"] == sel]

        rows_html = ""
        for _, row in filtered.iterrows():
            css = Config.SENTIMENT_CSS.get(row["감성"], "s-neu")
            rows_html += f"""
            <tr>
                <td><span class="{css}">{row['감성']}</span></td>
                <td><span class="tag">{str(row['분류'])}</span></td>
                <td><strong>{str(row['키워드'])[:18]}</strong></td>
                <td>{str(row['댓글내용'])[:55]}</td>
            </tr>"""

        st.markdown(f"""
        <table class="data-table">
          <thead><tr>
            <th>감성 ↕</th><th>분류 ↕</th><th>키워드 ↕</th><th>댓글 내용</th>
          </tr></thead>
          <tbody>{rows_html}</tbody>
        </table>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            "⬇️ CSV 다운로드",
            filtered.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"analysis_{vid}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    # ════════════════════════════════════════════
    # 면책조항
    # ════════════════════════════════════════════
    st.markdown("""
    <div class="disclaimer">
        <div class="d-title">⚠️ 면책조항 (Disclaimer)</div>
        <ul>
            <li>본 대시보드의 데이터는 유튜브 API를 통해 자동 수집되었으며, 실제 서비스상의 수치와 차이가 있을 수 있습니다.</li>
            <li>댓글 분석 결과는 AI에 의해 생성된 것으로, 실제 작성자의 의도나 공단의 공식 입장과는 다를 수 있습니다.</li>
            <li>제공되는 모든 정보는 참고용이며, 이를 근거로 한 판단에 대한 책임은 사용자에게 있습니다.</li>
        </ul>
    </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
