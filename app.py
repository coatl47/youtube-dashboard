import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import re
import io
from datetime import datetime

# 1. API 및 서비스 설정
# Streamlit Secrets에 YOUTUBE_API_KEY와 GEMINI_API_KEY가 저장되어 있어야 합니다.
API_KEY = st.secrets["YOUTUBE_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

youtube = build('youtube', 'v3', developerKey=API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 2. 영상 정보 및 댓글 수집 함수
@st.cache_data(ttl=600)
def get_video_info(video_id):
    try:
        req = youtube.videos().list(part="snippet,statistics", id=video_id)
        res = req.execute()
        if not res['items']: return None
        item = res['items'][0]
        return {
            "title": item['snippet']['title'],
            "view": int(item['statistics']['viewCount']),
            "like": int(item['statistics']['likeCount']),
            "comm": int(item['statistics']['commentCount'])
        }
    except: return None

def get_comments(video_id, count=50):
    comments = []
    token = None
    try:
        while len(comments) < count:
            req = youtube.commentThreads().list(
                part="snippet", videoId=video_id, maxResults=100,
                pageToken=token, order="time"
            )
            res = req.execute()
            for item in res['items']:
                snippet = item['snippet']['topLevelComment']['snippet']
                comments.append({"time": snippet['publishedAt'], "comment": snippet['textDisplay']})
                if len(comments) >= count: break
            token = res.get('nextPageToken')
            if not token: break
        return pd.DataFrame(comments)
    except: return pd.DataFrame()

# 3. AI 동적 분류 분석 함수
def analyze_ai_dynamic(df):
    if df.empty: return pd.DataFrame()
    text_data = "\n".join([f"- {c}" for c in df['comment']])
    
    prompt = f"""
    당신은 전문 데이터 분석가입니다. 다음 댓글들을 분석하세요.
    1. 주제(분류)를 스스로 도출하되 최대 9개까지만 생성하세요.
    2. 모든 댓글을 [감성, 분류, 키워드]로 분류하세요.
    3. 반드시 아래 CSV 형식으로만 출력하세요. 구분자는 '|'입니다.
    형식: 감성|분류|키워드|댓글내용
    감성: 긍정, 중립, 부정 중 선택
    
    댓글 목록:
    {text_data}
    """
    try:
        response = model.generate_content(prompt)
        clean_res = response.text.strip().replace('```csv', '').replace('```', '')
        result_df = pd.read_csv(io.StringIO(clean_res), sep='|', on_bad_lines='skip')
        result_df.columns = [c.strip() for c in result_df.columns]
        return result_df
    except: return pd.DataFrame()

# 4. 레이아웃 및 시각화
st.set_page_config(page_title="유튜브 모니터링", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

url = st.text_input("유튜브 URL 입력", placeholder="https://www.youtube.com/watch?v=...")

if url:
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if match:
        v_id = match.group(1)
        with st.spinner('AI 분석 중...'):
            info = get_video_info(v_id)
            raw_df = get_comments(v_id)
            final_df = analyze_ai_dynamic(raw_df)

        if not final_df.empty:
            st.divider()
            st.subheader(f"🎥 {info['title']}")
            
            # 지표
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("조회수", f"{info['view']:,}")
            c2.metric("좋아요", f"{info['like']:,}")
            c3.metric("댓글수", f"{info['comm']:,}")
            c4.metric("분석일", datetime.now().strftime('%Y-%m-%d'))

            # 차트 영역
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("📈 댓글 작성 추이")
                raw_df['time'] = pd.to_datetime(raw_df['time'])
                trend = raw_df.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt'), use_container_width=True)
            with col_b:
                st.subheader("😊 감성 분포")
                sent = final_df['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(sent, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 가로 막대 그래프
            st.subheader("📁 주제별 여론 분포 (AI 자동 생성)")
            bar_data = final_df.groupby(['분류', '감성']).size().reset_index(name='v')
            order = final_df['분류'].value_counts().index.tolist()
            st.plotly_chart(px.bar(bar_data, x='v', y='분류', color='감성', orientation='h',
                                   category_orders={"분류": order},
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 데이터 테이블
            st.subheader("📋 상세 분석 데이터")
            st.dataframe(final_df, use_container_width=True, height=400)
            st.download_button("CSV 다운로드", final_df.to_csv(index=False).encode('utf-8-sig'), "result.csv", "text/csv")
    else:
        st.error("URL 형식이 올바르지 않습니다.")
