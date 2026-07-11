from __future__ import annotations

import csv
import html
import io

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from monitoring.config import Settings
from monitoring.db import Repository
from monitoring.pipeline import analyze_pending, collect_video
from monitoring.youtube import extract_video_id


# GitHub에서 이 한 줄을 수정하면 링크 입력창의 기본 분석 대상이 바뀝니다.
TARGET_VIDEO_URL = "https://www.youtube.com/watch?v=fNHLffyXnQM"

load_dotenv()
settings = Settings.from_env()
repository = Repository(settings.db_path)
repository.initialize()

st.set_page_config(page_title="유튜브 여론 모니터링", page_icon="📊", layout="wide")
st.markdown(
    """<style>
    :root {
      --brand:#1769c7; --brand-dark:#0f579f; --ink:#172033; --muted:#6f7b8d;
      --line:#e4e9f0; --surface:#ffffff; --page:#f1f4f9;
      --positive:#13a05d; --negative:#e6313b; --neutral:#8b9bad;
    }
    html, body, [class*="css"] { font-family:-apple-system,BlinkMacSystemFont,"Pretendard","Noto Sans KR",sans-serif; }
    .stApp { background:linear-gradient(180deg,#eef5ff 0,#f4f6fa 280px,#f1f3f7 100%); color:var(--ink); }
    .block-container { max-width:1080px; padding:18px 22px 70px; }
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display:none; }
    h1,h2,h3,p { letter-spacing:-.035em; }

    .link-label { color:#526174; font-size:.78rem; font-weight:800; margin:0 0 6px 2px; }
    [data-testid="stTextInput"] label { display:none; }
    [data-testid="stTextInput"] input {
      min-height:48px; border:1px solid #d8e2ef; border-radius:14px; background:#fff;
      color:#26364b; -webkit-text-fill-color:#26364b; opacity:1; font-size:.88rem;
      box-shadow:0 8px 24px rgba(34,73,117,.07);
    }
    [data-testid="stTextInput"] input:focus { border-color:var(--brand); box-shadow:0 0 0 3px rgba(23,105,199,.12); }
    [data-testid="stButton"] button {
      min-height:48px; border:0; border-radius:14px; background:linear-gradient(135deg,var(--brand-dark),#2780e3);
      color:#fff; font-weight:850; box-shadow:0 9px 20px rgba(23,105,199,.22);
    }
    [data-testid="stButton"] button:hover { color:#fff; border:0; transform:translateY(-1px); }

    .hero {
      margin:14px 0 16px; padding:24px 28px; border-radius:22px;
      background:linear-gradient(135deg,#114f95 0%,#146ecb 62%,#2a7fe2 100%);
      box-shadow:0 16px 34px rgba(21,87,158,.22); color:#fff;
    }
    .hero-kicker { font-size:.76rem; font-weight:750; opacity:.78; margin-bottom:7px; }
    .hero-title { font-size:clamp(1.45rem,3vw,2.2rem); line-height:1.25; font-weight:900; letter-spacing:-.05em; }
    .hero-sub { margin-top:7px; font-size:.82rem; opacity:.82; }
    .pill-row { display:flex; gap:8px; overflow-x:auto; margin:0 0 16px; padding:1px 1px 5px; scrollbar-width:none; }
    .pill { white-space:nowrap; padding:9px 15px; background:#fff; border:1px solid #e2e8f0; border-radius:999px;
      font-size:.8rem; font-weight:800; color:#344154; box-shadow:0 5px 14px rgba(31,55,84,.05); }
    .pill.active { color:#fff; border-color:var(--brand); background:linear-gradient(135deg,#1662b5,#2780e3); }

    .video-card { background:#fff; border:1px solid rgba(218,226,236,.9); border-radius:20px; padding:22px;
      box-shadow:0 10px 28px rgba(40,65,95,.08); margin-bottom:16px; }
    .video-badge { display:inline-block; padding:6px 10px; border-radius:9px; background:#eaf4ff; color:#1763ab;
      font-size:.72rem; font-weight:850; }
    .video-title { margin:15px 0 13px; color:#172033; font-size:1.2rem; line-height:1.45; font-weight:900; }
    .video-meta { display:flex; flex-wrap:wrap; gap:7px 18px; color:#707c8d; font-size:.78rem; line-height:1.6; }
    .video-meta b { color:#26354a; margin-right:5px; }
    .video-link { display:inline-block; margin-top:12px; color:#1768bf!important; font-size:.8rem; font-weight:850; text-decoration:none!important; }

    .metric-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:0 0 16px; }
    .metric-card { min-height:112px; padding:18px; border:1px solid #dfe6ee; border-radius:18px; background:rgba(255,255,255,.96);
      box-shadow:0 8px 22px rgba(39,61,88,.055); }
    .metric-label { color:#7a8595; font-size:.76rem; margin-bottom:6px; }
    .metric-value { color:#152033; font-size:1.6rem; font-weight:900; letter-spacing:-.04em; }
    .metric-note { color:#8a94a2; font-size:.69rem; margin-top:5px; }

    [data-testid="stAlert"] { border-radius:16px; border:0; font-size:.8rem; }
    [data-testid="stVerticalBlockBorderWrapper"] {
      background:rgba(255,255,255,.97); border:1px solid #e2e7ee!important; border-radius:20px!important;
      box-shadow:0 9px 26px rgba(39,61,88,.065); padding:8px 7px 2px; margin-bottom:14px;
    }
    .section-title { color:#172033; font-size:1rem; font-weight:900; margin:3px 0 2px; }
    .section-caption { color:#7b8595; font-size:.76rem; margin:0 0 5px; }
    [data-testid="stPlotlyChart"] { margin-top:-8px; }

    .filter-title { font-size:.78rem; color:#657185; font-weight:800; margin-bottom:-5px; }
    [data-testid="stSelectbox"] label, [data-testid="stTextInput"] label { color:#697588; font-size:.72rem; font-weight:750; }
    [data-baseweb="select"] > div { border-radius:12px; border-color:#dfe5ed; background:#f9fbfd; }
    [data-testid="stDataFrame"] { border:1px solid #e4e8ee; border-radius:14px; overflow:hidden; }
    [data-testid="stDownloadButton"] button { border-radius:12px; background:#eef5fd; color:#1764b2; border:1px solid #d4e4f5; font-weight:800; }

    .notice-card { background:#fff; border:1px solid #e2e7ee; border-radius:20px; padding:20px 22px;
      box-shadow:0 9px 25px rgba(39,61,88,.055); color:#6e7888; font-size:.78rem; line-height:1.7; }
    .notice-card strong { display:block; color:#263449; font-size:.9rem; margin-bottom:6px; }
    .notice-card ul { margin:4px 0 0; padding-left:19px; }

    @media (max-width:720px) {
      .block-container { padding:12px 13px 56px; }
      .hero { margin-top:10px; padding:21px 16px; border-radius:19px; }
      .hero-title { font-size:1.35rem; }
      .hero-sub { font-size:.75rem; }
      .video-card { padding:17px 14px; border-radius:18px; }
      .video-title { font-size:1rem; }
      .video-meta { display:block; font-size:.73rem; }
      .video-meta span { display:block; margin-bottom:4px; }
      .metric-grid { grid-template-columns:repeat(2,1fr); gap:11px; }
      .metric-card { min-height:102px; padding:15px 13px; border-radius:16px; }
      .metric-value { font-size:1.35rem; }
      [data-testid="stVerticalBlockBorderWrapper"] { border-radius:18px!important; padding:5px 2px 0; }
      [data-testid="column"] { min-width:0!important; }
      .st-key-top_controls [data-testid="stHorizontalBlock"] { gap:.55rem; flex-wrap:wrap; }
      .st-key-top_controls [data-testid="column"]:first-child { width:100%!important; flex:1 1 100%!important; }
      .st-key-top_controls [data-testid="column"]:last-child { width:100%!important; flex:1 1 100%!important; }
      [data-testid="stDataFrame"] { font-size:.72rem; }
    }
    </style>""",
    unsafe_allow_html=True,
)


def safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def number(value: int | None) -> str:
    return "비공개" if value is None else f"{value:,}"


def section_heading(title: str, caption: str | None = None) -> None:
    st.markdown(f'<div class="section-title">{safe(title)}</div>', unsafe_allow_html=True)
    if caption:
        st.markdown(f'<div class="section-caption">{safe(caption)}</div>', unsafe_allow_html=True)


st.markdown('<div class="link-label">유튜브 영상 링크</div>', unsafe_allow_html=True)
with st.container(key="top_controls"):
    link_col, run_col = st.columns([4.2, 1])
    with link_col:
        st.text_input(
            "유튜브 영상 링크",
            value=TARGET_VIDEO_URL,
            placeholder="https://www.youtube.com/watch?v=...",
            label_visibility="collapsed",
            disabled=True,
        )
    with run_col:
        run_analysis = st.button("수집·분석", type="primary", use_container_width=True)

video_url = TARGET_VIDEO_URL

st.markdown(
    """<div class="hero">
      <div class="hero-kicker">YOUTUBE SOCIAL LISTENING</div>
      <div class="hero-title">국민연금 이사장 유튜브 여론 모니터링</div>
      <div class="hero-sub">댓글 반응과 주요 이슈를 한눈에 확인합니다.</div>
    </div>
    <div class="pill-row">
      <span class="pill">종합</span><span class="pill active">모니터링 영상</span>
      <span class="pill">댓글 여론</span><span class="pill">주요 분류</span>
    </div>""",
    unsafe_allow_html=True,
)

