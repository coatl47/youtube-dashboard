"""
국민연금 이사장 유튜브 여론 모니터링
디자인: roy8in.github.io 모바일 스크린샷 1:1 재현
"""

import html
import json
import math
import re
import time
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google import genai
from google.genai import types as genai_types
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

KST = ZoneInfo("Asia/Seoul")


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
    overflow: hidden;
    word-break: break-word;
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
    font-size: 0.65rem;
    white-space: normal;
    word-break: keep-all;
    word-wrap: break-word;
    font-weight: 600;
    line-height: 1.5;
    max-width: 100%;
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
    AD_LABEL        = "광고/홍보"          # 프롬프트와 차트 필터가 공유하는 고정 라벨

    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {"긍정": "#2ca02c", "부정": "#d62728", "중립": "#9e9e9e"}
    SENTIMENT_CSS    = {"긍정": "s-pos",   "부정": "s-neg",   "중립": "s-neu"}


# ============================================================
# 2. 분석 대상 영상
# ============================================================
TARGET_URL = "https://www.youtube.com/watch?v=fNHLffyXnQM&t=3s"


# ============================================================
# 3. API 클라이언트
# ============================================================
@st.cache_resource(show_spinner=False)
def _gemini_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

@st.cache_resource(show_spinner=False)
def _yt():
    return build("youtube", "v3", developerKey=st.secrets["YOUTUBE_API_KEY"])

def _is_quota(e) -> bool:
    return any(k in str(e).lower()
               for k in ["429", "resource_exhausted", "quota", "rate limit"])

def _is_unavailable(e) -> bool:
    return any(k in str(e).lower()
               for k in ["not found", "404", "does not exist", "unsupported"])


# ============================================================
# 4. YouTube 수집
# ============================================================
def extract_video_id(url: str) -> str | None:
    for pat in [r"(?:v=)([0-9A-Za-z_-]{11})",
                r"(?:youtu\.be/)([0-9A-Za-z_-]{11})",
                r"(?:embed/)([0-9A-Za-z_-]{11})",
                r"(?:shorts/)([0-9A-Za-z_-]{11})"]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None

