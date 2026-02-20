import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
from textblob import TextBlob
import plotly.express as px
import time  # 시간 제어를 위해 추가

# 1. API 설정
API_KEY = st.secrets["AIzaSyA5fVDWlybF-KgIB0DE-BgACb7xUUkcc9Y"] # (O) 반드시 이대로 적어주세요!
youtube = build('youtube', 'v3', developerKey=API_KEY)

# 2. 데이터 수집 함수
def get_comments(video_id):
    comments_data = []
    try:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=50,
            order="time"  # 실시간 모니터링을 위해 '최신순'으로 가져옵니다
        )
        response = request.execute()
        
        for item in response['items']:
            comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
            comments_data.append(comment)
        return comments_data
    except Exception as e:
        st.error(f"API 호출 오류: {e}")
        return []

# 3. Streamlit UI 구성
st.set_page_config(page_title="YouTube Live Dashboard", layout="wide")
st.title("📊 유튜브 실시간 댓글 분석 대시보드")

# 사이드바 설정
st.sidebar.header("🔄 자동 갱신 설정")
refresh_sec = st.sidebar.slider("갱신 주기 (초)", 30, 60, 30)
run_auto = st.sidebar.checkbox("자동 갱신 실행", value=True)

video_url = st.text_input("https://youtu.be/fNHLffyXnQM?si=-ueDExEYzsvRdeNk")

if video_url:
    # 비디오 ID 추출 (주소 형식이 달라도 대응 가능하도록 수정)
    if "v=" in video_url:
        video_id = video_url.split("v=")[1].split("&")[0]
    else:
        video_id = video_url.split("/")[-1]
    
    # --- 자동 갱신 핵심 로직 ---
    # st.empty()를 사용하여 화면이 계속 아래로 쌓이지 않고 '갱신'되게 합니다.
    placeholder = st.empty()

    while run_auto:
        with placeholder.container():
            # 데이터 수집 및 분석
            comments = get_comments(video_id)
            if not comments:
                st.warning("댓글을 불러올 수 없습니다.")
                break
                
            df = pd.DataFrame(comments, columns=['comment'])
            
            # 감성 분석
            df['sentiment'] = df['comment'].apply(lambda x: TextBlob(x).sentiment.polarity)
            df['status'] = df['sentiment'].apply(lambda x: '긍정' if x > 0 else ('부정' if x < 0 else '중립'))

            # 업데이트 시간 표시
            st.write(f"⏱️ 마지막 업데이트: {time.strftime('%Y-%m-%d %H:%M:%S')}")

            # 통계 시각화
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("댓글 감성 분포")
                fig = px.pie(df, names='status', color='status', 
                             color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#AB63FA'})
                st.plotly_chart(fig, use_container_width=True)
                
            with col2:
                st.subheader("최근 댓글 목록")
                st.dataframe(df[['comment', 'status']], height=400, use_container_width=True)

        # 설정된 시간만큼 대기 후 스크립트 재실행
        time.sleep(refresh_sec)

        st.rerun()