try:
    target_video_id = extract_video_id(video_url)
except ValueError:
    st.error("올바른 YouTube 영상 링크를 입력해주세요.")
    st.stop()

if run_analysis:
    try:
        with st.spinner("YouTube 댓글을 수집하고 AI로 분석하고 있습니다..."):
            collection = collect_video(settings, repository, video_url)
            analyzed = analyze_pending(settings, repository, limit=200)
        st.success(f"수집 {collection.unique:,}건 · 신규 분석 {analyzed:,}건 완료")
        st.rerun()
    except Exception as exc:
        # API 예외 원문에는 요청 URL이나 키가 포함될 수 있으므로 화면에 출력하지 않습니다.
        if type(exc).__name__ in {"YouTubeRequestError", "GeminiRequestError"}:
            message = str(exc)
        elif "Gemini" in type(exc).__name__ or "ClientError" in type(exc).__name__:
            message = "Gemini API 요청이 거부되었습니다. 보안 수정본을 GitHub에 반영했는지 확인하세요."
        else:
            message = f"처리 중 오류가 발생했습니다 ({type(exc).__name__}). Cloud 로그를 확인하세요."
        st.error(message)

videos = repository.list_videos()
video = next((row for row in videos if row["video_id"] == target_video_id), None)

if video is None:
    st.markdown(
        """<div class="notice-card"><strong>아직 수집된 데이터가 없습니다.</strong>
        위 링크를 확인한 뒤 ‘수집·분석’ 버튼을 눌러 첫 데이터를 만들어주세요.</div>""",
        unsafe_allow_html=True,
    )
    st.stop()

video_id = target_video_id
history, comments, run = repository.dashboard_rows(video_id)
latest = history[-1] if history else {}
valid_comments = [row for row in comments if not row["spam"]]
coverage = (len(valid_comments) / run["unique_count"] * 100) if run and run["unique_count"] else 0
negative = sum(row["sentiment"] == "부정" for row in valid_comments)
negative_rate = negative / len(valid_comments) * 100 if valid_comments else 0

