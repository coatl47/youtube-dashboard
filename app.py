"""
유튜브 실시간 여론 분석 대시보드
레이아웃: roy8in.github.io 에디토리얼 미니멀리즘 스타일
- 좌측 사이드바: URL 입력 + 영상 메타 정보
- 우측 메인: 분석 결과 (감성 / 주제 / 데이터)
"""

import io
import re
import time
import hashlib
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google import genai
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# 0. 페이지 설정 + 커스텀 CSS
# ============================================================
st.set_page_config(
    page_title="여론 분석",
    page_icon="◎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* ── 폰트 ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@300;400;600&family=DM+Mono:wght@300;400&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Serif KR', serif;
    color: #1a1a1a;
}

/* ── 전체 배경 ─────────────────────────────────────── */
.stApp { background-color: #f7f5f0; }

/* ── 사이드바 ──────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #1c2333;
    border-right: none;
}
[data-testid="stSidebar"] * {
    color: #c8cdd8 !important;
    font-family: 'Noto Serif KR', serif !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #ffffff !important;
    letter-spacing: 0.02em;
}
[data-testid="stSidebar"] .stTextInput input {
    background: #2a3347 !important;
    border: 1px solid #3d4f6e !important;
    color: #e8eaf0 !important;
    border-radius: 2px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.78rem !important;
}
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: #7b9cc4 !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton button {
    background: #2d6a9f !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 2px !important;
    width: 100% !important;
    font-family: 'Noto Serif KR', serif !important;
    letter-spacing: 0.05em;
    padding: 0.55rem 0rem !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #3a7dbf !important;
}
[data-testid="stSidebar"] hr {
    border-color: #2e3d56 !important;
    margin: 1.2rem 0 !important;
}

/* ── 메인 영역 헤더 ────────────────────────────────── */
.main-header {
    border-bottom: 2px solid #1c2333;
    padding-bottom: 1rem;
    margin-bottom: 2rem;
}
.main-header h1 {
    font-size: 1.6rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: #1c2333;
    margin: 0;
}
.main-header .subtitle {
    font-size: 0.78rem;
    color: #7a7a7a;
    font-family: 'DM Mono', monospace;
    margin-top: 0.3rem;
    letter-spacing: 0.05em;
}

/* ── 섹션 제목 ─────────────────────────────────────── */
.section-title {
    font-size: 0.68rem;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #7a7a7a;
    margin-bottom: 1rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #d8d4cc;
}

/* ── 메트릭 카드 ───────────────────────────────────── */
.metric-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: #d8d4cc;
    border: 1px solid #d8d4cc;
    margin-bottom: 2rem;
}
.metric-card {
    background: #f7f5f0;
    padding: 1.1rem 1.2rem;
    text-align: left;
}
.metric-label {
    font-size: 0.62rem;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #9a9a9a;
    margin-bottom: 0.4rem;
}
.metric-value {
    font-size: 1.45rem;
    font-weight: 600;
    color: #1c2333;
    letter-spacing: -0.02em;
    font-family: 'DM Mono', monospace;
}

/* ── Streamlit metric 오버라이드 ──────────────────── */
[data-testid="metric-container"] {
    background: #f7f5f0;
    border: 1px solid #d8d4cc;
    padding: 1rem 1.2rem !important;
    border-radius: 0 !important;
}
[data-testid="metric-container"] label {
    font-size: 0.62rem !important;
    font-family: 'DM Mono', monospace !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: #9a9a9a !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
    font-family: 'DM Mono', monospace !important;
    color: #1c2333 !important;
}

/* ── 영상 제목 블록 ─────────────────────────────────── */
.video-title-block {
    background: #1c2333;
    color: #f0ede6;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.6rem;
}
.video-title-block .vt-label {
    font-size: 0.6rem;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #7b9cc4;
    margin-bottom: 0.5rem;
}
.video-title-block .vt-title {
    font-size: 1.05rem;
    font-weight: 400;
    color: #f0ede6;
    line-height: 1.5;
}
.video-title-block .vt-meta {
    font-size: 0.7rem;
    font-family: 'DM Mono', monospace;
    color: #6a7a90;
    margin-top: 0.6rem;
}

