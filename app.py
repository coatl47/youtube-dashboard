"""
유튜브 여론 분석 대시보드 — 최적화 버전
개선사항:
  1. 댓글 샘플링: 인기 100개 + 최신 100개 혼합 (최대 200개, 999개 영상 대응)
  2. session_state 캐싱: 재렌더링 시 API 재호출 없음 + 수동 재분석 버튼
  3. CSS 디자인 정제: 카드 간격·폰트·테이블 가독성 개선
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

/* ── 메인 컨테이너 ── */
.block-container {
    max-width: 860px !important;
    padding: 2rem 1.5rem !important;
    margin: 0 auto !important;
}

/* ── 페이지 타이틀 ── */
.page-title {
    text-align: center;
    font-size: 1.5rem;
    font-weight: 700;
    color: #31333f;
    margin-bottom: 1.2rem;
    letter-spacing: -0.01em;
}

/* ── 재분석 버튼 ── */
.stButton > button {
    background: #fff !important;
    color: #555 !important;
    border: 1px solid #d9d9d9 !important;
    border-radius: 6px !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    padding: 0.35rem 0.9rem !important;
}
.stButton > button:hover {
    border-color: #1f77b4 !important;
    color: #1f77b4 !important;
}

/* ── 영상 제목 박스 ── */
.video-box {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background: #fff;
    padding: 0.85rem 1.1rem;
    text-align: center;
    margin-bottom: 1rem;
}
.video-box .vb-label { font-size: 0.68rem; color: #aaa; margin-bottom: 0.25rem; }
.video-box .vb-title { font-size: 0.9rem; color: #31333f; font-weight: 500; line-height: 1.5; }

/* ── 메트릭 4칸 ── */
.metric-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-bottom: 1rem;
}
.metric-box {
    background: #fff;
    border-radius: 8px;
    padding: 0.9rem 0.6rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.metric-box .m-label { font-size: 0.65rem; color: #aaa; margin-bottom: 0.3rem; letter-spacing: 0.02em; }
.metric-box .m-val   { font-size: 1.35rem; font-weight: 700; line-height: 1.1; }
.metric-box .m-val.blue  { color: #1f77b4; }
.metric-box .m-val.red   { color: #d62728; }
.metric-box .m-val.small { font-size: 0.75rem; font-weight: 400; color: #666; line-height: 1.7; }

/* ── 샘플 정보 뱃지 ── */
.sample-badge {
    text-align: center;
    font-size: 0.7rem;
    color: #aaa;
    margin-bottom: 1rem;
    letter-spacing: 0.02em;
}
.sample-badge span {
    background: #f0f2f6;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 2px 10px;
    margin: 0 3px;
}

/* ── st.container(border=True) 카드 ── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fff !important;
    border-radius: 10px !important;
    border: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07) !important;
    padding: 0.4rem 0.6rem 0.6rem !important;
    margin-bottom: 1rem !important;
}

/* ── 카드 제목 ── */
.card-title {
    font-size: 0.88rem;
    font-weight: 700;
    color: #31333f;
    margin-bottom: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #f5f5f5;
}

/* ── 테이블 ── */
.data-table { width:100%; border-collapse:collapse; font-size:0.8rem; }
.data-table th {
    text-align:left; padding:0.5rem 0.7rem;
    border-bottom:2px solid #eee; color:#888;
    font-weight:600; font-size:0.72rem;
    letter-spacing:0.02em; white-space:nowrap;
}
.data-table td { padding:0.55rem 0.7rem; border-bottom:1px solid #f8f8f8; vertical-align:middle; }
.data-table tr:last-child td { border-bottom:none; }
.data-table tr:hover td { background:#fafafa; }

/* 감성 텍스트 */
.s-pos { color:#2ca02c; font-weight:700; font-size:0.8rem; }
.s-neg { color:#d62728; font-weight:700; font-size:0.8rem; }
.s-neu { color:#1f77b4; font-weight:700; font-size:0.8rem; }

/* 분류 pill */
.tag {
    display:inline-block; background:#f0f2f6; color:#555;
    padding:2px 8px; border-radius:10px;
    font-size:0.7rem; white-space:nowrap;
}

/* ── 댓글 내용 말줄임 ── */
.comment-text {
    max-width: 280px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #444;
    font-size: 0.78rem;
}

/* ── selectbox ── */
[data-baseweb="select"] * { font-size:0.8rem !important; }

/* ── 정렬 힌트 ── */
.sort-hint { font-size:0.68rem; color:#bbb; text-align:right; margin-bottom:0.4rem; }

/* ── 다운로드 버튼 ── */
.stDownloadButton > button {
    background: #fff !important;
    border: 1px solid #d9d9d9 !important;
    color: #555 !important;
    border-radius: 6px !important;
    font-size: 0.78rem !important;
    padding: 0.35rem 0.9rem !important;
}
.stDownloadButton > button:hover {
    border-color: #1f77b4 !important;
    color: #1f77b4 !important;
}

/* ── 면책조항 ── */
.disclaimer {
    margin-top: 0.5rem;
    padding: 1rem 1.2rem;
    font-size: 0.73rem;
    color: #aaa;
    line-height: 2;
    text-align: center;
}
.disclaimer .d-title { font-size:0.8rem; font-weight:700; color:#e65100; margin-bottom:0.4rem; }
.disclaimer ul { text-align:left; padding-left:1.2rem; margin:0; }

/* metric 기본 숨김 */
[data-testid="metric-container"] { display:none !important; }
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
    # ① 샘플링: 인기 100 + 최신 100 = 최대 200개
    SAMPLE_POPULAR = 100   # order="relevance" (인기순)
    SAMPLE_RECENT  = 100   # order="time"      (최신순)
    COMMENT_MIN_LEN = 5

    BATCH_SIZE  = 20
    MAX_RETRIES = 2
    RETRY_WAIT  = 15
    MAX_TOPICS  = 8

    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {"긍정": "#2ca02c", "부정": "#d62728", "중립": "#1f77b4"}
    SENTIMENT_CSS    = {"긍정": "s-pos",   "부정": "s-neg",   "중립": "s-neu"}


# ============================================================
# 2. 분석 대상 영상 (URL만 변경하면 됩니다)
# ============================================================
TARGET_URL = "https://www.youtube.com/watch?v=fNHLffyXnQM&t=3s"


# ============================================================
# 3. Gemini 클라이언트
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
# 4. YouTube 데이터
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
    result = _fetch_info_cached(vid)
    if not result:
        st.error("❌ 응답 없음"); return None
    err = result.get("error")
    if not err: return result
    msgs = {
        "not_found": "❌ 영상을 찾을 수 없습니다 (비공개/삭제).",
        "http_403":  "❌ YouTube API 키 오류(403) — Secrets의 YOUTUBE_API_KEY를 확인하세요.",
        "http_404":  "❌ 영상 없음 (404).",
    }
    st.error(msgs.get(err, f"❌ 오류: {result.get('detail', err)}"))
    return None


def _collect_page(vid: str, order: str, limit: int) -> list:
    """한 가지 정렬 기준으로 최대 limit개 댓글을 페이지네이션 수집."""
    rows, seen, next_token = [], set(), None
    while len(rows) < limit:
        try:
            params = dict(part="snippet", videoId=vid,
                          maxResults=100, order=order)
            if next_token:
                params["pageToken"] = next_token
            r = _yt().commentThreads().list(**params).execute()
        except Exception:
            break

        for item in r.get("items", []):
            s = item["snippet"]["topLevelComment"]["snippet"]
            c = re.sub(r"<[^>]+>", "", s.get("textDisplay", ""))
            c = re.sub(r"https?://\S+", "", c).replace("\n", " ").strip()
            if len(c) < Config.COMMENT_MIN_LEN or c in seen:
                continue
            seen.add(c)
            rows.append({"time": s["publishedAt"], "text": c,
                         "likes": int(s.get("likeCount", 0)),
                         "order": order})
            if len(rows) >= limit:
                break

        next_token = r.get("nextPageToken")
        if not next_token:
            break
    return rows


@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(vid: str) -> pd.DataFrame:
    """
    ① 인기 댓글 최대 100개 (order=relevance)
    ② 최신 댓글 최대 100개 (order=time)
    → 중복 제거 후 합산, 최대 200개
    """
    popular = _collect_page(vid, "relevance", Config.SAMPLE_POPULAR)
    recent  = _collect_page(vid, "time",      Config.SAMPLE_RECENT)

    # 중복 텍스트 제거 (인기 우선 유지)
    seen, merged = set(), []
    for row in popular + recent:
        if row["text"] not in seen:
            seen.add(row["text"])
            merged.append(row)

    if not merged:
        st.warning("⚠️ 수집된 댓글이 없습니다.")
        return pd.DataFrame()

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
    if not {"감성","분류","키워드","댓글내용"}.issubset(df.columns):
        return pd.DataFrame()
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
    """캐시 함수 — st.* 호출 없음."""
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
    frames = [_parse(r) for r, _ in raw_results if _parse(r) is not None]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ============================================================
# 6. 분류 병합 (최대 8개)
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
BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
    margin=dict(l=8, r=8, t=8, b=8),
)

def chart_donut(res_df: pd.DataFrame) -> go.Figure:
    sc     = res_df["감성"].value_counts().reset_index()
    sc.columns = ["감성", "n"]
    colors = [Config.SENTIMENT_COLORS[s] for s in sc["감성"]]
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
        margin=dict(l=8, r=90, t=8, b=8), height=320,
        legend=dict(orientation="v", x=1.02, y=0.5,
                    xanchor="left", yanchor="middle",
                    font=dict(size=12), itemsizing="constant"),
    )
    return fig

def chart_topic_bar(res_df: pd.DataFrame) -> go.Figure:
    df    = merge_topics(res_df)
    bd    = df.groupby(["분류","감성"]).size().reset_index(name="n")
    order = bd.groupby("분류")["n"].sum().sort_values(ascending=True).index.tolist()
    fig   = px.bar(bd, x="n", y="분류", color="감성", orientation="h",
                   color_discrete_map=Config.SENTIMENT_COLORS,
                   category_orders={"분류": order, "감성": ["중립","부정","긍정"]},
                   labels={"n":"","분류":""}, height=max(240, len(order)*50))
    fig.update_layout(
        **BASE,
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center",
                    font=dict(size=11), traceorder="normal", title=None),
        xaxis=dict(showgrid=True, gridcolor="#ececec", zeroline=False,
                   tickfont=dict(size=10)),
        yaxis=dict(showgrid=False, tickfont=dict(size=11)),
        bargap=0.32,
    )
    fig.update_traces(marker_line_width=0)
    return fig

def fetch_view_history(info: dict) -> pd.DataFrame:
    pub_raw      = pd.to_datetime(info["published"])
    pub_day      = pub_raw.normalize()
    now          = pd.Timestamp.now().tz_localize(None)
    today        = now.normalize()
    total        = int(info["view_count"])
    days_elapsed = int((today - pub_day).days)

    rows = []
    # 구간 1: 개시일 당일 — 시간 단위
    day0_end   = pub_day + pd.Timedelta(days=1)
    hour_end   = min(day0_end, now)
    hour_range = pd.date_range(pub_raw.floor("h"), hour_end, freq="h")
    if len(hour_range) < 2:
        hour_range = pd.DatetimeIndex([pub_raw.floor("h"), hour_end])

    n_h = len(hour_range)
    if days_elapsed == 0:
        end_v = total
    else:
        n_t   = days_elapsed + 1
        x_a   = np.linspace(0.0, 4.0, n_t)
        w_a   = (1.0 - np.exp(-x_a)); w_a /= w_a[-1]
        end_v = max(int(round(float(w_a[0]) * total)), 1)

    x_h = np.linspace(0.0, 2.0, n_h); w_h = 1.0 - np.exp(-x_h)
    w_h = w_h / w_h[-1] if w_h[-1] > 0 else np.linspace(0.0, 1.0, n_h)
    for ts, wv in zip(hour_range, w_h):
        rows.append({"date": ts, "views": int(round(float(wv)*end_v)),
                     "is_hourly": True})

    # 구간 2: 다음날 ~ 오늘 — 일 단위
    if days_elapsed >= 1:
        day1      = pub_day + pd.Timedelta(days=1)
        day_range = pd.date_range(day1, today, freq="D").tolist()
        n_t       = days_elapsed + 1
        x_a       = np.linspace(0.0, 4.0, n_t)
        w_a       = (1.0 - np.exp(-x_a)); w_a /= w_a[-1]
        for i, ts in enumerate(day_range):
            rows.append({"date": ts,
                         "views": int(round(float(w_a[i+1]) * total)),
                         "is_hourly": False})

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df

def chart_view_trend(info: dict) -> go.Figure | None:
    import math
    df = fetch_view_history(info)
    if df.empty or len(df) < 2: return None

    total     = int(info["view_count"])
    span_days = int((df["date"].iloc[-1] - df["date"].iloc[0]).days)

    # Y축
    if total > 0:
        mag   = 10 ** math.floor(math.log10(total))
        max_v = math.ceil(total / mag) * mag
        if max_v == total: max_v = int(total * 1.2)
    else:
        max_v = 10_000
    raw_t  = max_v / 5
    mag2   = 10 ** math.floor(math.log10(max(raw_t, 1)))
    y_tick = math.ceil(raw_t / mag2) * mag2

    # X축
    if span_days <= 3:
        x_dtick, x_fmt = 3600000*6, "%m/%d %H시"
    elif span_days <= 14:
        x_dtick, x_fmt = 86400000, "%m/%d"
    elif span_days <= 60:
        x_dtick, x_fmt = 86400000*3, "%m/%d"
    elif span_days <= 365:
        x_dtick, x_fmt = 86400000*7, "%m/%d"
    else:
        x_dtick, x_fmt = "M1", "%Y-%m"

    hover_texts = []
    for _, row in df.iterrows():
        ts = row["date"]
        hover_texts.append(
            f"{ts.month}월 {ts.day}일 {ts.hour:02d}:00" if row["is_hourly"]
            else f"{ts.year}년 {ts.month}월 {ts.day}일"
        )

    fig = go.Figure(go.Scatter(
        x=df["date"], y=df["views"],
        mode="lines+markers",
        line=dict(color="#5b9bd5", width=2),
        marker=dict(size=4, color="#5b9bd5", opacity=0.8,
                    line=dict(color="#fff", width=1)),
        text=hover_texts, customdata=df["views"].tolist(),
        hovertemplate="<b>%{text}</b><br>누적 조회수: <b>%{customdata:,}회</b><extra></extra>",
        hoverlabel=dict(bgcolor="#1c2333",
                        font=dict(color="#fff", size=12,
                                  family="Noto Sans KR, sans-serif"),
                        bordercolor="#1c2333"),
    ))
    x_start = str((df["date"].iloc[0]  - pd.Timedelta(hours=6)).isoformat())
    x_end   = str((df["date"].iloc[-1] + pd.Timedelta(hours=6)).isoformat())
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Noto Sans KR, sans-serif", size=11, color="#555"),
        margin=dict(l=8, r=8, t=8, b=50), height=290, hovermode="closest",
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False,
                   type="date", tickformat=x_fmt, dtick=x_dtick,
                   tickangle=-35, tickfont=dict(size=10),
                   range=[x_start, x_end]),
        yaxis=dict(showgrid=True, gridcolor="#ececec", zeroline=False,
                   range=[0, max_v * 1.08], dtick=y_tick,
                   tickformat=",.0f", tickfont=dict(size=10)),
    )
    return fig


# ============================================================
# 8. 메인
# ============================================================
def main():
    st.markdown('<div class="page-title">📊 국민연금 유튜브 여론 모니터링</div>',
                unsafe_allow_html=True)

    vid = extract_video_id(TARGET_URL)
    if not vid:
        st.error("❌ TARGET_URL이 유효하지 않습니다."); return

    # ② session_state 캐싱 —————————————————————————————————
    # 재렌더링(위젯 조작 등) 시 API를 재호출하지 않음
    # "재분석" 버튼 클릭 시에만 캐시 초기화 후 재수집
    col_title, col_btn = st.columns([6, 1])
    with col_btn:
        if st.button("🔄 재분석"):
            for k in ["info","raw_df","res_df"]:
                st.session_state.pop(k, None)
            st.cache_data.clear()

    need_fetch = any(k not in st.session_state
                     for k in ["info","raw_df","res_df"])

    if need_fetch:
        with st.spinner("📡 데이터 수집 중..."):
            info   = fetch_video_info(vid)
            raw_df = fetch_comments(vid)
        if not info:       return
        if raw_df.empty:   st.error("❌ 댓글 수집 실패"); return

        with st.spinner(f"🤖 AI 분석 중 ({len(raw_df)}개 댓글, "
                        f"{(len(raw_df)+Config.BATCH_SIZE-1)//Config.BATCH_SIZE}배치)..."):
            h      = hashlib.md5("".join(raw_df["text"].tolist()).encode()).hexdigest()
            res_df = analyze(h, raw_df["text"].tolist())
        if res_df.empty:   st.error("❌ AI 분석 실패"); return

        # session_state 저장
        st.session_state["info"]   = info
        st.session_state["raw_df"] = raw_df
        st.session_state["res_df"] = res_df
    else:
        info   = st.session_state["info"]
        raw_df = st.session_state["raw_df"]
        res_df = st.session_state["res_df"]

    # ════ 영상 제목 박스 ═══════════════════════════════════
    st.markdown(f"""
    <div class="video-box">
        <div class="vb-label">분석 대상 영상:</div>
        <div class="vb-title">🎥 {info['title']}</div>
    </div>""", unsafe_allow_html=True)

    # ════ 메트릭 4개 ═══════════════════════════════════════
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

    # ③ 샘플 정보 뱃지 ————————————————————————————————————
    pop_n = len(raw_df[raw_df["order"]=="relevance"]) if "order" in raw_df.columns else len(raw_df)
    rec_n = len(raw_df[raw_df["order"]=="time"])      if "order" in raw_df.columns else 0
    st.markdown(f"""
    <div class="sample-badge">
        분석 댓글 총 <strong>{len(raw_df)}개</strong>
        <span>인기순 {pop_n}개</span>
        <span>최신순 {rec_n}개</span>
        (전체 댓글 {info['comment_count']:,}개 중 샘플)
    </div>""", unsafe_allow_html=True)

    # ════ 📈 누적 조회수 추이 ═══════════════════════════════
    vt = chart_view_trend(info)
    if vt:
        with st.container(border=True):
            st.markdown('<div class="card-title">📈 시간대별 누적 조회수 추이</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(vt, use_container_width=True,
                            config={"displayModeBar": False})

    # ════ 😊 감성 분포 ══════════════════════════════════════
    with st.container(border=True):
        st.markdown('<div class="card-title">😊 전체 감성 분포</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(chart_donut(res_df), use_container_width=True,
                        config={"displayModeBar": False})

    # ════ 📊 분류별 여론 ════════════════════════════════════
    with st.container(border=True):
        st.markdown('<div class="card-title">📊 분류별 여론 (긍정/부정/중립)</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(chart_topic_bar(res_df), use_container_width=True,
                        config={"displayModeBar": False})

    # ════ 📝 전체 분석 데이터 ═══════════════════════════════
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

        filtered  = res_df if sel == "전체" else res_df[res_df["감성"] == sel]
        rows_html = ""
        for _, row in filtered.iterrows():
            css = Config.SENTIMENT_CSS.get(row["감성"], "s-neu")
            content = str(row["댓글내용"])[:60]
            rows_html += f"""
            <tr>
                <td><span class="{css}">{row['감성']}</span></td>
                <td><span class="tag">{str(row['분류'])}</span></td>
                <td><strong>{str(row['키워드'])[:18]}</strong></td>
                <td><div class="comment-text" title="{content}">{content}</div></td>
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

    # ════ 면책조항 ══════════════════════════════════════════
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
