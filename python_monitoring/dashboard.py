from __future__ import annotations

import csv
import html
import io
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

st.set_page_config(page_title="유튜브 여론 모니터링", page_icon="📊", layout="centered")
st.markdown(
    """<style>
    :root {
      --brand:#1769c7; --brand-dark:#0f579f; --ink:#172033; --muted:#6f7b8d;
      --line:#e4e9f0; --surface:#ffffff; --page:#f1f4f9;
      --positive:#13a05d; --negative:#e6313b; --neutral:#8b9bad;
    }
    html, body, [class*="css"] { font-family:-apple-system,BlinkMacSystemFont,"Pretendard","Noto Sans KR",sans-serif; }
    .stApp { background:linear-gradient(180deg,#eef5ff 0,#f4f6fa 280px,#f1f3f7 100%); color:var(--ink); }
    .block-container { width:100%; max-width:460px; padding:14px 13px 64px; }
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display:none; }
    h1,h2,h3,p { letter-spacing:-.035em; }

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
    .st-key-top_controls { width:100%; overflow:hidden; }
    .st-key-top_controls [data-testid="stHorizontalBlock"] {
      display:grid!important; grid-template-columns:minmax(0,1fr) 76px; gap:6px; width:100%; align-items:stretch;
    }
    .st-key-top_controls [data-testid="column"] { width:auto!important; min-width:0!important; flex:none!important; }
    .st-key-top_controls [data-testid="stButton"] button { min-height:48px; padding:0 4px; font-size:.69rem; white-space:nowrap; }

    .hero {
      margin:12px 0 16px; padding:22px 16px; border-radius:19px;
      background:linear-gradient(135deg,#114f95 0%,#146ecb 62%,#2a7fe2 100%);
      box-shadow:0 16px 34px rgba(21,87,158,.22); color:#fff;
    }
    .hero-title { font-size:1.35rem; line-height:1.25; font-weight:900; letter-spacing:-.05em; }

    .video-card { background:#fff; border:1px solid rgba(218,226,236,.9); border-radius:18px; padding:17px 14px;
      box-shadow:0 10px 28px rgba(40,65,95,.08); margin-bottom:16px; }
    .video-badge { display:inline-block; padding:6px 10px; border-radius:9px; background:#eaf4ff; color:#1763ab;
      font-size:.72rem; font-weight:850; }
    .video-title { margin:15px 0 13px; color:#172033; font-size:1rem; line-height:1.45; font-weight:900; }
    .video-meta { display:block; color:#707c8d; font-size:.73rem; line-height:1.6; }
    .video-meta span { display:block; margin-bottom:4px; }
    .video-meta b { color:#26354a; margin-right:5px; }
    .video-link { display:inline-block; margin-top:12px; color:#1768bf!important; font-size:.8rem; font-weight:850; text-decoration:none!important; }

    .metric-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:11px; margin:0 0 16px; }
    .metric-card { min-height:102px; padding:15px 13px; border:1px solid #dfe6ee; border-radius:16px; background:rgba(255,255,255,.96);
      box-shadow:0 8px 22px rgba(39,61,88,.055); }
    .metric-label { color:#7a8595; font-size:.76rem; margin-bottom:6px; }
    .metric-value { color:#152033; font-size:1.35rem; font-weight:900; letter-spacing:-.04em; }
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
    [data-testid="stDownloadButton"] button { border-radius:12px; background:#eef5fd; color:#1764b2; border:1px solid #d4e4f5; font-weight:800; }

    .analysis-card { margin:14px 0; background:#fff; border:1px solid #e1e6ed; border-radius:19px;
      box-shadow:0 9px 26px rgba(39,61,88,.065); overflow:hidden; }
    .analysis-head { display:flex; align-items:center; justify-content:space-between; padding:16px 14px 10px; }
    .analysis-head strong { color:#182234; font-size:1rem; font-weight:900; }
    .analysis-count { padding:5px 9px; border-radius:999px; background:#edf6ff; color:#1765b2; font-size:.72rem; font-weight:850; }
    .analysis-scroll { width:100%; overflow-x:auto; }
    .analysis-table { width:100%; min-width:405px; border-collapse:collapse; table-layout:fixed; color:#1d2736; font-size:.77rem; }
    .analysis-table col.sentiment { width:58px; }
    .analysis-table col.topic { width:82px; }
    .analysis-table col.keyword { width:78px; }
    .analysis-table col.comment { width:auto; }
    .analysis-table thead th { padding:10px 8px 12px; border-top:1px solid #e7ebf0; border-bottom:1px solid #e1e6ec;
      background:#fff; text-align:left; vertical-align:top; font-size:.75rem; font-weight:900; }
    .analysis-table thead a { color:#1e2938!important; text-decoration:none!important; }
    .sort-icon { color:#9ca7b4; margin-left:3px; font-size:.72rem; }
    .analysis-table tbody td { padding:11px 8px; border-bottom:1px solid #e1e5ea; vertical-align:top; line-height:1.45; overflow-wrap:anywhere; }
    .analysis-table tbody tr:last-child td { border-bottom:0; }
    .sentiment-chip { display:inline-block; min-width:42px; padding:5px 7px; border-radius:999px; text-align:center; font-size:.69rem; font-weight:900; }
    .sentiment-positive { background:#e4f8ef; color:#15945d; }
    .sentiment-negative { background:#fff0f1; color:#df3b45; }
    .sentiment-neutral { background:#edf1f5; color:#657385; }
    .topic-chip { display:inline-block; max-width:70px; padding:4px 6px; border-radius:7px; background:#697584; color:#fff;
      font-size:.66rem; font-weight:850; line-height:1.15; text-align:center; word-break:keep-all; }
    .keyword-cell { font-weight:850; color:#202938; word-break:keep-all; }
    .comment-cell { color:#323d4c; white-space:normal; }
    [data-testid="stExpander"] { background:#fff; border:1px solid #e1e6ed; border-radius:14px; margin-bottom:9px; }

    .notice-card { background:#fff; border:1px solid #e2e7ee; border-radius:20px; padding:20px 22px;
      box-shadow:0 9px 25px rgba(39,61,88,.055); color:#6e7888; font-size:.78rem; line-height:1.7; }
    .notice-card strong { display:block; color:#263449; font-size:.9rem; margin-bottom:6px; }
    .notice-card ul { margin:4px 0 0; padding-left:19px; }

    @media (max-width:720px) {
      .block-container { padding:12px 13px 56px; }
      [data-testid="stVerticalBlockBorderWrapper"] { border-radius:18px!important; padding:5px 2px 0; }
      [data-testid="column"] { min-width:0!important; }
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


with st.container(key="top_controls"):
    link_col, run_col = st.columns([5, 1])
    with link_col:
        video_url = st.text_input(
            "유튜브 영상 링크",
            value=TARGET_VIDEO_URL,
            placeholder="https://www.youtube.com/watch?v=...",
            label_visibility="collapsed",
        ).strip()
    with run_col:
        run_analysis = st.button("수집·분석", type="primary", use_container_width=True)

video_url = video_url or TARGET_VIDEO_URL

st.markdown(
    """<div class="hero">
      <div class="hero-title">국민연금 이사장 유튜브 여론 모니터링</div>
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

with st.container(border=True):
    section_heading("시간대별 누적 조회수 추이")
    if history:
        hdf = pd.DataFrame(history)
        hdf["observed_at_utc"] = pd.to_datetime(hdf["observed_at_utc"], utc=True).dt.tz_convert("Asia/Seoul")
        baseline = pd.DataFrame({"observed_at_utc":[published], "view_count":[0]})
        chart_df = pd.concat([baseline, hdf[["observed_at_utc", "view_count"]]], ignore_index=True)
        chart_df = chart_df.sort_values("observed_at_utc", kind="stable").drop_duplicates("observed_at_utc", keep="last")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df["observed_at_utc"], y=chart_df["view_count"], mode="lines+markers",
            line=dict(color="#1768bd", width=3), marker=dict(size=7, color="#1768bd"),
            fill="tozeroy", fillcolor="rgba(23,104,189,.09)", hovertemplate="%{y:,}회<extra></extra>",
        ))
        latest_point = chart_df.iloc[-1]
        fig.add_annotation(
            x=latest_point["observed_at_utc"], y=latest_point["view_count"],
            text=f'현재 {int(latest_point["view_count"]):,}회', showarrow=False,
            yshift=16, xanchor="right", font=dict(size=12, color="#1768bd"),
        )
        fig.update_layout(
            height=310, margin=dict(l=8, r=8, t=34, b=8), paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", xaxis_title="", yaxis_title="",
            font=dict(family="Pretendard, Noto Sans KR, sans-serif", color="#647184", size=11),
            hovermode="x unified", showlegend=False,
        )
        fig.update_xaxes(gridcolor="#e7ebf0", showline=True, linecolor="#aeb8c4")
        fig.update_yaxes(gridcolor="#e7ebf0", tickformat="~s")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        st.info("아직 조회수 관측 데이터가 없습니다. 수집·분석 버튼을 눌러주세요.")

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
            height=390, margin=dict(l=8,r=8,t=16,b=72), paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="top", y=-.04, xanchor="center", x=.5, title=""),
            font=dict(family="Pretendard, Noto Sans KR, sans-serif", color="#647184", size=11),
        )
        fig.update_traces(domain=dict(x=[.08,.92], y=[.18,1]))
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
    with st.expander("검색·필터", expanded=False):
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

    allowed_sorts = {
        "sentiment":"sentiment", "topic":"topic", "keyword":"keyword", "comment":"text_plain",
    }
    sort_key = st.query_params.get("sort", "published_at_utc")
    sort_order = st.query_params.get("order", "desc")
    sort_column = allowed_sorts.get(sort_key, "published_at_utc")
    filtered = filtered.sort_values(sort_column, ascending=sort_order == "asc", kind="stable")

    def sort_href(key: str) -> str:
        next_order = "desc" if sort_key == key and sort_order == "asc" else "asc"
        return "?" + urlencode({"sort":key, "order":next_order})

    headers = [
        ("감성", "sentiment"), ("분류", "topic"), ("키워드", "keyword"), ("댓글 내용", "comment"),
    ]
    header_html = "".join(
        f'<th><a href="{sort_href(key)}">{label}<span class="sort-icon">↕</span></a></th>'
        for label, key in headers
    )
    row_html = []
    sentiment_classes = {
        "긍정":"sentiment-positive", "부정":"sentiment-negative", "중립":"sentiment-neutral",
    }
    for row in filtered.itertuples(index=False):
        sentiment_value = safe(row.sentiment)
        sentiment_class = sentiment_classes.get(row.sentiment, "sentiment-neutral")
        comment_text = safe(row.text_plain).replace("\n", "<br>")
        row_html.append(
            f'<tr><td><span class="sentiment-chip {sentiment_class}">{sentiment_value}</span></td>'
            f'<td><span class="topic-chip">{safe(row.topic)}</span></td>'
            f'<td class="keyword-cell">{safe(row.keyword)}</td>'
            f'<td class="comment-cell">{comment_text}</td></tr>'
        )
    if not row_html:
        row_html.append('<tr><td colspan="4" style="padding:28px;text-align:center;color:#8490a0">조건에 맞는 댓글이 없습니다.</td></tr>')

    st.markdown(
        f'''<div class="analysis-card">
          <div class="analysis-head"><strong>전체 분석 데이터</strong><span class="analysis-count">총 {len(filtered):,}건</span></div>
          <div class="analysis-scroll"><table class="analysis-table">
            <colgroup><col class="sentiment"><col class="topic"><col class="keyword"><col class="comment"></colgroup>
            <thead><tr>{header_html}</tr></thead><tbody>{"".join(row_html)}</tbody>
          </table></div>
        </div>''',
        unsafe_allow_html=True,
    )

    filtered["작성시각"] = pd.to_datetime(filtered["published_at_utc"], utc=True).dt.tz_convert("Asia/Seoul")
    shown = filtered.rename(columns={
        "sentiment":"감성", "topic":"분류", "keyword":"키워드", "text_plain":"댓글 내용",
        "like_count":"좋아요", "reply_count":"답글", "risk":"위험", "confidence":"신뢰도",
    })[["감성","분류","키워드","댓글 내용","좋아요","답글","위험","작성시각","신뢰도"]]

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