/* ── 감성 배지 ─────────────────────────────────────── */
.badge-pos { background:#e8f5f0; color:#1a6b4a; padding:2px 8px; font-size:0.7rem; font-family:'DM Mono',monospace; border-radius:2px; }
.badge-neg { background:#fdf0ee; color:#8b2a1a; padding:2px 8px; font-size:0.7rem; font-family:'DM Mono',monospace; border-radius:2px; }
.badge-neu { background:#f0eeff; color:#4a3d8b; padding:2px 8px; font-size:0.7rem; font-family:'DM Mono',monospace; border-radius:2px; }

/* ── 차트 컨테이너 ─────────────────────────────────── */
.chart-wrap {
    background: #ffffff;
    border: 1px solid #d8d4cc;
    padding: 1.2rem;
    margin-bottom: 1.4rem;
}

/* ── 사이드바 메타 정보 ────────────────────────────── */
.meta-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.55rem 0;
    border-bottom: 1px solid #2e3d56;
    font-size: 0.78rem;
}
.meta-key {
    font-family: 'DM Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #5a6a80 !important;
}
.meta-val {
    font-family: 'DM Mono', monospace;
    font-size: 0.75rem;
    color: #c8cdd8 !important;
    text-align: right;
}

/* ── 탭 스타일 ─────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 2px solid #1c2333;
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.6rem 1.2rem;
    border-radius: 0;
    color: #7a7a7a;
    background: transparent;
    border: none;
}
.stTabs [aria-selected="true"] {
    background: #1c2333 !important;
    color: #ffffff !important;
}

/* ── 데이터프레임 ──────────────────────────────────── */
.stDataFrame { border: 1px solid #d8d4cc !important; }

/* ── 다운로드 버튼 ─────────────────────────────────── */
.stDownloadButton button {
    background: transparent !important;
    border: 1px solid #1c2333 !important;
    color: #1c2333 !important;
    border-radius: 0 !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.08em !important;
    padding: 0.45rem 1rem !important;
}
.stDownloadButton button:hover {
    background: #1c2333 !important;
    color: #ffffff !important;
}

/* ── selectbox ─────────────────────────────────────── */
.stSelectbox select, [data-baseweb="select"] {
    border-radius: 0 !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.78rem !important;
}

/* ── 상태 메시지 ───────────────────────────────────── */
[data-testid="stStatusWidget"] {
    border-radius: 0 !important;
    border: 1px solid #d8d4cc !important;
}

/* ── 구분선 ─────────────────────────────────────────── */
hr { border-color: #d8d4cc !important; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 1. CONFIG
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

    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {
        "긍정": "#2a7d5a",
        "부정": "#b84030",
        "중립": "#5a4d9a",
    }


# ============================================================
# 2. Gemini 클라이언트
# ============================================================
@st.cache_resource(show_spinner=False)
def _gemini_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])


def _is_quota_error(err: str) -> bool:
    return any(k.lower() in err.lower() for k in
               ["429", "RESOURCE_EXHAUSTED", "quota", "rate limit"])


def _is_not_found_error(err: str) -> bool:
    return any(k in err.lower() for k in
               ["not found", "404", "does not exist", "unsupported"])


# ============================================================
# 3. YouTube 데이터
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
        resp  = _yt_client().videos().list(part="snippet,statistics", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
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
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(video_id: str, limit: int = Config.COMMENT_LIMIT) -> pd.DataFrame:
    try:
        resp = _yt_client().commentThreads().list(
            part="snippet", videoId=video_id,
            maxResults=min(limit * 2, 100), order="relevance",
        ).execute()
    except Exception:
        return pd.DataFrame()

    rows, seen = [], set()
    for item in resp.get("items", []):
        snip  = item["snippet"]["topLevelComment"]["snippet"]
        clean = re.sub(r"<[^>]+>", "", snip.get("textDisplay", ""))
        clean = re.sub(r"https?://\S+", "", clean).replace("\n", " ").strip()
        if len(clean) < Config.COMMENT_MIN_LEN or clean in seen:
            continue
        seen.add(clean)
        rows.append({"time": snip["publishedAt"], "text": clean,
                     "likes": int(snip.get("likeCount", 0))})
        if len(rows) >= limit:
            break

    if not rows:
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
        f"규칙: 감성={labels} 중 하나만. 영어 금지. CSV만 출력.\n\n{lines}"
    )


def _parse_response(text: str) -> pd.DataFrame:
    text  = re.sub(r"```[a-z]*", "", text).replace("```", "").strip()
    match = re.search(r"감성\s*\|\s*분류", text)
    if not match:
        return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(text[match.start():]),
                         sep="|", on_bad_lines="skip", engine="python", dtype=str)
    except Exception:
        return pd.DataFrame()
    df.columns = [c.strip() for c in df.columns]
    if not {"감성","분류","키워드","내용"}.issubset(df.columns):
        return pd.DataFrame()
    df = df[["감성","분류","키워드","내용"]].copy().dropna(subset=["감성","분류"])
    df["감성"] = df["감성"].str.strip()
    df.loc[~df["감성"].isin(set(Config.SENTIMENT_LABELS)), "감성"] = "중립"
    return df[df["내용"].str.strip().str.len() > 0].reset_index(drop=True)


def _call_api(prompt: str) -> tuple:
    client, last_error = _gemini_client(), "모든 모델 실패"
    for model_name in Config.GEMINI_MODEL_PRIORITY:
        for attempt in range(Config.MAX_RETRIES):
            try:
                resp = client.models.generate_content(model=model_name, contents=prompt)
                return resp.text, model_name, None
            except Exception as e:
                err = str(e)
                last_error = f"[{model_name}] {err}"
                if _is_quota_error(err) or _is_not_found_error(err):
                    break
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_WAIT)
    return None, None, last_error