published = pd.to_datetime(video["published_at_utc"], utc=True).tz_convert("Asia/Seoul")
updated = (
    pd.to_datetime(latest["observed_at_utc"], utc=True).tz_convert("Asia/Seoul")
    if latest.get("observed_at_utc") else None
)
badge = f'{video["channel_title"]} · {published:%Y%m%d}'
updated_text = f"{updated:%Y-%m-%d %H:%M:%S}" if updated else "관측 전"
st.markdown(
    f"""<div class="video-card">
      <span class="video-badge">{safe(badge)}</span>
      <div class="video-title">{safe(video["title"])}</div>
      <div class="video-meta">
        <span><b>영상 게시 시점</b>{published:%Y-%m-%d %H:%M:%S}</span>
        <span><b>최종 업데이트</b>{safe(updated_text)}</span>
      </div>
      <a class="video-link" href="{safe(video_url)}" target="_blank" rel="noopener noreferrer">유튜브 영상 열기 ↗</a>
    </div>""",
    unsafe_allow_html=True,
)

metric_items = [
    ("조회수", number(latest.get("view_count", 0)), "가장 최근 수집 기준"),
    ("좋아요", number(latest.get("like_count")), "가장 최근 수집 기준"),
    ("댓글 수", number(latest.get("comment_count")), "유튜브 통계 기준"),
    ("분석 댓글 수", f"{len(valid_comments):,}", "광고 제외 기준"),
]
metric_html = "".join(
    f'<div class="metric-card"><div class="metric-label">{safe(label)}</div>'
    f'<div class="metric-value">{safe(value)}</div><div class="metric-note">{safe(note)}</div></div>'
    for label, value, note in metric_items
)
st.markdown(f'<div class="metric-grid">{metric_html}</div>', unsafe_allow_html=True)

if run:
    state = "정상" if run["status"] == "success" else "부분 수집" if run["status"] == "partial" else "실패"
    st.info(
        f'마지막 수집: {state} · 고유 댓글 {run["unique_count"]:,}건 · '
        f'분석 커버리지 {coverage:.1f}% · 부정 비중 {negative_rate:.1f}% · API {run["quota_units"]} units'
    )

with st.container(border=True):
    section_heading("시간대별 누적 조회수 추이")
    if len(history) < 2:
        st.warning("관측점이 2개 미만입니다. 다음 정기 수집 이후 추이가 표시됩니다.")
    else:
        hdf = pd.DataFrame(history)
        hdf["observed_at_utc"] = pd.to_datetime(hdf["observed_at_utc"], utc=True).dt.tz_convert("Asia/Seoul")
        fig = px.line(hdf, x="observed_at_utc", y="view_count", markers=True)
        fig.update_traces(line_color="#1768bd", line_width=3, marker_size=7, fill="tozeroy", fillcolor="rgba(23,104,189,.09)")
        fig.update_layout(
            height=340, margin=dict(l=8, r=8, t=20, b=8), paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", xaxis_title="", yaxis_title="",
            font=dict(family="Pretendard, Noto Sans KR, sans-serif", color="#647184", size=11),
            hovermode="x unified", showlegend=False,
        )
        fig.update_xaxes(gridcolor="#e7ebf0", showline=True, linecolor="#aeb8c4")
        fig.update_yaxes(gridcolor="#e7ebf0", tickformat="~s")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with st.container(border=True):
    section_heading("전체 감성 분포", "광고성 댓글을 제외한 감성 분포를 보여줍니다.")
    if valid_comments:
        sdf = pd.DataFrame(valid_comments)["sentiment"].value_counts().rename_axis("감성").reset_index(name="건수")
        fig = px.pie(
            sdf, names="감성", values="건수", hole=.58,
            category_orders={"감성": ["긍정", "부정", "중립"]},
            color="감성", color_discrete_map={"긍정":"#13a05d", "부정":"#e6313b", "중립":"#8b9bad"},
        )
        fig.update_traces(textposition="inside", textinfo="percent", textfont_size=13, marker_line_color="#fff", marker_line_width=1)
        fig.update_layout(
            height=350, margin=dict(l=8,r=8,t=16,b=8), paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-.05, xanchor="center", x=.5, title=""),
            font=dict(family="Pretendard, Noto Sans KR, sans-serif", color="#647184", size=11),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar":False})
    else:
        st.info("분석된 댓글이 없습니다.")

