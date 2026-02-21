import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import re
import io
from datetime import datetime

# 1. API 설정
API_KEY = st.secrets["YOUTUBE_API_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

youtube = build('youtube', 'v3', developerKey=API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 2. 수집 함수
@st.cache_data(ttl=600)
def get_stats(v_id):
    try:
        r = youtube.videos().list(part="snippet,statistics", id=v_id).execute()
        return {
            "title": r['items'][0]['snippet']['title'],
            "v_count": int(r['items'][0]['statistics']['viewCount']),
            "l_count": int(r['items'][0]['statistics']['likeCount']),
            "c_count": int(r['items'][0]['statistics']['commentCount'])
        }
    except: return None

def get_comms(v_id, limit=30): # 속도를 위해 30개로 우선 테스트
    comms = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=100, order="time").execute()
        for item in r['items']:
            snip = item['snippet']['topLevelComment']['snippet']
            comms.append({"time": snip['publishedAt'], "text": snip['textDisplay']})
            if len(comms) >= limit: break
        return pd.DataFrame(comms)
    except: return pd.DataFrame()

# 3. AI 분석 함수 (파싱 로직 대폭 강화)
def analyze_ai(df):
    if df.empty: return pd.DataFrame()
    raw_txt = "\n".join([f"- {t[:100]}" for t in df['text']]) # 댓글당 100자 제한하여 전송
    
    prompt = f"""
    아래 유튜브 댓글들을 분석해서 [감성, 분류, 키워드]를 추출해줘.
    분류는 영상 내용에 맞게 니가 직접 생성해 (최대 9개).
    반드시 '감성|분류|키워드|내용' 형식의 CSV로만 대답해. 설명은 절대 하지마.
    
    댓글:
    {raw_txt}
    """
    try:
        res = model.generate_content(prompt)
        txt = res.text.strip().replace('```csv', '').replace('```', '')
        # 데이터프레임 변환 (구분자 | 사용)
        rdf = pd.read_csv(io.StringIO(txt), sep='|', on_bad_lines='skip')
        rdf.columns = [c.strip() for c in rdf.columns]
        return rdf
    except Exception as e:
        st.error(f"AI 분석 중 기술적 문제 발생: {e}")
        return pd.DataFrame()

# 4. UI 및 레이아웃
st.set_page_config(page_title="유튜브 분석", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

url = st.text_input("유튜브 URL을 입력하고 엔터를 치세요")

if url:
    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if m:
        vid = m.group(1)
        
        # 단계별 진행 확인
        with st.status("데이터 분석 진행 중...", expanded=True) as status:
            st.write("1. 영상 정보 수집 중...")
            info = get_stats(vid)
            st.write("2. 댓글 데이터 수집 중...")
            raw = get_comms(vid)
            st.write("3. AI 주제 분류 및 감성 분석 중...")
            final = analyze_ai(raw)
            status.update(label="분석 완료!", state="complete", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 분석 영상: {info['title']}")
            
            # 지표
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("조회수", f"{info['v_count']:,}")
            i2.metric("좋아요", f"{info['l_count']:,}")
            i3.metric("댓글수", f"{info['c_count']:,}")
            i4.metric("최종 업데이트", datetime.now().strftime('%H:%M'))

            # 차트
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📈 댓글 작성 시간대")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt'), use_container_width=True)
            with c2:
                st.subheader("😊 전체 감성 비율")
                s_counts = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_counts, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            st.subheader("📁 주제별 여론 (최대 9개)")
            # 분류별 막대 그래프
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            st.subheader("📋 전체 상세 데이터")
            st.dataframe(final, use_container_width=True)
        else:
            st.warning("데이터를 불러왔으나 분석 결과가 비어있습니다. API 키나 댓글 허용 여부를 확인하세요.")