@st.cache_data(ttl=86400, show_spinner=False)
def _run_batches(comment_hash: str, comment_texts: list) -> tuple:
    batches = [comment_texts[i:i+Config.BATCH_SIZE]
               for i in range(0, len(comment_texts), Config.BATCH_SIZE)]
    results, errors = [], []
    for idx, batch in enumerate(batches):
        raw, model, err = _call_api(_build_prompt(batch))
        if raw:
            results.append((raw, model))
            if idx < len(batches) - 1:
                time.sleep(1)
        else:
            errors.append(f"배치 {idx+1}: {err}")
    return results, errors


def analyze_comments(comment_hash: str, comment_texts: list) -> pd.DataFrame:
    raw_results, errors = _run_batches(comment_hash, comment_texts)
    if errors:
        with st.expander("⚠️ 오류 상세", expanded=True):
            for e in errors:
                st.code(e)
    frames = []
    for raw, _ in raw_results:
        parsed = _parse_response(raw)
        if not parsed.empty:
            frames.append(parsed)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ============================================================
# 5. 차트 (plotly — roy8in 스타일 팔레트 적용)
# ============================================================
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Mono, monospace", size=11, color="#4a4a4a"),
    margin=dict(l=0, r=0, t=30, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def chart_sentiment_donut(res_df: pd.DataFrame) -> go.Figure:
    sc  = res_df["감성"].value_counts().reset_index()
    sc.columns = ["감성", "count"]
    colors = [Config.SENTIMENT_COLORS.get(s, "#aaa") for s in sc["감성"]]
    fig = go.Figure(go.Pie(
        labels=sc["감성"], values=sc["count"],
        hole=0.6,
        marker=dict(colors=colors, line=dict(color="#f7f5f0", width=3)),
        textfont=dict(family="DM Mono, monospace", size=11),
        hovertemplate="%{label}: %{value}개 (%{percent})<extra></extra>",
    ))
    total = sc["count"].sum()
    fig.add_annotation(text=f"<b>{total}</b><br><span style='font-size:10px'>댓글</span>",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(family="DM Mono, monospace", size=16, color="#1c2333"))
    fig.update_layout(**PLOT_LAYOUT, height=280, showlegend=True)
    return fig


def chart_trend(raw_df: pd.DataFrame) -> go.Figure:
    trend = raw_df.set_index("time").resample("h").size().reset_index(name="n")
    fig = go.Figure(go.Scatter(
        x=trend["time"], y=trend["n"],
        mode="lines+markers",
        line=dict(color="#1c2333", width=1.8),
        marker=dict(size=5, color="#2d6a9f"),
        fill="tozeroy",
        fillcolor="rgba(28,35,51,0.06)",
        hovertemplate="%{x|%m/%d %H시}: %{y}개<extra></extra>",
    ))
    fig.update_layout(**PLOT_LAYOUT, height=220,
                      xaxis=dict(showgrid=False, zeroline=False),
                      yaxis=dict(showgrid=True, gridcolor="#e8e4de", zeroline=False))
    return fig


def chart_topic_bar(res_df: pd.DataFrame) -> go.Figure:
    bd    = res_df.groupby(["분류","감성"]).size().reset_index(name="n")
    order = bd.groupby("분류")["n"].sum().sort_values(ascending=True).index.tolist()
    fig   = px.bar(bd, x="n", y="분류", color="감성", orientation="h",
                   color_discrete_map=Config.SENTIMENT_COLORS,
                   category_orders={"분류": order},
                   labels={"n":"댓글 수","분류":""},
                   height=max(260, len(order)*38))
    fig.update_layout(**PLOT_LAYOUT,
                      xaxis=dict(showgrid=True, gridcolor="#e8e4de", zeroline=False),
                      yaxis=dict(showgrid=False),
                      bargap=0.35)
    fig.update_traces(marker_line_width=0)
    return fig


# ============================================================
# 6. 사이드바
# ============================================================
def render_sidebar() -> tuple[str | None, dict | None, pd.DataFrame]:
    with st.sidebar:
        st.markdown("### 여론 분석")
        st.markdown('<hr>', unsafe_allow_html=True)

        url = st.text_input(
            "YouTube URL",
            placeholder="https://youtu.be/...",
            label_visibility="collapsed",
        )
        run = st.button("분석 시작", use_container_width=True)

        st.markdown('<hr>', unsafe_allow_html=True)

        info, raw_df = None, pd.DataFrame()

        if run and url:
            video_id = extract_video_id(url)
            if not video_id:
                st.error("유효하지 않은 URL입니다.")
                return None, None, pd.DataFrame()

            with st.spinner("수집 중..."):
                info   = fetch_video_info(video_id)
                raw_df = fetch_comments(video_id)

            if info:
                # 영상 메타 정보
                st.markdown(f"""
                <div style='font-size:0.8rem; color:#c8cdd8; line-height:1.6;
                            margin-bottom:1rem; font-family:Noto Serif KR,serif;'>
                    {info['title']}
                </div>
                """, unsafe_allow_html=True)

                for label, val in [
                    ("채널",   info["channel"]),
                    ("게시일", info["published"]),
                    ("조회수", f"{info['view_count']:,}"),
                    ("좋아요", f"{info['like_count']:,}"),
                    ("댓글",   f"{info['comment_count']:,}"),
                ]:
                    st.markdown(f"""
                    <div class='meta-item'>
                        <span class='meta-key'>{label}</span>
                        <span class='meta-val'>{val}</span>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown('<hr>', unsafe_allow_html=True)
                st.markdown(f"""
                <div style='font-size:0.62rem; font-family:DM Mono,monospace;
                            color:#4a5a70; letter-spacing:0.08em;'>
                    {datetime.now().strftime('%Y.%m.%d %H:%M')} 기준
                </div>
                """, unsafe_allow_html=True)

            return video_id, info, raw_df

        # 초기 안내
        st.markdown("""
        <div style='font-size:0.75rem; color:#4a5a70; line-height:1.8;
                    font-family:DM Mono,monospace; letter-spacing:0.04em;'>
            유튜브 영상 URL을 입력하고<br>
            분석 시작 버튼을 누르세요.<br><br>
            — 댓글 감성 분석<br>
            — 주제별 여론 분포<br>
            — 시간대별 반응 추이
        </div>
        """, unsafe_allow_html=True)

    return None, None, pd.DataFrame()


# ============================================================
# 7. 메인
# ============================================================
def main():
    # 사이드바
    video_id, info, raw_df = render_sidebar()

    # ── 헤더 ─────────────────────────────────────────────────
    st.markdown("""
    <div class='main-header'>
        <h1>YouTube 여론 분석</h1>
        <div class='subtitle'>COMMENT SENTIMENT &amp; TOPIC ANALYSIS — POWERED BY GEMINI</div>
    </div>
    """, unsafe_allow_html=True)

    # ── 분석 전 초기 화면 ────────────────────────────────────
    if not video_id or info is None:
        st.markdown("""
        <div style='display:flex; align-items:center; justify-content:center;
                    height:55vh; flex-direction:column; gap:1rem;'>
            <div style='font-size:3rem; opacity:0.15;'>◎</div>
            <div style='font-size:0.75rem; font-family:DM Mono,monospace;
                        letter-spacing:0.15em; color:#9a9a9a; text-transform:uppercase;'>
                좌측에 URL을 입력해 분석을 시작하세요
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    if raw_df.empty:
        st.error("댓글을 수집하지 못했습니다.")
        return

    # ── AI 분석 ──────────────────────────────────────────────
    with st.status("Gemini 분석 중...", expanded=False) as status:
        h      = hashlib.md5("".join(raw_df["text"].tolist()).encode()).hexdigest()
        res_df = analyze_comments(h, raw_df["text"].tolist())
        if res_df.empty:
            status.update(label="분석 실패", state="error")
            st.error("AI 분석에 실패했습니다.")
            return
        status.update(label="분석 완료", state="complete")

    # ── 영상 제목 블록 ────────────────────────────────────────
    st.markdown(f"""
    <div class='video-title-block'>
        <div class='vt-label'>분석 대상</div>
        <div class='vt-title'>{info['title']}</div>
        <div class='vt-meta'>{info['channel']} · {info['published']}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── 메트릭 4개 ───────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    pos_n = (res_df["감성"] == "긍정").sum()
    neg_n = (res_df["감성"] == "부정").sum()
    pos_r = f"{pos_n/len(res_df)*100:.0f}%" if len(res_df) else "—"
    neg_r = f"{neg_n/len(res_df)*100:.0f}%" if len(res_df) else "—"

    with c1:
        st.metric("분석 댓글", f"{len(res_df):,}")
    with c2:
        st.metric("긍정 비율", pos_r)
    with c3:
        st.metric("부정 비율", neg_r)
    with c4:
        topic_n = res_df["분류"].nunique()
        st.metric("식별된 주제", f"{topic_n}개")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 탭: 감성 / 주제 / 추이 / 데이터 ─────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["감성 분석", "주제별 여론", "댓글 추이", "원본 데이터"])

    with tab1:
        st.markdown('<div class="section-title">Sentiment Distribution</div>',
                    unsafe_allow_html=True)
        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
            st.plotly_chart(chart_sentiment_donut(res_df), use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with col_b:
            # 감성별 상위 키워드
            st.markdown('<div class="section-title">주요 키워드</div>',
                        unsafe_allow_html=True)
            for sent in Config.SENTIMENT_LABELS:
                sub = res_df[res_df["감성"] == sent]["키워드"].dropna()
                if sub.empty:
                    continue
                keywords = ", ".join(
                    sorted(set(
                        k.strip()
                        for row in sub
                        for k in str(row).split(",")
                        if k.strip()
                    ))[:12]
                )
                badge_cls = {"긍정":"badge-pos","부정":"badge-neg","중립":"badge-neu"}[sent]
                st.markdown(
                    f'<span class="{badge_cls}">{sent}</span>'
                    f'<span style="font-size:0.78rem; margin-left:0.6rem; color:#4a4a4a;">'
                    f'{keywords}</span><br><br>',
                    unsafe_allow_html=True,
                )

    with tab2:
        st.markdown('<div class="section-title">Topic &amp; Sentiment Breakdown</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.plotly_chart(chart_topic_bar(res_df), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab3:
        st.markdown('<div class="section-title">Hourly Comment Volume</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        st.plotly_chart(chart_trend(raw_df), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab4:
        st.markdown('<div class="section-title">Raw Analysis Data</div>',
                    unsafe_allow_html=True)

        # 감성 필터
        col_f, col_dl = st.columns([2, 1])
        with col_f:
            sel = st.selectbox("감성 필터",
                               ["전체"] + Config.SENTIMENT_LABELS,
                               label_visibility="collapsed")
        filtered = res_df if sel == "전체" else res_df[res_df["감성"] == sel]

        st.dataframe(
            filtered,
            use_container_width=True,
            height=420,
            column_config={
                "감성":  st.column_config.TextColumn("감성",  width=60),
                "분류":  st.column_config.TextColumn("주제",  width=100),
                "키워드":st.column_config.TextColumn("키워드",width=120),
                "내용":  st.column_config.TextColumn("내용",  width=300),
            },
        )
        with col_dl:
            st.download_button(
                "CSV 다운로드",
                filtered.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"analysis_{video_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