@st.cache_data(ttl=600, show_spinner=False)
def _fetch_info_cached(vid: str) -> dict:
    try:
        r = _yt().videos().list(part="snippet,statistics", id=vid).execute()
        if not r.get("items"):
            return {"error": "not_found"}
        item = r["items"][0]
        s = item["statistics"]
        return {
            "title":         item["snippet"]["title"],
            "channel":       item["snippet"]["channelTitle"],
            "published":     item["snippet"]["publishedAt"],   # ISO-8601 UTC
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
    err = result.get("error")
    if not err:
        return result
    msgs = {
        "not_found": "❌ 영상을 찾을 수 없습니다 (비공개/삭제).",
        "http_403":  "❌ YouTube API 키 오류 또는 할당량 초과 (403).",
        "http_404":  "❌ 영상을 찾을 수 없습니다 (404).",
    }
    st.error(msgs.get(err, f"❌ 오류: {result.get('detail', err)}"))
    return None

def _clean_comment(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", " ", text).strip()

def _collect_page(vid: str, order: str, limit: int) -> tuple[list, str | None]:
    rows, seen, next_token = [], set(), None
    while len(rows) < limit:
        try:
            params = dict(part="snippet", videoId=vid, maxResults=100,
                          order=order, textFormat="plainText")
            if next_token:
                params["pageToken"] = next_token
            r = _yt().commentThreads().list(**params).execute()
        except HttpError as e:
            if "commentsDisabled" in str(e):
                return rows, "댓글 사용이 중지된 영상입니다."
            return rows, f"YouTube API 오류 ({e.resp.status})"
        except Exception as e:
            return rows, f"{type(e).__name__}: {e}"
        for item in r.get("items", []):
            s = item["snippet"]["topLevelComment"]["snippet"]
            c = _clean_comment(s.get("textDisplay", ""))
            if len(c) < Config.COMMENT_MIN_LEN or c in seen:
                continue
            seen.add(c)
            rows.append({"time": s["publishedAt"], "text": c,
                         "likes": int(s.get("likeCount", 0)), "order": order})
            if len(rows) >= limit:
                break
        next_token = r.get("nextPageToken")
        if not next_token:
            break
    return rows, None

@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(vid: str) -> tuple[pd.DataFrame, str | None]:
    popular, err1 = _collect_page(vid, "relevance", Config.SAMPLE_POPULAR)
    recent,  err2 = _collect_page(vid, "time",      Config.SAMPLE_RECENT)
    seen, merged = set(), []
    for row in popular + recent:
        if row["text"] not in seen:
            seen.add(row["text"])
            merged.append(row)
    if not merged:
        return pd.DataFrame(), err1 or err2
    df = pd.DataFrame(merged)
    df["time"] = pd.to_datetime(df["time"])
    return df, None


# ============================================================
# 5. AI 분석 (JSON 구조화 출력 + 원문 인덱스 조인)
# ============================================================
def _build_prompt(texts: list[str]) -> str:
    labels = ", ".join(f'"{s}"' for s in Config.SENTIMENT_LABELS)
    lines = "\n".join(f"{i + 1}. {t[:200]}" for i, t in enumerate(texts))
    return (
        "유튜브 댓글 여론 분석 작업입니다. 아래 번호가 매겨진 댓글을 분석해 "
        "JSON 배열만 출력하세요. JSON 외 다른 텍스트는 금지합니다.\n\n"
        '각 댓글마다 객체 하나: {"i": 댓글번호(정수), "s": 감성, "c": 분류, "k": 키워드}\n'
        f"- s: {labels} 중 하나\n"
        "- c: 댓글 주제를 나타내는 2~8자 한국어 명사구 (예: 연금개혁, 기금운용, 인물평가). "
        f'광고·홍보·도배성 댓글은 반드시 "{Config.AD_LABEL}"으로 분류\n'
        "- k: 핵심 키워드 1개 (한국어, 10자 이내)\n"
        f"1번부터 {len(texts)}번까지 모든 댓글을 빠짐없이 분석하세요.\n\n"
        f"[댓글 목록]\n{lines}"
    )

def _parse_batch(raw: str, texts: list[str]) -> list[dict]:
    """모델 응답(JSON 배열)을 파싱해 원문 댓글과 인덱스로 조인한다."""
    raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            idx = int(it.get("i")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= idx < len(texts):
            continue
        s = str(it.get("s", "")).strip()
        rows.append({
            "감성":   s if s in Config.SENTIMENT_LABELS else "중립",
            "분류":   str(it.get("c", "")).strip() or "기타",
            "키워드": str(it.get("k", "")).strip(),
            "댓글내용": texts[idx],
        })
    return rows

def _call_api(prompt: str) -> tuple[str | None, str | None]:
    """모델 우선순위에 따라 호출. 반환: (응답 텍스트, 오류 메시지)."""
    client, last_err = _gemini_client(), "호출 실패"
    cfg = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
    )
    for model in Config.GEMINI_MODEL_PRIORITY:
        for attempt in range(Config.MAX_RETRIES):
            try:
                r = client.models.generate_content(
                    model=model, contents=prompt, config=cfg)
                if r.text:
                    return r.text, None
                last_err = f"[{model}] 빈 응답"
                break
            except Exception as e:
                last_err = f"[{model}] {e}"
                if _is_quota(e) or _is_unavailable(e):
                    break   # 다음 모델로 폴백
                if attempt < Config.MAX_RETRIES - 1:
                    time.sleep(Config.RETRY_WAIT)
    return None, last_err

@st.cache_data(ttl=86400, show_spinner=False)
def analyze_comments(cache_key: str, _texts: tuple[str, ...]) -> tuple[pd.DataFrame, list[str]]:
    """cache_key(댓글 해시)로만 캐싱하고 _texts는 해싱에서 제외한다."""
    texts = list(_texts)
    batches = [texts[i:i + Config.BATCH_SIZE]
               for i in range(0, len(texts), Config.BATCH_SIZE)]
    rows, errors = [], []
    for idx, batch in enumerate(batches):
        raw, err = _call_api(_build_prompt(batch))
        if raw is None:
            errors.append(f"배치 {idx + 1}/{len(batches)}: {err}")
            continue
        parsed = _parse_batch(raw, batch)
        if not parsed:
            errors.append(f"배치 {idx + 1}/{len(batches)}: 응답 파싱 실패")
        rows.extend(parsed)
        if idx < len(batches) - 1:
            time.sleep(1)
    if not rows:
        return pd.DataFrame(), errors
    df = (pd.DataFrame(rows)
          .drop_duplicates(subset="댓글내용")
          .reset_index(drop=True))
    return df, errors


# ============================================================
# 6. 분류 병합
# ============================================================
def merge_topics(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["분류"].value_counts()
    if len(counts) <= Config.MAX_TOPICS:
        return df.copy()
    top = set(counts.iloc[:Config.MAX_TOPICS - 1].index)
    out = df.copy()
    out["분류"] = out["분류"].where(out["분류"].isin(top), "기타")
    return out


# ============================================================
# 7. 차트
# ============================================================
def chart_donut(res_df: pd.DataFrame) -> go.Figure | None:
    df = res_df[res_df["분류"] != Config.AD_LABEL]
    if df.empty:
        df = res_df
    if df.empty:
        return None
    sc = (df["감성"].value_counts()
          .reindex(Config.SENTIMENT_LABELS)
          .dropna()
          .astype(int))
    colors = [Config.SENTIMENT_COLORS.get(s, "#ccc") for s in sc.index]
    fig = go.Figure(go.Pie(
        labels=sc.index.tolist(), values=sc.values.tolist(), hole=0.50,
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

def chart_topic_bar(res_df: pd.DataFrame) -> go.Figure | None:
    if res_df.empty:
        return None
    df    = merge_topics(res_df)
    bd    = df.groupby(["분류", "감성"]).size().reset_index(name="n")
    order = bd.groupby("분류")["n"].sum().sort_values(ascending=True).index.tolist()
    fig   = px.bar(bd, x="n", y="분류", color="감성", orientation="h",
                   color_discrete_map=Config.SENTIMENT_COLORS,
                   category_orders={"분류": order, "감성": ["중립", "부정", "긍정"]},
                   labels={"n": "", "분류": ""},
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

def build_view_curve(info: dict) -> pd.DataFrame:
    """게재 시점~현재의 누적 조회수 추정 곡선.

    YouTube Data API는 조회수 이력을 제공하지 않으므로 현재 총 조회수를
    지수 포화 곡선(1-e^-kf)으로 배분한 '추정치'다. 실측 데이터가 아니다.
    """
    pub   = pd.to_datetime(info["published"], utc=True).tz_convert(KST).tz_localize(None)
    now   = pd.Timestamp.now(tz=KST).tz_localize(None)
    total = int(info["view_count"])
    if total <= 0 or now <= pub:
        return pd.DataFrame()

    day1 = pub.normalize() + pd.Timedelta(days=1)   # 게재 다음날 0시
    stamps = list(pd.date_range(pub.floor("h"), min(day1, now), freq="h"))
    if now > day1:
        stamps += list(pd.date_range(day1 + pd.Timedelta(days=1),
                                     now.normalize(), freq="D"))
    stamps.append(now)
    stamps = sorted(set(stamps))

    span  = (now - pub).total_seconds()
    k     = 4.0
    denom = 1.0 - math.exp(-k)
    rows = []
    for ts in stamps:
        f = min(max((ts - pub).total_seconds() / span, 0.0), 1.0)
        views = int(round(total * (1.0 - math.exp(-k * f)) / denom))
        rows.append({"date": ts, "views": views, "is_hourly": ts < day1})
    return pd.DataFrame(rows)

def chart_view_trend(info: dict) -> go.Figure | None:
    df = build_view_curve(info)
    if len(df) < 2:
        return None
    total     = int(info["view_count"])
    span_days = int((df["date"].iloc[-1] - df["date"].iloc[0]).days)

    mag   = 10 ** math.floor(math.log10(total))
    max_v = math.ceil(total / mag) * mag
    if max_v == total:
        max_v = int(total * 1.2)
    raw_t  = max_v / 5
    mag2   = 10 ** math.floor(math.log10(max(raw_t, 1)))
    y_tick = math.ceil(raw_t / mag2) * mag2

    if span_days <= 3:     x_dtick, x_fmt = 3600000 * 6,  "%m/%d %H시"
    elif span_days <= 14:  x_dtick, x_fmt = 86400000,     "%m/%d"
    elif span_days <= 60:  x_dtick, x_fmt = 86400000 * 3, "%m/%d"
    elif span_days <= 365: x_dtick, x_fmt = 86400000 * 7, "%m/%d"
    else:                  x_dtick, x_fmt = "M1",         "%Y-%m"

    hover_texts = [
        f"{ts.month}월 {ts.day}일 {ts.hour:02d}:00" if hourly
        else f"{ts.year}년 {ts.month}월 {ts.day}일"
        for ts, hourly in zip(df["date"], df["is_hourly"])
    ]
    fig = go.Figure(go.Scatter(
        x=df["date"], y=df["views"], mode="lines",
        line=dict(color="#1f77b4", width=2.5),
        text=hover_texts, customdata=df["views"].tolist(),
        hovertemplate="<b>%{text}</b><br>누적 조회수(추정): <b>%{customdata:,}회</b><extra></extra>",
        hoverlabel=dict(bgcolor="#1c2333",
                        font=dict(color="#fff", size=12), bordercolor="#1c2333"),
    ))
    x_start = (df["date"].iloc[0]  - pd.Timedelta(hours=6)).isoformat()
    x_end   = (df["date"].iloc[-1] + pd.Timedelta(hours=6)).isoformat()
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
        topic   = html.escape(str(row["분류"]))
        keyword = html.escape(str(row["키워드"])[:14])
        content = html.escape(str(row["댓글내용"]))
        rows_html += f"""
        <tr>
          <td style="width:52px"><span class="{css}">{row['감성']}</span></td>
          <td style="width:72px"><span class="tag">{topic}</span></td>
          <td style="width:72px"><strong style="font-size:0.72rem">{keyword}</strong></td>
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
        <th style="width:52px">감성</th>
        <th style="width:72px">분류</th>
        <th style="width:72px">키워드</th>
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
def load_data(vid: str) -> bool:
    """수집 + 분석 결과를 session_state에 채운다. 성공 시 True."""
    if all(k in st.session_state for k in ("info", "res_df")):
        return True

    with st.spinner("📡 데이터 수집 중..."):
        info = fetch_video_info(vid)
        if not info:
            return False
        raw_df, err = fetch_comments(vid)
    if raw_df.empty:
        st.error(f"❌ 댓글 수집 실패: {err or '수집된 댓글이 없습니다.'}")
        return False

    texts   = tuple(raw_df["text"])
    h       = hashlib.md5("\x1f".join(texts).encode()).hexdigest()
    n_batch = -(-len(texts) // Config.BATCH_SIZE)
    with st.spinner(f"🤖 AI 분석 중 ({len(texts)}개 댓글, {n_batch}배치)..."):
        res_df, errors = analyze_comments(h, texts)

    if errors:
        with st.expander("⚠️ 분석 오류 상세", expanded=False):
            for e in errors:
                st.code(e)
    if res_df.empty:
        st.error("❌ AI 분석에 실패했습니다. 잠시 후 재분석해 주세요.")
        return False

    st.session_state["info"]   = info
    st.session_state["raw_df"] = raw_df
    st.session_state["res_df"] = res_df
    return True


def main():
    vid = extract_video_id(TARGET_URL)
    if not vid:
        st.error("❌ TARGET_URL이 유효하지 않습니다.")
        return

    # ── 상단 다크 헤더 ─────────────────────────────────────
    st.markdown('<div class="top-header">국민연금 이사장 유튜브 여론 모니터링</div>',
                unsafe_allow_html=True)

    # ── 재분석 버튼 ────────────────────────────────────────
    _, col_btn = st.columns([4, 1])
    with col_btn:
        if st.button("🔄 재분석"):
            for k in ("info", "raw_df", "res_df"):
                st.session_state.pop(k, None)
            st.cache_data.clear()

    if not load_data(vid):
        return
    info   = st.session_state["info"]
    res_df = st.session_state["res_df"]

    # ── 영상 정보 카드 ─────────────────────────────────────
    pub_dt  = pd.to_datetime(info["published"], utc=True).tz_convert(KST)
    pub_str = pub_dt.strftime("%Y-%m-%d %H:%M:%S")
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"""
    <div class="video-card">
        <div class="vc-channel">{html.escape(info['channel'])} · {pub_dt.strftime('%Y%m%d')}</div>
        <div class="vc-title">{html.escape(info['title'])}</div>
        <div class="vc-meta">
            영상 게재 시점 &nbsp;<span>{pub_str}</span><br>
            최종 업데이트 &nbsp;<span>{now_str}</span><br>
            링크 &nbsp;<a class="vc-link" href="{TARGET_URL}" target="_blank">유튜브 영상 열기</a>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── 메트릭 2×2 ─────────────────────────────────────────
    analyzed_n = int((res_df["분류"] != Config.AD_LABEL).sum())
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
            <div class="mc-value">{analyzed_n:,}</div>
            <div class="mc-sub">광고 제외 기준</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── 시간대별 누적 조회수 추이 (추정) ────────────────────
    vt = chart_view_trend(info)
    if vt:
        st.markdown('<div class="section-card">'
                    '<div class="section-title">시간대별 누적 조회수 추이</div>'
                    '<div class="section-sub">현재 총 조회수를 기반으로 한 추정 곡선입니다 (실측 이력 아님).</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(vt, width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ── 전체 감성 분포 ──────────────────────────────────────
    donut = chart_donut(res_df)
    if donut:
        st.markdown('<div class="section-card">'
                    '<div class="section-title">전체 감성 분포</div>'
                    '<div class="section-sub">광고성 댓글을 제외한 감성 분포를 보여줍니다.</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(donut, width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ── 분류별 여론 ────────────────────────────────────────
    topic_bar = chart_topic_bar(res_df)
    if topic_bar:
        st.markdown('<div class="section-card">'
                    '<div class="section-title">분류별 여론</div>'
                    '<div class="section-sub">주요 분류별 댓글 반응을 감성 기준으로 나누어 보여줍니다.</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(topic_bar, width="stretch", config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ── 전체 분석 데이터 (고정 헤더 + 스크롤) ──────────────
    with st.container(border=True):
        col_f, col_dl = st.columns([2, 1])
        with col_f:
            sel = st.selectbox("감성 필터", ["전체"] + Config.SENTIMENT_LABELS,
                               label_visibility="collapsed")
        filtered = res_df if sel == "전체" else res_df[res_df["감성"] == sel]
        with col_dl:
            st.download_button(
                "⬇️ CSV",
                filtered.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"analysis_{vid}_{datetime.now(KST).strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )
        render_table(filtered, len(filtered))

    # ── 면책조항 ───────────────────────────────────────────
    st.markdown("""
    <div class="disclaimer">
        <div class="d-title">면책조항</div>
        <ul>
            <li>본 대시보드의 수치는 유튜브 API 수집 시점 기준이며, 실제 서비스 화면과 차이가 있을 수 있습니다.</li>
            <li>조회수 추이 그래프는 현재 총 조회수 기반 추정 곡선으로, 실제 시간대별 이력과 다릅니다.</li>
            <li>댓글 감성 및 주제 분류 결과는 AI 자동 분석 결과로, 실제 작성자의 의도와 다를 수 있습니다.</li>
            <li>분석 결과는 참고용이며, 정책 판단이나 대외 커뮤니케이션에는 추가 검토가 필요합니다.</li>
        </ul>
    </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
