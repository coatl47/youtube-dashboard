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

# 서비스 초기화
youtube = build('youtube', 'v3', developerKey=API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# [해결 포인트] 모델 이름을 명확히 지정하고, 최신 SDK 규칙을 따릅니다.
model = genai.GenerativeModel('gemini-1.5-flash')

# 2. 수집 함수
@st.cache_data(ttl=600)
def get_stats(v_id):
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

def get_comms(v_id, limit=30):
    comms = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=50, order="time").execute()
        for item in r['items']:
            snip = item['snippet']['topLevelComment']['snippet']
            # 불필요한 HTML 태그 제거 및 텍스트 정제
            clean_txt = re.sub('<[^<]+?>', '', snip['textDisplay']).replace('\n', ' ')
            comms.append({"time": snip['publishedAt'], "text": clean_txt})
            if len(comms) >= limit: break
        return pd.DataFrame(comms)
    except: return pd.DataFrame()

# 3. AI 분석 함수 (데이터 누락 방지 로직 강화)
def analyze_ai(df):
    if df.empty: return pd.DataFrame()
    raw_txt = "\n".join([f"- {t[:120]}" for t in df['text']])
    
    prompt = f"""
    당신은 전문 데이터 분석가입니다. 다음 유튜브 댓글들을 분석하세요.
    
    [지침]
    1. 주제(분류)를 영상 내용에 맞게 직접 생성하세요 (최대 9개).
    2. 모든 댓글을 [감성, 분류, 키워드, 내용]으로 분류하세요.
    3. 결과는 반드시 '|' 구분자를 사용한 CSV 형식으로만 출력하세요.
    4. 반드시 헤더 '감성|분류|키워드|내용'을 포함하고 다른 말은 절대 하지 마세요.
    
    댓글 목록:
    {raw_txt}
    """
    try:
        # AI 호출 (v1beta 관련 에러 방지를 위해 기본 generate_content 사용)
        response = model.generate_content(prompt)
        full_text = response.text.strip()
        
        # 데이터프레임 변환 (AI의 불필요한 텍스트 제거)
        clean_csv = re.sub(r'```csv\n|```', '', full_text)
        if "감성|분류" in clean_csv:
            start_idx = clean_csv.find("감성|분류")
            rdf = pd.read_csv(io.StringIO(clean_csv[start_idx:]), sep='|', on_bad_lines='skip', engine='python')
            rdf.columns = [c.strip() for c in rdf.columns]
            return rdf
        return pd.DataFrame()
    except Exception as e:
        st.error(f"분석 중 오류 발생: {e}")
        return pd.DataFrame()

# 4. UI 구성
st.set_page_config(page_title="유튜브 여론 분석", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

url = st.text_input("분석할 유튜브 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")

if url:
    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if m:
        vid = m.group(1)
        
        with st.status("데이터 분석 진행 중...", expanded=True) as status:
            info = get_stats(vid)
            raw = get_comms(vid)
            final = analyze_ai(raw)
            if not final.empty:
                status.update(label="분석 성공!", state="complete", expanded=False)
            else:
                status.update(label="분석 실패(데이터 없음)", state="error", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 영상 제목: {info['title']}")
            
            # 상단 지표
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("조회수", f"{info['v_count']:,}")
            m2.metric("좋아요", f"{info['l_count']:,}")
            m3.metric("댓글수", f"{info['c_count']:,}")
            m4.metric("분석 시각", datetime.now().strftime('%H:%M'))

            # 차트 영역
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📈 시간대별 댓글 추이")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt', markers=True), use_container_width=True)
            with c2:
                st.subheader("😊 감성 분석 비율")
                s_counts = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_counts, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 분류 그래프
            st.subheader("📁 AI 추출 주제별 여론 (최대 9개)")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 상세 테이블
            st.subheader("📋 전체 상세 분석 테이블")
            st.dataframe(final, use_container_width=True, height=400)
            st.download_button("결과 CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), f"analysis_{vid}.csv", "text/csv")
        elif info:
            st.warning("⚠️ 유튜브 데이터를 가져왔으나 AI가 표 형식의 분석 결과를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.")
