import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
from textblob import TextBlob
import plotly.express as px
import time

# 1. API 설정
API_KEY = st.secrets["YOUTUBE_API_KEY"]
youtube = build('youtube', 'v3', developerKey=API_KEY)

# 2. 데이터 수집 함수 (이름 확인: get_all_comments)
def get_all_comments(video_id, max_count=500):
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
                if len(comments) >= max_count:
                    break
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return comments
    except Exception as e:
        st.error(f"API 오류 발생: {e}")
        return []

# 3. Streamlit UI 구성
st.set_page_config(page_title="YouTube Live Dashboard", layout="wide")
st.title("📊 유튜브 실시간 댓글 분석 대시보드")

st.write("---")
st.write("✅ 시스템이 정상적으로 코드를 읽고 있습니다.")
st.write("---")

# 사이드바 설정
st.sidebar.header("🔄 자동 갱신 설정")
refresh_sec = st.sidebar.slider("갱신 주기 (초)", 10, 60, 30)
run_auto = st.sidebar.checkbox("자동 갱신 실행", value=False) # 처음엔 꺼두는 것이 안전합니다.
target_count = st.sidebar.slider("분석할 댓글 개수", 100, 1000, 300)

# 입력창 수정: 라벨과 기본값 분리
video_url = st.text_input("유튜브 영상 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")

if video_url:
    # 비디오 ID 추출 로직
    if "v=" in video_url:
        video_id = video_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        video_id = video_url.split("/")[-1]
    else:
        video_id = video_url.split("/")[-1].split("?")[0]
    
    # 데이터 표시 영역
    placeholder = st.empty()

    # 분석 실행 부분
    with placeholder.container():
        with st.spinner('데이터를 분석 중입니다...'):
            # 함수 이름 일치시킴: get_all_comments
            comments = get_all_comments(video_id, max_count=target_count)
            
            if comments:
                df = pd.DataFrame(comments, columns=['comment'])
                
                # 감성 분석 (영문 기준이므로 한글은 번역이나 다른 라이브러리가 필요할 수 있지만 일단 유지)
                df['sentiment'] = df['comment'].apply(lambda x: TextBlob(x).sentiment.polarity)
                df['status'] = df['sentiment'].apply(lambda x: '긍정' if x > 0 else ('부정' if x < 0 else '중립'))

                st.write(f"⏱️ 마지막 업데이트: {time.strftime('%Y-%m-%d %H:%M:%S')}")

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("댓글 감성 분포")
                    fig = px.pie(df, names='status', color='status', 
                                 color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#AB63FA'})
                    st.plotly_chart(fig, use_container_width=True)
                    
                with col2:
                    st.subheader(f"최근 댓글 목록 (총 {len(df)}개)")
                    st.dataframe(df[['comment', 'status']], height=400, use_container_width=True)
            else:
                st.warning("분석할 댓글이 없습니다.")

    # 자동 갱신 처리
    if run_auto:
        time.sleep(refresh_sec)
        st.rerun()

