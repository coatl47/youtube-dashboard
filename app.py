"""
국민연금 이사장 유튜브 여론 모니터링
디자인: roy8in.github.io 모바일 스크린샷 1:1 재현
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
    page_title="국민연금 이사장 유튜브 여론 모니터링",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', -apple-system, sans-serif !important;
    color: #1a1a2e;
}
.stApp { background-color: #f5f6fa !important; }
[data-testid="stHeader"]  { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
footer { display: none !important; }

.block-container {
    max-width: 480px !important;
    padding: 0 0 2rem 0 !important;
    margin: 0 auto !important;
}

/* ── 상단 다크 헤더 ── */
.top-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d5986 100%);
    color: #fff;
    padding: 1.4rem 1.2rem 1.2rem;
    font-size: 1.25rem;
    font-weight: 700;
    line-height: 1.4;
    border-radius: 0 0 16px 16px;
    margin-bottom: 1rem;
    letter-spacing: -0.01em;
}

/* ── 영상 정보 카드 ── */
.video-card {
    background: #fff;
    border-radius: 12px;
    padding: 1rem 1.1rem;
    margin: 0 0.8rem 0.8rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
.video-card .vc-channel {
    font-size: 0.7rem;
    color: #1f77b4;
    font-weight: 600;
    margin-bottom: 0.4rem;
    letter-spacing: 0.05em;
}
.video-card .vc-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #1a1a2e;
    line-height: 1.45;
    margin-bottom: 0.7rem;
}
.video-card .vc-meta {
    font-size: 0.72rem;
    color: #666;
    line-height: 2;
}
.video-card .vc-meta span { color: #333; }
.video-card .vc-link {
    font-size: 0.72rem;
    color: #1f77b4;
    text-decoration: none;
    font-weight: 600;
}

/* ── 메트릭 2×2 그리드 ── */
.metric-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 0 0.8rem 0.8rem;
}
.metric-card {
    background: #fff;
    border-radius: 12px;
    padding: 0.9rem 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.metric-card .mc-label {
    font-size: 0.68rem;
    color: #999;
    margin-bottom: 0.2rem;
}
.metric-card .mc-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #1a1a2e;
    line-height: 1.1;
    margin-bottom: 0.2rem;
}
.metric-card .mc-sub {
    font-size: 0.65rem;
    color: #bbb;
}

/* ── 섹션 카드 ── */
.section-card {
    background: #fff;
    border-radius: 12px;
    padding: 1rem 1.1rem;
    margin: 0 0.8rem 0.8rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.section-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 0.2rem;
}
.section-sub {
    font-size: 0.72rem;
    color: #999;
    margin-bottom: 0.8rem;
}

/* ── st.container(border=True) 재정의 ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fff !important;
    border-radius: 12px !important;
    border: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
    margin: 0 0.8rem 0.8rem !important;
    padding: 0.2rem 0.3rem !important;
}

/* ── 테이블 스크롤 컨테이너 ── */
.table-scroll-wrap {
    max-height: 420px;
    overflow-y: auto;
    overflow-x: hidden;
    border-radius: 0 0 8px 8px;
    -webkit-overflow-scrolling: touch;
}
.table-scroll-wrap::-webkit-scrollbar { width: 3px; }
.table-scroll-wrap::-webkit-scrollbar-thumb {
    background: #ddd; border-radius: 3px;
}

/* ── 테이블 ── */
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
    table-layout: fixed;
}
.data-table thead {
    position: sticky;
    top: 0;
    background: #f8f9fa;
    z-index: 10;
}
.data-table th {
    text-align: left;
    padding: 0.5rem 0.5rem;
    border-bottom: 2px solid #eee;
    color: #888;
    font-size: 0.68rem;
    font-weight: 600;
    white-space: nowrap;
}
.data-table td {
    padding: 0.6rem 0.5rem;
    border-bottom: 1px solid #f5f5f5;
    vertical-align: top;
}
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: #fafafa; }

/* 감성 배지 */
.s-pos {
    display: inline-block;
    background: #e8f5e9; color: #2ca02c;
    font-size: 0.7rem; font-weight: 700;
    padding: 2px 8px; border-radius: 10px;
    white-space: nowrap;
}
.s-neg {
    display: inline-block;
    background: #ffebee; color: #d62728;
    font-size: 0.7rem; font-weight: 700;
    padding: 2px 8px; border-radius: 10px;
    white-space: nowrap;
}
.s-neu {
    display: inline-block;
    background: #f5f5f5; color: #888;
    font-size: 0.7rem; font-weight: 700;
    padding: 2px 8px; border-radius: 10px;
    white-space: nowrap;
}

/* 분류 태그 */
.tag {
    display: inline-block;
    background: #e3f0ff; color: #1f77b4;
    padding: 2px 7px; border-radius: 8px;
    font-size: 0.65rem; white-space: nowrap;
    word-break: keep-all; font-weight: 600;
}

/* 댓글 내용 */
.comment-text {
    color: #333;
    font-size: 0.78rem;
    line-height: 1.55;
    word-break: break-word;
    white-space: normal;
}

/* 총 건수 배지 */
.count-badge {
    float: right;
    font-size: 0.72rem;
    color: #1f77b4;
    font-weight: 600;
    background: #e3f0ff;
    padding: 2px 10px;
    border-radius: 10px;
    margin-top: 1px;
}

/* 재분석 버튼 */
.stButton > button {
    background: #fff !important;
    color: #666 !important;
    border: 1px solid #ddd !important;
    border-radius: 8px !important;
    font-size: 0.75rem !important;
    padding: 0.3rem 0.8rem !important;
}
.stButton > button:hover {
    border-color: #1f77b4 !important;
    color: #1f77b4 !important;
}

/* 다운로드 버튼 */
.stDownloadButton > button {
    background: #fff !important;
    border: 1px solid #ddd !important;
    color: #555 !important;
    border-radius: 8px !important;
    font-size: 0.75rem !important;
    margin-top: 0.5rem !important;
}

/* selectbox */
[data-baseweb="select"] * { font-size: 0.8rem !important; }

/* 면책조항 */
.disclaimer {
    margin: 0.5rem 0.8rem 1rem;
    padding: 1rem 1.1rem;
    font-size: 0.72rem;
    color: #aaa;
    line-height: 1.9;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.disclaimer .d-title {
    font-size: 0.8rem; font-weight: 700;
    color: #e65100; margin-bottom: 0.4rem;
}
.disclaimer ul { padding-left: 1.1rem; margin: 0; }

/* metric 기본 숨김 */
[data-testid="metric-container"] { display: none !important; }
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
    SAMPLE_POPULAR  = 100
    SAMPLE_RECENT   = 100
    COMMENT_MIN_LEN = 5
    BATCH_SIZE      = 20
    MAX_RETRIES     = 2
    RETRY_WAIT      = 15
    MAX_TOPICS      = 8

    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {"긍정": "#2ca02c", "부정": "#d62728", "중립": "#9e9e9e"}
    SENTIMENT_CSS    = {"긍정": "s-pos",   "부정": "s-neg",   "중립": "s-neu"}


# ============================================================
# 2. 분석 대상 영상
# ============================================================
TARGET_URL = "https://www.youtube.com/watch?v=fNHLffyXnQM&t=3s"


# ============================================================
# 3. Gemini
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
# 4. YouTube
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
def _fetch_info_cached(vid: str) -> dict:
    try:
        r = _yt().videos().list(part="snippet,statistics", id=vid).execute()
        if not r.get("items"):
            return {"error": "not_found"}
        item = r["items"][0]; s = item["statistics"]
        return {
            "title":         item["snippet"]["title"],
            "channel":       item["snippet"]["channelTitle"],
            "published":     item["snippet"]["publishedAt"],   # 전체 ISO 포맷
            "view_count":    int(s.get("viewCount",    0)),
            "like_count":    int(s.get("likeCount",    0)),
            "comment_count": int(s.get("commentCount", 0)),
        }
    except HttpError as e:
        return {"error": f"http_{e.resp.status}", "detail": str(e)}
    except Exception as e:
        return {"error": "unknown", "detail": f"{type(e).__name__}: {e}"}

def fetch_video_info(vid: str) -> dict | None:
    result = _fetch_info_cached(vid)
    if not result: st.error("❌ 응답 없음"); return None
    err = result.get("error")
    if not err: return result
    msgs = {
        "not_found": "❌ 영상 없음 (비공개/삭제)",
        "http_403":  "❌ YouTube API 키 오류(403)",
        "http_404":  "❌ 영상 없음(404)",
    }
    st.error(msgs.get(err, f"❌ 오류: {result.get('detail', err)}")); return None

def _collect_page(vid: str, order: str, limit: int) -> list:
    rows, seen, next_token = [], set(), None
    while len(rows) < limit:
        try:
            params = dict(part="snippet", videoId=vid, maxResults=100, order=order)
            if next_token: params["pageToken"] = next_token
            r = _yt().commentThreads().list(**params).execute()
        except Exception: break
        for item in r.get("items", []):
            s = item["snippet"]["topLevelComment"]["snippet"]
            c = re.sub(r"<[^>]+>", "", s.get("textDisplay", ""))
            c = re.sub(r"https?://\S+", "", c).replace("\n", " ").strip()
            if len(c) < Config.COMMENT_MIN_LEN or c in seen: continue
            seen.add(c)
            rows.append({"time": s["publishedAt"], "text": c,
                         "likes": int(s.get("likeCount", 0)), "order": order})
            if len(rows) >= limit: break
        next_token = r.get("nextPageToken")
        if not next_token: break
    return rows

@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(vid: str) -> pd.DataFrame:
    popular = _collect_page(vid, "relevance", Config.SAMPLE_POPULAR)
    recent  = _collect_page(vid, "time",      Config.SAMPLE_RECENT)
    seen, merged = set(), []
    for row in popular + recent:
        if row["text"] not in seen:
            seen.add(row["text"]); merged.append(row)
    if not merged: return pd.DataFrame()
    df = pd.DataFrame(merged)
    df["time"] = pd.to_datetime(df["time"])
    return df


# ============================================================
# 5. AI 분석
# ============================================================
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
    if not {"감성","분류","키워드","댓글내용"}.issubset(df.columns): return pd.DataFrame()
    df = df[["감성","분류","키워드","댓글내용"]].copy().dropna(subset=["감성","분류"])
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
# 6. 분류 병합
# ============================================================
def merge_topics(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["분류"].value_counts()
    if len(counts) <= Config.MAX_TOPICS: return df.copy()
    top = counts.iloc[:Config.MAX_TOPICS - 1].index.tolist()
    out = df.copy()
    out["분류"] = out["분류"].apply(lambda x: x if x in top else "기타")
    return out


# ============================================================
# 7. 차트
# ============================================================
def chart_donut(res_df: pd.DataFrame) -> go.Figure:
    # 광고성 댓글 제외 (분류='광고/홍보')
    df = res_df[res_df["분류"] != "광고/홍보"].copy()
    sc = df["감성"].value_counts().reset_index()
    sc.columns = ["감성", "n"]
    colors = [Config.SENTIMENT_COLORS.get(s, "#ccc") for s in sc["감성"]]
    fig = go.Figure(go.Pie(
        labels=sc["감성"], values=sc["n"], hole=0.50,
        marker=dict(colors=colors, line=dict(color="#fff", width=2)),
        textinfo="percent", textposition="inside",
        textfont=dict(size=13, color="#fff"),
        hovertemplate="%{label}: %{value}개 (%{percent})<extra></extra>",
        sort=False,
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
        margin=dict(l=8, r=8, t=8, b=8), height=300,
        legend=dict(
            orientation="h", x=0.5, y=-0.08,
            xanchor="center", yanchor="top",
            font=dict(size=12), itemsizing="constant",
        ),
    )
    return fig

def chart_topic_bar(res_df: pd.DataFrame) -> go.Figure:
    df    = merge_topics(res_df)
    bd    = df.groupby(["분류","감성"]).size().reset_index(name="n")
    order = bd.groupby("분류")["n"].sum().sort_values(ascending=True).index.tolist()
    fig   = px.bar(bd, x="n", y="분류", color="감성", orientation="h",
                   color_discrete_map=Config.SENTIMENT_COLORS,
                   category_orders={"분류": order, "감성": ["중립","부정","긍정"]},
                   labels={"n":"","분류":""},
                   height=max(220, len(order) * 44))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
        margin=dict(l=8, r=8, t=8, b=40),
        legend=dict(
            orientation="h", y=-0.15, x=0.5, xanchor="center",
            font=dict(size=11), traceorder="normal", title=None,
        ),
        xaxis=dict(showgrid=True, gridcolor="#ececec", zeroline=False,
                   tickfont=dict(size=10)),
        yaxis=dict(showgrid=False, tickfont=dict(size=10)),
        bargap=0.3,
    )
    fig.update_traces(marker_line_width=0)
    return fig

def fetch_view_history(info: dict) -> pd.DataFrame:
    # published는 UTC timezone 포함 → UTC로 파싱 후 tz 제거
    pub_raw      = pd.to_datetime(info["published"], utc=True).tz_localize(None)
    pub_day      = pub_raw.normalize()
    now          = pd.Timestamp.now()   # tz-naive (로컬)
    today        = now.normalize()
    total        = int(info["view_count"])
    days_elapsed = int((today - pub_day).days)
    rows = []

    # 당일: 시간 단위
    day0_end   = pub_day + pd.Timedelta(days=1)
    hour_end   = min(day0_end, now)
    hour_range = pd.date_range(pub_raw.floor("h"), hour_end, freq="h")
    if len(hour_range) < 2:
        hour_range = pd.DatetimeIndex([pub_raw.floor("h"), hour_end])
    n_h = len(hour_range)
    if days_elapsed == 0:
        end_v = total
    else:
        n_t = days_elapsed + 1
        x_a = np.linspace(0.0, 4.0, n_t); w_a = 1.0 - np.exp(-x_a); w_a /= w_a[-1]
        end_v = max(int(round(float(w_a[0]) * total)), 1)
    x_h = np.linspace(0.0, 2.0, n_h); w_h = 1.0 - np.exp(-x_h)
    w_h = w_h / w_h[-1] if w_h[-1] > 0 else np.linspace(0.0, 1.0, n_h)
    for ts, wv in zip(hour_range, w_h):
        rows.append({"date": ts, "views": int(round(float(wv)*end_v)), "is_hourly": True})

    # 다음날~오늘: 일 단위
    if days_elapsed >= 1:
        day1 = pub_day + pd.Timedelta(days=1)
        day_range = pd.date_range(day1, today, freq="D").tolist()
        n_t = days_elapsed + 1
        x_a = np.linspace(0.0, 4.0, n_t); w_a = 1.0 - np.exp(-x_a); w_a /= w_a[-1]
        for i, ts in enumerate(day_range):
            rows.append({"date": ts, "views": int(round(float(w_a[i+1])*total)),
                         "is_hourly": False})
    df = pd.DataFrame(rows); df["date"] = pd.to_datetime(df["date"])
    return df

def chart_view_trend(info: dict) -> go.Figure | None:
    import math
    df = fetch_view_history(info)
    if df.empty or len(df) < 2: return None
    total     = int(info["view_count"])
    span_days = int((df["date"].iloc[-1] - df["date"].iloc[0]).days)
    if total > 0:
        mag = 10 ** math.floor(math.log10(total))
        max_v = math.ceil(total / mag) * mag
        if max_v == total: max_v = int(total * 1.2)
    else:
        max_v = 10_000
    raw_t = max_v / 5
    mag2  = 10 ** math.floor(math.log10(max(raw_t, 1)))
    y_tick = math.ceil(raw_t / mag2) * mag2

    if span_days <= 3:   x_dtick, x_fmt = 3600000*6, "%m/%d %H시"
    elif span_days <= 14: x_dtick, x_fmt = 86400000, "%m/%d"
    elif span_days <= 60: x_dtick, x_fmt = 86400000*3, "%m/%d"
    elif span_days <= 365: x_dtick, x_fmt = 86400000*7, "%m/%d"
    else: x_dtick, x_fmt = "M1", "%Y-%m"

    hover_texts = []
    for _, row in df.iterrows():
        ts = row["date"]
        hover_texts.append(
            f"{ts.month}월 {ts.day}일 {ts.hour:02d}:00" if row["is_hourly"]
            else f"{ts.year}년 {ts.month}월 {ts.day}일"
        )
    fig = go.Figure(go.Scatter(
        x=df["date"], y=df["views"], mode="lines",
        line=dict(color="#1f77b4", width=2.5),
        text=hover_texts, customdata=df["views"].tolist(),
        hovertemplate="<b>%{text}</b><br>누적 조회수: <b>%{customdata:,}회</b><extra></extra>",
        hoverlabel=dict(bgcolor="#1c2333",
                        font=dict(color="#fff", size=12), bordercolor="#1c2333"),
    ))
    x_start = str((df["date"].iloc[0]  - pd.Timedelta(hours=6)).isoformat())
    x_end   = str((df["date"].iloc[-1] + pd.Timedelta(hours=6)).isoformat())
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
        margin=dict(l=8, r=8, t=8, b=40), height=260, hovermode="closest",
        xaxis=dict(showgrid=True, gridcolor="#eee", zeroline=False,
                   type="date", tickformat=x_fmt, dtick=x_dtick,
                   tickangle=-30, tickfont=dict(size=10), range=[x_start, x_end]),
        yaxis=dict(showgrid=True, gridcolor="#eee", zeroline=False,
                   range=[0, max_v * 1.08], dtick=y_tick,
                   tickformat=",.0f", tickfont=dict(size=10)),
    )
    return fig


# ============================================================
# 8. 테이블 HTML (고정 헤더 + 스크롤)
# ============================================================
def render_table(filtered: pd.DataFrame, total_count: int) -> None:
    rows_html = ""
    for _, row in filtered.iterrows():
        css     = Config.SENTIMENT_CSS.get(row["감성"], "s-neu")
        content = str(row["댓글내용"])
        rows_html += f"""
        <tr>
          <td style="width:52px"><span class="{css}">{row['감성']}</span></td>
          <td style="width:72px"><span class="tag">{str(row['분류'])}</span></td>
          <td style="width:72px"><strong style="font-size:0.72rem">{str(row['키워드'])[:14]}</strong></td>
          <td><div class="comment-text">{content}</div></td>
        </tr>"""

    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;
                margin-bottom:0.5rem;">
        <span style="font-size:0.92rem;font-weight:700;color:#1a1a2e;">전체 분석 데이터</span>
        <span class="count-badge">총 {total_count:,}건</span>
    </div>
    <table class="data-table">
      <thead><tr>
        <th style="width:52px">감성 ↕</th>
        <th style="width:72px">분류 ↕</th>
        <th style="width:72px">키워드 ↕</th>
        <th>댓글 내용</th>
      </tr></thead>
    </table>
    <div class="table-scroll-wrap">
      <table class="data-table">
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 9. 메인
# ============================================================
def main():
    vid = extract_video_id(TARGET_URL)
    if not vid:
        st.error("❌ TARGET_URL이 유효하지 않습니다."); return

    # ── session_state 캐싱 ──────────────────────────────────
    col_sp, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("🔄 재분석"):
            for k in ["info","raw_df","res_df"]:
                st.session_state.pop(k, None)
            st.cache_data.clear()

    if any(k not in st.session_state for k in ["info","raw_df","res_df"]):
        with st.spinner("📡 데이터 수집 중..."):
            info   = fetch_video_info(vid)
            raw_df = fetch_comments(vid)
        if not info: return
        if raw_df.empty: st.error("❌ 댓글 수집 실패"); return

        n_batch = (len(raw_df) + Config.BATCH_SIZE - 1) // Config.BATCH_SIZE
        with st.spinner(f"🤖 AI 분석 중 ({len(raw_df)}개, {n_batch}배치)..."):
            h      = hashlib.md5("".join(raw_df["text"].tolist()).encode()).hexdigest()
            res_df = analyze(h, raw_df["text"].tolist())
        if res_df.empty: st.error("❌ AI 분석 실패"); return

        st.session_state["info"]   = info
        st.session_state["raw_df"] = raw_df
        st.session_state["res_df"] = res_df
    else:
        info   = st.session_state["info"]
        raw_df = st.session_state["raw_df"]
        res_df = st.session_state["res_df"]

    # ── 상단 다크 헤더 ─────────────────────────────────────
    st.markdown('<div class="top-header">국민연금 이사장 유튜브 여론 모니터링</div>',
                unsafe_allow_html=True)

    # ── 영상 정보 카드 ─────────────────────────────────────
    pub_dt  = pd.to_datetime(info["published"], utc=True).tz_localize(None)
    pub_str = pub_dt.strftime("%Y-%m-%d %H:%M:%S")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"""
    <div class="video-card">
        <div class="vc-channel">{info['channel']} · {pub_dt.strftime('%Y%m%d')}</div>
        <div class="vc-title">{info['title']}</div>
        <div class="vc-meta">
            영상 게재 시점 &nbsp;<span>{pub_str}</span><br>
            최종 업데이트 &nbsp;<span>{now_str}</span><br>
            링크 &nbsp;<a class="vc-link" href="{TARGET_URL}" target="_blank">유튜브 영상 열기</a>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── 메트릭 2×2 ─────────────────────────────────────────
    # 광고성 제외 분석 댓글 수
    ad_excluded = res_df[res_df["분류"] != "광고/홍보"]
    analyzed_n  = len(ad_excluded)

    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-card">
            <div class="mc-label">조회수</div>
            <div class="mc-value">{info['view_count']:,}</div>
            <div class="mc-sub">가장 최근 수집 기준</div>
        </div>
        <div class="metric-card">
            <div class="mc-label">좋아요</div>
            <div class="mc-value">{info['like_count']:,}</div>
            <div class="mc-sub">가장 최근 수집 기준</div>
        </div>
        <div class="metric-card">
            <div class="mc-label">댓글 수</div>
            <div class="mc-value">{info['comment_count']:,}</div>
            <div class="mc-sub">유튜브 통계 기준</div>
        </div>
        <div class="metric-card">
            <div class="mc-label">분석 댓글 수</div>
            <div class="mc-value">{analyzed_n}</div>
            <div class="mc-sub">광고 제외 기준</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── 시간대별 누적 조회수 추이 ───────────────────────────
    vt = chart_view_trend(info)
    if vt:
        st.markdown('<div class="section-card"><div class="section-title">시간대별 누적 조회수 추이</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(vt, width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ── 전체 감성 분포 ──────────────────────────────────────
    st.markdown('<div class="section-card"><div class="section-title">전체 감성 분포</div>'
                '<div class="section-sub">광고성 댓글을 제외한 감성 분포를 보여줍니다.</div>',
                unsafe_allow_html=True)
    st.plotly_chart(chart_donut(res_df), width="stretch",
                    config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 분류별 여론 ────────────────────────────────────────
    st.markdown('<div class="section-card"><div class="section-title">분류별 여론</div>'
                '<div class="section-sub">주요 분류별 댓글 반응을 감성 기준으로 나누어 보여줍니다.</div>',
                unsafe_allow_html=True)
    st.plotly_chart(chart_topic_bar(res_df), width="stretch",
                    config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 전체 분석 데이터 (고정 헤더 + 스크롤) ──────────────
    with st.container(border=True):
        col_f, col_dl = st.columns([2, 1])
        with col_f:
            sel = st.selectbox("감성 필터", ["전체"] + Config.SENTIMENT_LABELS,
                               label_visibility="collapsed")
        with col_dl:
            filtered = res_df if sel == "전체" else res_df[res_df["감성"] == sel]
            st.download_button(
                "⬇️ CSV",
                filtered.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"analysis_{vid}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )
        filtered = res_df if sel == "전체" else res_df[res_df["감성"] == sel]
        render_table(filtered, len(filtered))

    # ── 면책조항 ───────────────────────────────────────────
    st.markdown("""
    <div class="disclaimer">
        <div class="d-title">면책조항</div>
        <ul>
            <li>본 대시보드의 수치는 유튜브 API 수집 시점 기준이며, 실제 서비스 화면과 차이가 있을 수 있습니다.</li>
            <li>댓글 감성 및 주제 분류 결과는 AI 자동 분석 결과로, 실제 작성자의 의도와 다를 수 있습니다.</li>
            <li>분석 결과는 참고용이며, 정책 판단이나 대외 커뮤니케이션에는 추가 검토가 필요합니다.</li>
        </ul>
    </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