with st.container(border=True):
    section_heading("분류별 여론", "주요 분류별 댓글 반응을 감성 기준으로 나누어 보여줍니다.")
    if valid_comments:
        tdf = pd.DataFrame(valid_comments).groupby(["topic", "sentiment"]).size().reset_index(name="건수")
        order = tdf.groupby("topic")["건수"].sum().sort_values().index
        fig = px.bar(
            tdf, x="건수", y="topic", color="sentiment", orientation="h",
            category_orders={"topic":list(order), "sentiment":["긍정","부정","중립"]},
            color_discrete_map={"긍정":"#13a05d", "부정":"#e6313b", "중립":"#8b9bad"},
        )
        fig.update_layout(
            height=max(330, 42*len(order)+120), margin=dict(l=8,r=8,t=18,b=8),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="", yaxis_title="", bargap=.28,
            legend=dict(orientation="h", yanchor="bottom", y=-.2, xanchor="center", x=.5, title=""),
            font=dict(family="Pretendard, Noto Sans KR, sans-serif", color="#647184", size=11),
        )
        fig.update_xaxes(gridcolor="#e8ecf1")
        fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar":False})
    else:
        st.info("분석된 댓글이 없습니다.")

if comments:
    df = pd.DataFrame(comments)
    with st.container(border=True):
        section_heading("전체 분석 데이터", f"총 {len(df):,}건")
        f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
        query = f1.text_input("댓글·키워드 검색", placeholder="검색어 입력")
        sentiment = f2.selectbox("감성", ["전체", "긍정", "중립", "부정"])
        risk = f3.selectbox("위험", ["전체", "긴급", "주의", "관찰"])
        topic = f4.selectbox("분류", ["전체", *sorted(df["topic"].dropna().unique())])

        filtered = df.copy()
        if query:
            mask = filtered["text_plain"].str.contains(query, case=False, na=False) | filtered["keyword"].str.contains(query, case=False, na=False)
            filtered = filtered[mask]
        if sentiment != "전체":
            filtered = filtered[filtered["sentiment"] == sentiment]
        if risk != "전체":
            filtered = filtered[filtered["risk"] == risk]
        if topic != "전체":
            filtered = filtered[filtered["topic"] == topic]

        filtered["작성시각"] = pd.to_datetime(filtered["published_at_utc"], utc=True).dt.tz_convert("Asia/Seoul")
        shown = filtered.rename(columns={
            "sentiment":"감성", "topic":"분류", "keyword":"키워드", "text_plain":"댓글 내용",
            "like_count":"좋아요", "reply_count":"답글", "risk":"위험", "confidence":"신뢰도",
        })[["감성","분류","키워드","댓글 내용","좋아요","답글","위험","작성시각","신뢰도"]]
        st.dataframe(
            shown,
            column_config={
                "댓글 내용": st.column_config.TextColumn(width="large"),
                "작성시각": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                "신뢰도": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.0f%%"),
            },
            width="stretch", hide_index=True, height=520,
        )

        def csv_safe(frame: pd.DataFrame) -> bytes:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(frame.columns)
            for row in frame.itertuples(index=False, name=None):
                values = []
                for value in row:
                    text = str(value)
                    values.append("'" + text if text.startswith(("=", "+", "-", "@")) else text)
                writer.writerow(values)
            return ("\ufeff" + output.getvalue()).encode("utf-8")

        st.download_button("필터 결과 CSV", csv_safe(shown), f"comments-{video_id}.csv", "text/csv")

st.markdown(
    """<div class="notice-card"><strong>면책조항</strong><ul>
      <li>본 대시보드의 수치는 YouTube API 수집 시점 기준이며 실제 서비스 화면과 차이가 있을 수 있습니다.</li>
      <li>댓글 감성 및 주제 분류는 AI 자동 분석 결과로 실제 작성자의 의도와 다를 수 있습니다.</li>
      <li>분석 결과는 참고용이며, 정책 판단이나 대외 커뮤니케이션에는 추가 검토가 필요합니다.</li>
    </ul></div>""",
    unsafe_allow_html=True,
)
