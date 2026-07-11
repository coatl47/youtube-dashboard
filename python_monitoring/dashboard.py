from __future__ import annotations

import csv
import io
from datetime import UTC

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from monitoring.config import Settings
from monitoring.db import Repository
from monitoring.pipeline import analyze_pending, collect_video
from monitoring.youtube import extract_video_id


# GitHub에서 이 한 줄만 수정하면 분석 대상 영상이 바뀝니다.
TARGET_VIDEO_URL = "https://www.youtube.com/watch?v=fNHLffyXnQM"

load_dotenv()
settings = Settings.from_env()
repository = Repository(settings.db_path)
repository.initialize()

st.set_page_config(page_title="유튜브 여론 모니터링", page_icon="📊", layout="wide")
st.markdown(
    """<style>
    .stApp { background: #f3f6fa; }
    .block-container { max-width: 1380px; padding-top: 1.4rem; }
    [data-testid="stMetric"] { background:#fff; border:1px solid #dfe5ed; border-radius:14px; padding:16px; }
    h1, h2, h3 { letter-spacing:-0.03em; color:#172234; }
    </style>""",
    unsafe_allow_html=True,
)

st.title("유튜브 여론 모니터링")
st.caption("수집·AI 분석과 분리된 읽기 전용 화면 · 실제 관측 스냅샷만 추이로 표시")

st.sidebar.subheader("고정 분석 대상")
st.sidebar.code(TARGET_VIDEO_URL, language=None)

if st.sidebar.button("데이터 수집·분석", type="primary", use_container_width=True):
    try:
        with st.spinner("YouTube 댓글을 수집하고 AI로 분석하고 있습니다..."):
            collection = collect_video(settings, repository, TARGET_VIDEO_URL)
            analyzed = analyze_pending(settings, repository, limit=200)
        st.sidebar.success(
            f"수집 {collection.unique:,}건 · 신규 분석 {analyzed:,}건 완료"
        )
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f"수집·분석 실패: {type(exc).__name__}: {exc}")

videos = repository.list_videos()
target_video_id = extract_video_id(TARGET_VIDEO_URL)
video = next((row for row in videos if row["video_id"] == target_video_id), None)

if video is None:
    st.info("아직 수집된 데이터가 없습니다. 왼쪽의 ‘데이터 수집·분석’ 버튼을 눌러주세요.")
    st.stop()

video_id = target_video_id
history, comments, run = repository.dashboard_rows(video_id)

st.subheader(video["title"])
st.caption(f'{video["channel_title"]} · 게시 {pd.to_datetime(video["published_at_utc"]).tz_convert("Asia/Seoul"):%Y-%m-%d %H:%M KST}')

latest = history[-1] if history else {}
valid_comments = [row for row in comments if not row["spam"]]
coverage = (len(valid_comments) / run["unique_count"] * 100) if run and run["unique_count"] else 0
negative = sum(row["sentiment"] == "부정" for row in valid_comments)
negative_rate = negative / len(valid_comments) * 100 if valid_comments else 0

cols = st.columns(5)
cols[0].metric("조회수", f'{latest.get("view_count", 0):,}')
cols[1].metric("좋아요", "비공개" if latest.get("like_count") is None else f'{latest["like_count"]:,}')
cols[2].metric("YouTube 댓글", "비공개" if latest.get("comment_count") is None else f'{latest["comment_count"]:,}')
cols[3].metric("분석 성공", f"{len(valid_comments):,}", help="광고와 분석 실패 제외")
cols[4].metric("부정 비중", f"{negative_rate:.1f}%")

if run:
    state = "정상" if run["status"] == "success" else "부분 수집" if run["status"] == "partial" else "실패"
    st.info(
        f'마지막 수집: {state} · 고유 댓글 {run["unique_count"]:,}건 · '
        f'분석 커버리지 {coverage:.1f}% · API 사용 {run["quota_units"]} units. '
        "인기·최신 혼합 표본은 전체 댓글을 완전히 대표하지 않을 수 있습니다."
    )

left, right = st.columns([1.6, 1])
with left:
    st.subheader("실제 누적 조회수 추이")
    if len(history) < 2:
        st.warning("관측점이 2개 미만입니다. 다음 정기 수집 이후 추이가 표시됩니다.")
    else:
        hdf = pd.DataFrame(history)
        hdf["observed_at_utc"] = pd.to_datetime(hdf["observed_at_utc"], utc=True).dt.tz_convert("Asia/Seoul")
        fig = px.line(hdf, x="observed_at_utc", y="view_count", markers=True)
        fig.update_traces(line_color="#2f6fb6", line_width=3)
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_title="관측 시각 (KST)", yaxis_title="누적 조회수")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

with right:
    st.subheader("감성 분포")
    if valid_comments:
        sdf = pd.DataFrame(valid_comments)["sentiment"].value_counts().rename_axis("감성").reset_index(name="건수")
        fig = px.pie(sdf, names="감성", values="건수", hole=.55,
                     color="감성", color_discrete_map={"긍정": "#2f79c9", "중립": "#8290a8", "부정": "#d24c4c"})
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), legend_orientation="h")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        st.info("분석된 댓글이 없습니다.")

st.subheader("주제별 여론")
if valid_comments:
    tdf = pd.DataFrame(valid_comments).groupby(["topic", "sentiment"]).size().reset_index(name="건수")
    order = tdf.groupby("topic")["건수"].sum().sort_values().index
    fig = px.bar(tdf, x="건수", y="topic", color="sentiment", orientation="h",
                 category_orders={"topic": list(order), "sentiment": ["긍정", "중립", "부정"]},
                 color_discrete_map={"긍정": "#2f79c9", "중립": "#8290a8", "부정": "#d24c4c"})
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_title="댓글 수", yaxis_title="", legend_title="감성")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

st.subheader("근거 댓글 탐색")
if not comments:
    st.info("분석된 댓글이 없습니다.")
    st.stop()

df = pd.DataFrame(comments)
f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
query = f1.text_input("댓글·키워드 검색")
sentiment = f2.selectbox("감성", ["전체", "긍정", "중립", "부정"])
risk = f3.selectbox("위험", ["전체", "긴급", "주의", "관찰"])
topic = f4.selectbox("주제", ["전체", *sorted(df["topic"].dropna().unique())])

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
    "risk": "위험", "sentiment": "감성", "topic": "주제", "keyword": "키워드",
    "text_plain": "댓글", "like_count": "좋아요", "reply_count": "답글", "confidence": "신뢰도",
})[["위험", "감성", "주제", "키워드", "댓글", "좋아요", "답글", "작성시각", "신뢰도"]]
st.dataframe(shown, width="stretch", hide_index=True, height=520)

def csv_safe(frame: pd.DataFrame) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(frame.columns)
    for row in frame.itertuples(index=False, name=None):
        safe = []
        for value in row:
            text = str(value)
            safe.append("'" + text if text.startswith(("=", "+", "-", "@")) else text)
        writer.writerow(safe)
    return ("\ufeff" + output.getvalue()).encode("utf-8")

st.download_button("필터 결과 CSV", csv_safe(shown), f"comments-{video_id}.csv", "text/csv")
st.caption("자동 분류는 참고용입니다. 신뢰도가 낮거나 민감한 항목은 사람이 원문 맥락을 확인하세요.")
