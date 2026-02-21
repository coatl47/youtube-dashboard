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

# [해결 포인트] 모델 이름을 단순화하여 호출합니다. 
# 대부분의 최신 환경에서는 'gemini-1.5-flash'만으로 호출하는 것이 가장 안정적입니다.
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

def get_comms(v_id, limit=30):
    comms = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=50, order="time").execute()
        for item in r['items']:
            snip = item['snippet']['topLevelComment']['snippet']
            # HTML 태그 및 줄바꿈 제거하여 AI 분석 효율 높임
            clean_txt = re.sub('<[^<]+?>', '', snip['textDisplay']).replace('\n', ' ')
            comms.append({"time": snip['publishedAt'], "text": clean_txt})
            if len(comms) >= limit: break
        return pd.DataFrame(comms)
    except: return pd.DataFrame()

# 3. AI 분석 함수 (파싱 강화)
def analyze_ai(df):
    if df.empty: return pd.DataFrame()
    raw_txt = "\n".join([f"- {t[:120]}" for t in df['text']])
    
    prompt = f"""
    당신은 전문 데이터 분석가입니다. 다음 유튜브 댓글들을 분석하세요.
    
    [지침]
    1. 주제(분류)를 영상 내용에 맞게 직접 생성하세요 (최대 9개).
    2. 모든 댓글을 [감성, 분류, 키워드, 내용]으로 분류하세요.
    3. 반드시 아래의 CSV 형식으로만 출력하세요. 설명은 생략하세요.
    4. 구분자는 반드시 '|'를 사용하세요.
    
    형식:
    감성|분류|키워드|내용
    
    댓글 목록:
    {raw_txt}
    """
    try:
        # 모델 콘텐츠 생성
        response = model.generate_content(prompt)
        full_text = response.text.strip()
        
        # 데이터프레임 변환 로직 (텍스트 내 마크다운 제거 등)
        clean_csv = re.sub(r'```csv\n|```', '', full_text)
        if "감성|분류" in clean_csv:
            start_idx = clean_csv.find("감성|분류")
            rdf = pd.read_csv(io.StringIO(clean_csv[start_idx:]), sep='|', on_bad_lines='skip', engine='python')
            rdf.columns = [c.strip() for c in rdf.columns]
            return rdf
        return pd.DataFrame()
    except Exception as e:
        st.error(f"AI 분석 중 오류 발생: {e}")
        return pd.DataFrame()

# 4. UI 구성
st.set_page_config(page_title="유튜브 분석기", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

url = st.text_input("유튜브 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")

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
            st.subheader(f"🎥 영상: {info['title']}")
            
            # 메트릭 지표
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("조회수", f"{info['v_count']:,}")
            m2.metric("좋아요", f"{info['l_count']:,}")
            m3.metric("댓글수", f"{info['c_count']:,}")
            m4.metric("최종 업데이트", datetime.now().strftime('%H:%M'))

            # 시각화
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📈 시간대별 댓글 추이")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt', markers=True), use_container_width=True)
            with c2:
                st.subheader("😊 전체 감성 비율")
                s_counts = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_counts, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 분류별 분석 그래프
            st.subheader("📁 주제별 여론 분석 (AI 자동 생성)")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 데이터 테이블
            st.subheader("📋 상세 분석 테이블")
            st.dataframe(final, use_container_width=True, height=400)
            st.download_button("결과 CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), f"analysis_{vid}.csv", "text/csv")
