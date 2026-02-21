import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import re
import time
from datetime import datetime


# 1. 설정 및 API 연결
API_KEY = st.secrets["YOUTUBE_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"] # Gemini API 키 필요

youtube = build('youtube', 'v3', developerKey=API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 2. 비디오 정보 및 댓글 수집 함수
def get_video_stats(video_id):
    request = youtube.videos().list(part="snippet,statistics", id=video_id)
    response = request.execute()
    item = response['items'][0]
    return {
        "title": item['snippet']['title'],
        "view_count": int(item['statistics']['viewCount']),
        "like_count": int(item['statistics']['likeCount']),
        "comment_count": int(item['statistics']['commentCount'])
    }

def get_comments_with_time(video_id, max_count=100):
    comments = []
    next_page_token = None
    while len(comments) < max_count:
        request = youtube.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=100,
            pageToken=next_page_token, order="time"
        )
        response = request.execute()
        for item in response['items']:
            snippet = item['snippet']['topLevelComment']['snippet']
            comments.append({
                "time": snippet['publishedAt'],
                "comment": snippet['textDisplay']
            })
            if len(comments) >= max_count: break
        next_page_token = response.get('nextPageToken')
        if not next_page_token: break
    return pd.DataFrame(comments)

# 3. AI 분석 함수 (감성, 분류, 키워드 한 번에 추출)
def analyze_comments_ai(df):
    # 분석 성능을 위해 최대 50개씩 묶어서 처리하거나 샘플링 권장
    sample_text = "\n".join([f"- {c}" for c in df['comment'].head(30)])
    
    prompt = f"""
    아래 유튜브 댓글들을 분석해서 각 댓글별로 [감성, 분류, 키워드]를 추출해줘.
    분류는 다음 9개 중 하나로만 선택해: 기초연금, 보험료지원, 주택사업, 기금성과, 기금독립성, 치매안심지원, 코스닥, 정책문의, 기타.
    감성은 '긍정', '중립', '부정' 중 하나야.
    결과는 반드시 CSV 형식을 지켜줘. (형식: 감성|분류|키워드|원본댓글내용)
    
    댓글:
    {sample_text}
    """
    
    try:
        response = model.generate_content(prompt)
        # 결과 파싱 로직 (예시용 단순 구현)
        # 실제 운영시에는 response.text를 정제하여 DataFrame으로 결합하는 과정이 필요합니다.
        st.success("AI 분석 완료")
        return response.text
    except:
        return None

# 4. UI 구성
st.set_page_config(page_title="국민연금 유튜브 모니터링", layout="wide")
st.title("📊 국민연금 유튜브 여론 모니터링")

video_url = st.text_input("https://www.youtube.com/watch?v=fNHLffyXnQM")

if video_url:
    video_id = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', video_url).group(1)
    stats = get_video_stats(video_id)
    df = get_comments_with_time(video_id)

    # 상단 지표 (Metric)
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 조회수", f"{stats['view_count']:,}")
    m2.metric("좋아요", f"{stats['like_count']:,}")
    m3.metric("댓글 수", f"{stats['comment_count']:,}")
    m4.metric("최종 업데이트", datetime.now().strftime('%Y-%m-%d %H:%M'))

    # 레이아웃 구성
    col1, col2 = st.columns([1, 1])

    with col1:
        # 1. 시간대별 누적 추이 (조회수 대신 댓글 작성 추이로 대체 시각화)
        st.subheader("📈 시간대별 댓글 작성 추이")
        df['time'] = pd.to_datetime(df['time'])
        df_trend = df.set_index('time').resample('H').size().reset_index(name='counts')
        fig_line = px.line(df_trend, x='time', y='counts', title="시간별 유입량")
        st.plotly_chart(fig_line, use_container_width=True)

    with col2:
        # 2. 전체 감성 분포
        st.subheader("😊 전체 감성 분포")
        # (샘플 데이터를 위한 임시 데이터 - 실제 분석값 반영 필요)
        sentiment_data = pd.DataFrame({'status': ['긍정', '부정', '중립'], 'value': [60, 25, 15]})
        fig_pie = px.pie(sentiment_data, names='status', values='value', 
                         color='status', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'})
        st.plotly_chart(fig_pie, use_container_width=True)

    # 3. 분류별 여론 (가로 막대 그래프)
    st.subheader("📁 주제별 여론 분포")
    category_data = pd.DataFrame({
        '분류': ['기초연금', '보험료지원', '주택사업', '기금성과'],
        '긍정': [20, 15, 10, 30],
        '부정': [5, 10, 2, 20]
    }).melt(id_vars='분류', var_name='감성', value_name='수치')
    
    fig_bar = px.bar(category_data, x='수치', y='분류', color='감성', orientation='h',
                     color_discrete_map={'긍정':'#00CC96','부정':'#EF553B'})
    st.plotly_chart(fig_bar, use_container_width=True)

    # 4. 전체 분석 데이터 테이블
    st.subheader("📋 전체 분석 데이터")
    # 분석된 결과 데이터프레임 (예시)
    analysis_df = pd.DataFrame({
        '감성': ['긍정', '부정', '중립', '긍정'],
        '분류': ['기초연금', '보험료지원', '기금성과', '주택사업'],
        '키워드': ['수급액', '부담', '수익률', '청약'],
        '댓글 내용': df['comment'].head(4).values
    })
    
    st.dataframe(analysis_df, use_container_width=True, height=400)
    
    # CSV 다운로드 버튼
    csv = analysis_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("CSV 다운로드", csv, "analysis_result.csv", "text/csv")

