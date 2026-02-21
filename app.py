import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
from textblob import TextBlob
import plotly.express as px
import time
import re

# 1. API 설정
API_KEY = st.secrets["YOUTUBE_API_KEY"]
youtube = build('youtube', 'v3', developerKey=API_KEY)

# 2. 비디오 ID 추출 함수 (안전성 강화)
def extract_video_id(url):
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

# 3. 데이터 수집 함수 (Paging 로직 포함)
def get_all_comments(video_id, max_count=300):
    comments = []
    next_page_token = None
    try:
        while len(comments) < max_count:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                pageToken=next_page_token,
                order="time"
            )
            response = request.execute()
            for item in response['items']:
                comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
                comments.append(comment)
                if len(comments) >= max_count: break
            next_page_token = response.get('nextPageToken')
            if not next_page_token: break
        return comments
    except Exception as e:
        st.error(f"데이터 수집 중 오류: {e}")
        return []

# 4. UI 구성
st.set_page_config(page_title="YouTube Analysis", layout="wide")
st.title("📊 유튜브 실시간 댓글 분석 대시보드")
st.write("✅ 시스템 정상 작동 중") # 확인용 메시지

# 사이드바
st.sidebar.header("⚙️ 설정")
target_count = st.sidebar.slider("분석할 댓글 개수", 100, 1000, 300, step=100)
refresh_sec = st.sidebar.slider("갱신 주기 (초)", 10, 60, 30)
run_auto = st.sidebar.checkbox("자동 갱신 활성화", value=False)

# 메인 입력창
video_url = st.text_input("유튜브 영상 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=fNHLffyXnQM&t=1s")

if video_url:
    video_id = extract_video_id(video_url)
    
    if video_id:
        # 데이터 표시 컨테이너
        with st.spinner('댓글 수집 및 분석 중...'):
            comments = get_all_comments(video_id, max_count=target_count)
            
            if comments:
                df = pd.DataFrame(comments, columns=['comment'])
                # 단순 감성 분석
                df['sentiment'] = df['comment'].apply(lambda x: TextBlob(x).sentiment.polarity)
                df['status'] = df['sentiment'].apply(lambda x: '긍정' if x > 0 else ('부정' if x < 0 else '중립'))

                st.info(f"⏱️ 마지막 업데이트: {time.strftime('%H:%M:%S')} (수집된 댓글: {len(df)}개)")

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("😊 감성 분포")
                    fig = px.pie(df, names='status', color='status',
                                 color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#AB63FA'})
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.subheader("💬 최신 댓글 현황")
                    st.dataframe(df[['status', 'comment']], height=400, use_container_width=True)
            else:
                st.warning("분석할 댓글이 없습니다.")
    else:
        st.error("유효한 유튜브 주소가 아닙니다.")

# 5. 자동 갱신 로직 (코드 맨 끝에 배치)
if run_auto:
    time.sleep(refresh_sec)
    st.rerun()
