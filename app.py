import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import google.generativeai as genai
from google.generativeai.types import RequestOptions
import re
import io
from datetime import datetime

# [설정] API 키 가져오기
API_KEY = st.secrets["YOUTUBE_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# 서비스 초기화
youtube = build('youtube', 'v3', developerKey=API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# 404 에러 해결의 핵심: 모델 호출 시 옵션 설정
# 모델 객체를 함수 안에서 생성하거나 호출 방식을 표준화합니다.
def get_gemini_model():
    return genai.GenerativeModel('gemini-1.5-flash')

# [기능] 유튜브 데이터 수집
@st.cache_data(ttl=600)
def get_video_stats(v_id):
    try:
        r = youtube.videos().list(part="snippet,statistics", id=v_id).execute()
        if not r['items']: return None
        item = r['items'][0]
        return {
            "title": item['snippet']['title'],
            "v_count": int(item['statistics']['viewCount']),
            "l_count": int(item['statistics']['likeCount']),
            "c_count": int(item['statistics']['commentCount'])
        }
    except: return None

def get_comments(v_id, limit=30):
    comms = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=50, order="time").execute()
        for item in r['items']:
            snip = item['snippet']['topLevelComment']['snippet']
            clean_txt = re.sub('<[^<]+?>', '', snip['textDisplay']).replace('\n', ' ')
            comms.append({"time": snip['publishedAt'], "text": clean_txt})
            if len(comms) >= limit: break
        return pd.DataFrame(comms)
    except: return pd.DataFrame()

# [기능] AI 분석 (에러 방지 강화)
def run_analysis(df):
    if df.empty: return pd.DataFrame()
    raw_txt = "\n".join([f"- {t[:120]}" for t in df['text']])
    
    prompt = f"""
    당신은 데이터 분석가입니다. 다음 댓글을 분석하여 '|' 구분자로 된 CSV 형식으로만 답하세요.
    주제(분류)는 영상에 맞춰 최대 9개 이내로 유동적으로 생성하세요.
    형식: 감성|분류|키워드|내용
    (감성: 긍정, 중립, 부정 중 하나)
    
    댓글 목록:
    {raw_txt}
    """
    
    try:
        model = get_gemini_model()
        # 404 에러 방지를 위한 핵심 옵션: api_version='v1'
        response = model.generate_content(
            prompt, 
            request_options=RequestOptions(api_version='v1')
        )
        
        txt = response.text.strip()
        # 데이터프레임 변환
        if "감성|분류" in txt:
            start_idx = txt.find("감성|분류")
            clean_csv = txt[start_idx:].strip().replace('```csv', '').replace('```', '')
            rdf = pd.read_csv(io.StringIO(clean_csv), sep='|', on_bad_lines='skip', engine='python')
            rdf.columns = [c.strip() for c in rdf.columns]
            return rdf
        return pd.DataFrame()
    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
        return pd.DataFrame()

# [UI] 레이아웃 구성
st.set_page_config(page_title="국민연금 모니터링", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

url = st.text_input("유튜브 URL 입력", placeholder="https://www.youtube.com/watch?v=...")

if url:
    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if m:
        vid = m.group(1)
        with st.status("분석 중...", expanded=True) as status:
            info = get_video_stats(vid)
            raw = get_comments(vid)
            final = run_analysis(raw)
            status.update(label="처리 완료!", state="complete", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 {info['title']}")
            
            # 지표 영역
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("조회수", f"{info['v_count']:,}")
            m2.metric("좋아요", f"{info['l_count']:,}")
            m3.metric("댓글수", f"{info['c_count']:,}")
            m4.metric("분석시각", datetime.now().strftime('%H:%M'))

            # 차트 영역
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📈 시간대별 댓글 추이")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt', markers=True), use_container_width=True)
            with col2:
                st.subheader("😊 감성 분석")
                s_counts = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_counts, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            st.subheader("📁 주제별 여론 (최대 9개)")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            st.subheader("📋 전체 상세 데이터")
            st.dataframe(final, use_container_width=True)
            st.download_button("CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), "result.csv")
