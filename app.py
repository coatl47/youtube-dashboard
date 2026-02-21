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

# [해결 포인트] 모델명을 드롭다운에서 확인하신 'gemini-3-flash'로 변경합니다.
model = genai.GenerativeModel('gemini-3-flash')

# 2. 수집 함수
@st.cache_data(ttl=600)
def get_stats(v_id):
    try:
        r = youtube.videos().list(part="snippet,statistics", id=v_id).execute()
        return {
            "title": r['items'][0]['snippet']['title'],
            "v_count": int(r['items'][0]['statistics']['view_count']),
            "l_count": int(r['items'][0]['statistics'].get('likeCount', 0)),
            "c_count": int(r['items'][0]['statistics'].get('commentCount', 0))
        }
    except: return None

def get_comms(v_id, limit=50):
    comms = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=100, order="time").execute()
        for item in r.get('items', []):
            snip = item['snippet']['topLevelComment']['snippet']
            clean_txt = re.sub('<[^<]+?>', '', snip['textDisplay']).replace('\n', ' ')
            comms.append({"time": snip['publishedAt'], "text": clean_txt})
            if len(comms) >= limit: break
        return pd.DataFrame(comms)
    except: return pd.DataFrame()

# 3. AI 분석 함수
def analyze_ai(df):
    if df.empty: return pd.DataFrame()
    raw_txt = "\n".join([f"- {t[:120]}" for t in df['text']])
    
    prompt = f"""
    유튜브 댓글 분석 보고서를 CSV 형식으로 작성하세요. 
    구분자는 '|'를 사용하고 헤더는 '감성|분류|키워드|내용' 입니다.
    주제(분류)는 영상 내용에 맞게 최대 9개 이내로 생성하세요.
    
    댓글 목록:
    {raw_txt}
    """
    try:
        response = model.generate_content(prompt)
        txt = response.text.strip()
        
        # 데이터프레임 변환
        if "감성|분류" in txt:
            start_idx = txt.find("감성|분류")
            clean_csv = txt[start_idx:].replace('```csv', '').replace('```', '').strip()
            rdf = pd.read_csv(io.StringIO(clean_csv), sep='|', on_bad_lines='skip', engine='python')
            rdf.columns = [c.strip() for c in rdf.columns]
            return rdf
        return pd.DataFrame()
    except Exception as e:
        st.error(f"AI 분석 중 오류: {e}")
        return pd.DataFrame()

# 4. UI 구성
st.set_page_config(page_title="유튜브 여론 분석", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드 (Gemini 3)")

url = st.text_input("유튜브 URL을 입력하세요")

if url:
    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if m:
        vid = m.group(1)
        with st.status("Gemini 3 모델로 분석 중...", expanded=True) as status:
            info = get_stats(vid)
            raw = get_comms(vid)
            final = analyze_ai(raw)
            status.update(label="분석 완료!", state="complete", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 영상: {info['title']}")
            
            i1, i2, i3, i4 = st.columns(4)
            i1.metric("조회수", f"{info['v_count']:,}")
            i2.metric("좋아요", f"{info['l_count']:,}")
            i3.metric("댓글수", f"{info['c_count']:,}")
            i4.metric("분석일", datetime.now().strftime('%Y-%m-%d'))

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📈 댓글 추이")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt'), use_container_width=True)
            with c2:
                st.subheader("😊 감성 분포")
                sent = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(sent, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            st.subheader("📁 주제별 분석")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            st.dataframe(final, use_container_width=True)
