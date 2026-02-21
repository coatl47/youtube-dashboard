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

def get_comms(v_id, limit=30):
    comms = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=50, order="time").execute()
        for item in r['items']:
            snip = item['snippet']['topLevelComment']['snippet']
            comms.append({"time": snip['publishedAt'], "text": snip['textDisplay']})
            if len(comms) >= limit: break
        return pd.DataFrame(comms)
    except: return pd.DataFrame()

# 3. AI 분석 함수 (파싱 로직 대폭 강화)
def analyze_ai(df):
    if df.empty: return pd.DataFrame()
    raw_txt = "\n".join([f"- {t[:100]}" for t in df['text']])
    
    prompt = f"""
    유튜브 댓글 분석 보고서를 작성해줘.
    
    [작업 지침]
    1. 주제(분류)를 영상 내용에 맞게 직접 생성해 (최대 9개).
    2. 모든 댓글을 [감성, 분류, 키워드, 내용]으로 분류해.
    3. 결과는 반드시 '|' 구분자를 사용한 CSV 형식으로만 출력해.
    4. CSV 헤더는 반드시 '감성|분류|키워드|내용' 이어야 해.
    5. 서론이나 결론 같은 부가 설명은 절대 하지 마.
    
    댓글 목록:
    {raw_txt}
    """
    try:
        response = model.generate_content(prompt)
        full_text = response.text.strip()
        
        # 텍스트 정제: AI가 마크다운 코드 블록 안에 넣었을 경우 추출
        if "감성|분류" in full_text:
            # 헤더가 시작되는 지점부터 끝까지 추출
            start_idx = full_text.find("감성|분류")
            clean_csv = full_text[start_idx:].strip()
            # 마크다운 닫는 기호 제거
            clean_csv = clean_csv.replace("```", "")
            
            # 데이터프레임 읽기
            rdf = pd.read_csv(io.StringIO(clean_csv), sep='|', on_bad_lines='skip', engine='python')
            rdf.columns = [c.strip() for c in rdf.columns]
            return rdf
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"분석 중 오류: {e}")
        return pd.DataFrame()

# 4. UI 구성
st.set_page_config(page_title="유튜브 분석기", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

url = st.text_input("유튜브 URL 입력", placeholder="[https://www.youtube.com/watch?v=](https://www.youtube.com/watch?v=)...")

if url:
    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if m:
        vid = m.group(1)
        
        with st.status("분석 데이터를 불러오는 중입니다...", expanded=True) as status:
            info = get_stats(vid)
            raw = get_comms(vid)
            final = analyze_ai(raw)
            status.update(label="데이터 분석 완료!", state="complete", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 분석 영상: {info['title']}")
            
            # 지표 표시
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("조회수", f"{info['v_count']:,}")
            i2.metric("좋아요", f"{info['l_count']:,}")
            i3.metric("댓글수", f"{info['c_count']:,}")
            i4.metric("최종 업데이트", datetime.now().strftime('%H:%M'))

            # 시각화 차트
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📈 시간대별 댓글 분포")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt', markers=True), use_container_width=True)
            with c2:
                st.subheader("😊 감성 분석 결과")
                s_counts = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_counts, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 분류별 분석 (가로 막대)
            st.subheader("📁 AI 자동 추출 주제별 여론")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 전체 데이터 테이블
            st.subheader("📋 전체 상세 분석 테이블")
            st.dataframe(final, use_container_width=True, height=400)
            
            st.download_button("결과 CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), f"{vid}_analysis.csv", "text/csv")
        else:
            st.warning("⚠️ 데이터를 가져왔으나 AI가 분석 결과를 생성하지 못했습니다. URL이 올바른지, 혹은 댓글이 충분한지 확인해 주세요.")
