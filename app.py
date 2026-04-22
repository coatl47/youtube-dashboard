"""
유튜브 여론 분석 대시보드
디자인: 스크린샷 roy8in.github.io 1:1 재현
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
# 0. 페이지 설정 + CSS
# ============================================================
st.set_page_config(
    page_title="국민연금 유튜브 여론 모니터링",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

/* 전체 기본 */
html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif !important;
    background-color: #f0f2f6 !important;
    color: #31333f;
}
.stApp { background-color: #f0f2f6 !important; }

/* 상단 헤더 숨김 */
[data-testid="stHeader"] { display: none; }
footer { display: none; }
[data-testid="stToolbar"] { display: none; }

/* 메인 패딩 */
.block-container {
    padding: 2rem 2rem 2rem 2rem !important;
    max-width: 900px !important;
}

/* ── 카드 공통 ── */
.card {
    background: #ffffff;
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1.2rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
}

/* ── 페이지 타이틀 ── */
.page-title {
    text-align: center;
    font-size: 1.45rem;
    font-weight: 700;
    color: #31333f;
    margin-bottom: 0.8rem;
}

/* ── 영상 제목 박스 ── */
.video-box {
    background: #fff;
    border-radius: 8px;
    border: 1px solid #e8eaed;
    padding: 0.85rem 1.1rem;
    margin-bottom: 1.2rem;
    text-align: center;
}
.video-box .vb-label {
    font-size: 0.72rem;
    color: #888;
    margin-bottom: 0.3rem;
}
.video-box .vb-icon { font-size: 1rem; margin-right: 0.3rem; }
.video-box .vb-title {
    font-size: 0.92rem;
    font-weight: 500;
    color: #31333f;
    line-height: 1.5;
}

/* ── 메트릭 4칸 ── */
.metric-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    background: #fff;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    margin-bottom: 1.2rem;
}
.metric-cell {
    padding: 1rem 0.8rem;
    text-align: center;
    border-right: 1px solid #f0f2f6;
}
.metric-cell:last-child { border-right: none; }
.metric-cell .m-label {
    font-size: 0.72rem;
    color: #888;
    margin-bottom: 0.35rem;
}
.metric-cell .m-value {
    font-size: 1.45rem;
    font-weight: 700;
    line-height: 1.2;
}
.metric-cell .m-value.blue  { color: #1f77b4; }
.metric-cell .m-value.red   { color: #d62728; }
.metric-cell .m-value.small {
    font-size: 0.82rem;
    font-weight: 500;
    color: #555;
    line-height: 1.6;
}

/* ── 카드 제목 ── */
.card-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #31333f;
    margin-bottom: 0.8rem;
}

/* ── 테이블 스타일 ── */
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
}
.data-table th {
    text-align: left;
    padding: 0.5rem 0.6rem;
    border-bottom: 2px solid #e8eaed;
    color: #555;
    font-weight: 500;
    cursor: pointer;
}
.data-table td {
    padding: 0.55rem 0.6rem;
    border-bottom: 1px solid #f5f5f5;
    vertical-align: top;
}
.data-table tr:last-child td { border-bottom: none; }

/* 감성 배지 */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 700;
}
.badge-pos { background: #e8f5e9; color: #2e7d32; }
.badge-neg { background: #ffebee; color: #c62828; }
.badge-neu { background: #e3f2fd; color: #1565c0; }

/* 분류 태그 */
.tag {
    display: inline-block;
    background: #f0f2f6;
    color: #555;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.72rem;
}

/* ── 면책조항 ── */
.disclaimer {
    background: #fff8e1;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin-top: 1rem;
    font-size: 0.78rem;
    color: #555;
    line-height: 1.9;
}
.disclaimer .d-title {
    font-weight: 700;
    font-size: 0.85rem;
    color: #e65100;
    margin-bottom: 0.4rem;
}

/* ── URL 입력창 ── */
.stTextInput input {
    border-radius: 8px !important;
    border: 1px solid #dde !important;
    font-size: 0.9rem !important;
    padding: 0.5rem 0.8rem !important;
}
.stTextInput input:focus {
    border-color: #1f77b4 !important;
    box-shadow: 0 0 0 2px rgba(31,119,180,0.15) !important;
}
.stButton button {
    background: #1f77b4 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-size: 0.88rem !important;
    font-weight: 700 !important;
    padding: 0.5rem 1.5rem !important;
}
.stButton button:hover { background: #155f8a !important; }

/* Streamlit 기본 metric 숨김 (커스텀 HTML 사용) */
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
    COMMENT_LIMIT   = 40
    COMMENT_MIN_LEN = 5
    BATCH_SIZE      = 20
    MAX_RETRIES     = 2
    RETRY_WAIT      = 15

    SENTIMENT_LABELS = ["긍정", "부정", "중립"]
    SENTIMENT_COLORS = {"긍정": "#2ca02c", "부정": "#d62728", "중립": "#1f77b4"}


# ============================================================
# 2. Gemini
# ============================================================
@st.cache_resource(show_spinner=False)
def _gemini_client():
    return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def _is_quota_error(e):
    return any(k.lower() in str(e).lower() for k in ["429","RESOURCE_EXHAUSTED","quota","rate limit"])

def _is_not_found(e):
    return any(k in str(e).lower() for k in ["not found","404","does not exist","unsupported"])


# ============================================================
# 3. YouTube
# ============================================================
@st.cache_resource
def _yt():
    return build("youtube", "v3", developerKey=st.secrets["YOUTUBE_API_KEY"])

def extract_video_id(url):
    for pat in [r"(?:v=)([0-9A-Za-z_-]{11})",
                r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
                r"(?:embed\/)([0-9A-Za-z_-]{11})",
                r"(?:shorts\/)([0-9A-Za-z_-]{11})"]:
        m = re.search(pat, url)
        if m: return m.group(1)
    return None

@st.cache_data(ttl=600, show_spinner=False)
def fetch_video_info(vid):
    try:
        r = _yt().videos().list(part="snippet,statistics", id=vid).execute()
        if not r.get("items"): return None
        item = r["items"][0]; s = item["statistics"]
        return {
            "title":   item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "published": item["snippet"]["publishedAt"][:10],
            "view_count":    int(s.get("viewCount",    0)),
            "like_count":    int(s.get("likeCount",    0)),
            "comment_count": int(s.get("commentCount", 0)),
        }
    except: return None

@st.cache_data(ttl=600, show_spinner=False)
def fetch_comments(vid, limit=Config.COMMENT_LIMIT):
    try:
        r = _yt().commentThreads().list(
            part="snippet", videoId=vid,
            maxResults=min(limit*2, 100), order="relevance",
        ).execute()
    except: return pd.DataFrame()

    rows, seen = [], set()
    for item in r.get("items", []):
        s = item["snippet"]["topLevelComment"]["snippet"]
        c = re.sub(r"<[^>]+>","", s.get("textDisplay",""))
        c = re.sub(r"https?://\S+","", c).replace("\n"," ").strip()
        if len(c) < Config.COMMENT_MIN_LEN or c in seen: continue
        seen.add(c)
        rows.append({"time": s["publishedAt"], "text": c,
                     "likes": int(s.get("likeCount", 0))})
        if len(rows) >= limit: break

    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df

@st.cache_data(ttl=600, show_spinner=False)
def fetch_view_history(vid):
    """영상 공개일 기준 누적 조회수 시뮬레이션 (실제 API는 Analytics 필요)"""
    info = fetch_video_info(vid)
    if not info: return pd.DataFrame()
    pub  = pd.to_datetime(info["published"])
    now  = pd.Timestamp.now(tz="UTC").tz_localize(None)
    days = max((now - pub).days, 1)
    dates = pd.date_range(pub, now, periods=min(days, 60))
    total = info["view_count"]
    # 지수적 증가 패턴 모사
    import numpy as np
    x = np.linspace(0, 3, len(dates))
    w = 1 - np.exp(-x)
    w = w / w[-1] * total
    return pd.DataFrame({"date": dates, "views": w.astype(int)})


# ============================================================
# 4. AI
# ============================================================
def _prompt(texts):
    labels = "/".join(Config.SENTIMENT_LABELS)
    lines  = "\n".join(f"{i+1}. {t[:120]}" for i,t in enumerate(texts))
    return (f"다음 댓글을 분석해 CSV로 출력하세요.\n"
            f"헤더: 감성|분류|키워드|댓글내용\n"
            f"규칙: 감성={labels} 중 하나만. 영어 금지. CSV만 출력.\n\n{lines}")

def _parse(text):
    text  = re.sub(r"```[a-z]*","",text).replace("```","").strip()
    match = re.search(r"감성\s*\|\s*분류", text)
    if not match: return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(text[match.start():]),
                         sep="|", on_bad_lines="skip", engine="python", dtype=str)
    except: return pd.DataFrame()
    df.columns = [c.strip() for c in df.columns]
    needed = {"감성","분류","키워드","댓글내용"}
    if not needed.issubset(df.columns): return pd.DataFrame()
    df = df[list(needed)].copy().dropna(subset=["감성","분류"])
    df["감성"] = df["감성"].str.strip()
    df.loc[~df["감성"].isin(set(Config.SENTIMENT_LABELS)), "감성"] = "중립"
    return df[df["댓글내용"].str.strip().str.len()>0].reset_index(drop=True)

def _call(prompt):
    client, last = _gemini_client(), "실패"
    for m in Config.GEMINI_MODEL_PRIORITY:
        for attempt in range(Config.MAX_RETRIES):
            try:
                r = client.models.generate_content(model=m, contents=prompt)
                return r.text, m, None
            except Exception as e:
                last = f"[{m}] {e}"
                if _is_quota_error(e) or _is_not_found(e): break
                if attempt < Config.MAX_RETRIES-1: time.sleep(Config.RETRY_WAIT)
    return None, None, last

@st.cache_data(ttl=86400, show_spinner=False)
def _run_batches(h, texts):
    batches = [texts[i:i+Config.BATCH_SIZE] for i in range(0,len(texts),Config.BATCH_SIZE)]
    results, errors = [], []
    for idx, batch in enumerate(batches):
        raw, model, err = _call(_prompt(batch))
        if raw:
            results.append((raw, model))
            if idx < len(batches)-1: time.sleep(1)
        else:
            errors.append(f"배치 {idx+1}: {err}")
    return results, errors

def analyze(h, texts):
    raw_results, errors = _run_batches(h, texts)
    if errors:
        with st.expander("⚠️ 오류 상세", expanded=False):
            for e in errors: st.code(e)
    frames = [_parse(r) for r,_ in raw_results]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ============================================================
# 5. 차트
# ============================================================
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Noto Sans KR, sans-serif", size=12, color="#31333f"),
    margin=dict(l=10, r=10, t=10, b=10),
)

def make_donut(res_df):
    sc = res_df["감성"].value_counts().reset_index()
    sc.columns = ["감성","n"]
    colors = [Config.SENTIMENT_COLORS.get(s,"#aaa") for s in sc["감성"]]
    fig = go.Figure(go.Pie(
        labels=sc["감성"], values=sc["n"], hole=0.55,
        marker=dict(colors=colors, line=dict(color="#fff", width=2)),
        textinfo="percent",
        textfont=dict(size=13, family="Noto Sans KR, sans-serif"),
        hovertemplate="%{label}: %{value}개 (%{percent})<extra></extra>",
    ))
    fig.update_layout(**CHART_LAYOUT, height=320,
                      legend=dict(orientation="v", x=1.02, y=0.5,
                                  font=dict(size=12)))
    return fig

def make_trend(raw_df):
    trend = raw_df.set_index("time").resample("h").size().reset_index(name="n")
    fig = go.Figure(go.Scatter(
        x=trend["time"], y=trend["n"],
        mode="lines", line=dict(color="#5b9bd5", width=2),
        fill="tozeroy", fillcolor="rgba(91,155,213,0.1)",
        hovertemplate="%{x|%m/%d %H시}: %{y}개<extra></extra>",
    ))
    fig.update_layout(**CHART_LAYOUT, height=260,
                      xaxis=dict(showgrid=False, zeroline=False),
                      yaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False))
    return fig

def make_view_trend(vid):
    df = fetch_view_history(vid)
    if df.empty: return None
    fig = go.Figure(go.Scatter(
        x=df["date"], y=df["views"],
        mode="lines", line=dict(color="#5b9bd5", width=2),
        fill="tozeroy", fillcolor="rgba(91,155,213,0.08)",
        hovertemplate="%{x|%Y-%m-%d}: %{y:,}회<extra></extra>",
    ))
    fig.update_layout(**CHART_LAYOUT, height=260,
                      xaxis=dict(showgrid=False, zeroline=False,
                                 tickformat="%b %d\n%Y"),
                      yaxis=dict(showgrid=True, gridcolor="#f0f0f0",
                                 zeroline=False, tickformat=","))
    return fig

def make_topic_bar(res_df):
    bd    = res_df.groupby(["분류","감성"]).size().reset_index(name="n")
    order = bd.groupby("분류")["n"].sum().sort_values(ascending=True).index.tolist()
    fig   = px.bar(bd, x="n", y="분류", color="감성", orientation="h",
                   color_discrete_map=Config.SENTIMENT_COLORS,
                   category_orders={"분류": order},
                   labels={"n":"","분류":""},
                   height=max(220, len(order)*52))
    fig.update_layout(
        **CHART_LAYOUT,
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center",
                    font=dict(size=11)),
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False),
        yaxis=dict(showgrid=False),
        bargap=0.35,
    )
    fig.update_traces(marker_line_width=0)
    return fig


# ============================================================
# 6. 메인
# ============================================================
def main():
    # ── 제목 ─────────────────────────────────────────────────
    st.markdown('<div class="page-title">📊 유튜브 여론 분석 대시보드</div>',
                unsafe_allow_html=True)

    # ── URL 입력 ──────────────────────────────────────────────
    col_in, col_btn = st.columns([5, 1])
    with col_in:
        url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...",
                            label_visibility="collapsed")
    with col_btn:
        run = st.button("분석", use_container_width=True)

    if not (run and url):
        st.markdown("""
        <div class="card" style="text-align:center; padding:3rem; color:#999;">
            <div style="font-size:2.5rem; margin-bottom:0.8rem;">🔍</div>
            <div style="font-size:0.95rem;">분석할 유튜브 영상 URL을 입력하고 분석 버튼을 누르세요.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── 데이터 수집 ───────────────────────────────────────────
    video_id = extract_video_id(url)
    if not video_id:
        st.error("❌ 유효하지 않은 URL입니다.")
        return

    with st.spinner("데이터 수집 중..."):
        info   = fetch_video_info(video_id)
        raw_df = fetch_comments(video_id)

    if not info:
        st.error("❌ 영상 정보를 가져올 수 없습니다.")
        return
    if raw_df.empty:
        st.error("❌ 댓글을 수집할 수 없습니다.")
        return

    # ── AI 분석 ──────────────────────────────────────────────
    with st.spinner("AI 분석 중..."):
        h      = hashlib.md5("".join(raw_df["text"].tolist()).encode()).hexdigest()
        res_df = analyze(h, raw_df["text"].tolist())

    if res_df.empty:
        st.error("❌ AI 분석에 실패했습니다.")
        return

    # ════════════════════════════════════════════════════════
    # 영상 제목 박스
    # ════════════════════════════════════════════════════════
    st.markdown(f"""
    <div class="video-box">
        <div class="vb-label">분석 대상 영상:</div>
        <div><span class="vb-icon">🎬</span>
        <span class="vb-title">{info['title']}</span></div>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    # 메트릭 4개
    # ════════════════════════════════════════════════════════
    now_str = datetime.now().strftime("%Y-%m-%d\n%H:%M:%S")
    st.markdown(f"""
    <div class="metric-grid">
        <div class="metric-cell">
            <div class="m-label">총 조회수</div>
            <div class="m-value blue">{info['view_count']:,}</div>
        </div>
        <div class="metric-cell">
            <div class="m-label">좋아요</div>
            <div class="m-value red">{info['like_count']:,}</div>
        </div>
        <div class="metric-cell">
            <div class="m-label">댓글 수</div>
            <div class="m-value blue">{info['comment_count']:,}</div>
        </div>
        <div class="metric-cell">
            <div class="m-label">최종 업데이트</div>
            <div class="m-value small">{now_str}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    # 시간대별 누적 조회수 추이
    # ════════════════════════════════════════════════════════
    vt_fig = make_view_trend(video_id)
    if vt_fig:
        st.markdown('<div class="card"><div class="card-title">📈 시간대별 누적 조회수 추이</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(vt_fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    # 전체 감성 분포
    # ════════════════════════════════════════════════════════
    st.markdown('<div class="card"><div class="card-title">😊 전체 감성 분포</div>',
                unsafe_allow_html=True)
    st.plotly_chart(make_donut(res_df), use_container_width=True,
                    config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    # 분류별 여론
    # ════════════════════════════════════════════════════════
    st.markdown('<div class="card"><div class="card-title">📊 분류별 여론 (긍정/부정/중립)</div>',
                unsafe_allow_html=True)
    st.plotly_chart(make_topic_bar(res_df), use_container_width=True,
                    config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    # 전체 분석 데이터 테이블
    # ════════════════════════════════════════════════════════
    st.markdown('<div class="card">', unsafe_allow_html=True)

    col_t, col_f = st.columns([3, 1])
    with col_t:
        st.markdown('<div class="card-title">📋 전체 분석 데이터</div>',
                    unsafe_allow_html=True)
    with col_f:
        sel = st.selectbox("감성 필터", ["전체"] + Config.SENTIMENT_LABELS,
                           label_visibility="collapsed")

    filtered = res_df if sel == "전체" else res_df[res_df["감성"] == sel]

    # 배지 색상 매핑
    badge_map = {"긍정": "pos", "부정": "neg", "중립": "neu"}

    rows_html = ""
    for _, row in filtered.iterrows():
        b   = badge_map.get(row["감성"], "neu")
        rows_html += f"""
        <tr>
            <td><span class="badge badge-{b}">{row['감성']}</span></td>
            <td><span class="tag">{row['분류']}</span></td>
            <td><strong>{str(row['키워드'])[:20]}</strong></td>
            <td>{str(row['댓글내용'])[:60]}</td>
        </tr>"""

    st.markdown(f"""
    <table class="data-table">
        <thead>
            <tr>
                <th>감성 ↕</th>
                <th>분류 ↕</th>
                <th>키워드 ↕</th>
                <th>댓글 내용</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "⬇️ CSV 다운로드",
        filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"analysis_{video_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    # 면책조항
    # ════════════════════════════════════════════════════════
    st.markdown("""
    <div class="disclaimer">
        <div class="d-title">⚠️ 면책조항 (Disclaimer)</div>
        <ul style="margin:0; padding-left:1.2rem;">
            <li>본 대시보드의 데이터는 유튜브 API를 통해 자동 수집되었으며, 실제 서비스상의 수치와 차이가 있을 수 있습니다.</li>
            <li>댓글 분석 결과는 AI에 의해 생성된 것으로, 실제 작성자의 의도나 공단의 공식 입장과는 다를 수 있습니다.</li>
            <li>제공되는 모든 정보는 참고용이며, 이를 근거로 한 판단에 대한 책임은 사용자에게 있습니다.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
