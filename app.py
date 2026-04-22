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

def get_best_model():
    """
    결제 한도 문제를 피하기 위해 무료 할당량이 많은 
    Flash 모델을 최우선적으로 선택합니다.
    """
    try:
        # 사용 가능한 모델 리스트 가져오기
        available_models = [m.name for m in genai.list_models()]
        
        # Flash 모델 우선순위 리스트 (최신 모델부터)
        # 3-flash가 목록에 있다면 가장 먼저 선택, 없으면 1.5-flash 선택
        targets = ['models/gemini-3-flash', 'models/gemini-1.5-flash']
        
        for target in targets:
            if target in available_models:
                return genai.GenerativeModel(target)
        
        # 예외 상황: 타겟 모델이 없을 경우 리스트 중 첫 번째 모델 선택
        if available_models:
            return genai.GenerativeModel(available_models[0])
    except Exception as e:
        st.error(f"모델 목록 확인 중 오류: {e}")
    return None

# 2. 데이터 수집 함수
@st.cache_data(ttl=600)
def get_stats(v_id):
    try:
        r = youtube.videos().list(part="snippet,statistics", id=v_id).execute()
        item = r['items'][0]
        return {
            "title": item['snippet']['title'],
            "v_count": int(item['statistics']['viewCount']),
            "l_count": int(item['statistics'].get('likeCount', 0)),
            "c_count": int(item['statistics'].get('commentCount', 0))
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
    
    model = get_best_model()
    if not model:
        st.error("사용 가능한 Gemini 모델을 찾을 수 없습니다.")
        return pd.DataFrame()
        
    raw_txt = "\n".join([f"- {t[:120]}" for t in df['text']])
    prompt = f"""
    당신은 전문 데이터 분석가입니다. 다음 유튜브 댓글들을 분석하세요.
    1. 핵심 주제(분류)를 영상 내용에 맞게 생성하세요 (최대 9개).
    2. 모든 댓글을 [감성, 분류, 키워드, 내용]으로 분류하세요.
    3. 결과는 반드시 '|' 구분자를 사용한 CSV 형식으로만 출력하세요.
    4. 반드시 헤더 '감성|분류|키워드|내용'을 포함하고 다른 설명은 하지 마세요.
    
    댓글 목록:
    {raw_txt}
    """
    try:
        # Flash 모델은 속도가 빠르므로 즉시 응답을 생성합니다.
        response = model.generate_content(prompt)
        res_txt = response.text.strip()
        
        if "감성|분류" in res_txt:
            start_idx = res_txt.find("감성|분류")
            clean_csv = res_txt[start_idx:].replace('```csv', '').replace('```', '').strip()
            rdf = pd.read_csv(io.StringIO(clean_csv), sep='|', on_bad_lines='skip', engine='python')
            rdf.columns = [c.strip() for c in rdf.columns]
            return rdf
        return pd.DataFrame()
    except Exception as e:
        st.error(f"AI 분석 중 오류(429 발생 시 한도 확인 필요): {e}")
        return pd.DataFrame()

# 4. UI 구성
st.set_page_config(page_title="유튜브 여론 분석 대시보드", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 (Flash 모델 최적화)")
st.info("💡 Pro 모델 대신 할당량이 넉넉한 Flash 모델을 사용하여 한도 초과 문제를 방지합니다.")

url = st.text_input("분석할 유튜브 URL을 입력하세요")

if url:
    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if m:
        vid = m.group(1)
        with st.status("무료 할당량이 넉넉한 Flash 모델로 분석 중...", expanded=True) as status:
            info = get_stats(vid)
            raw = get_comms(vid)
            final = analyze_ai(raw)
            if not final.empty:
                status.update(label="분석 완료!", state="complete", expanded=False)
            else:
                status.update(label="분석 실패 (한도 혹은 데이터 확인)", state="error", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 영상 제목: {info['title']}")
            
            # 상단 지표
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 조회수", f"{info['v_count']:,}")
            m2.metric("좋아요", f"{info['l_count']:,}")
            m3.metric("댓글 수", f"{info['c_count']:,}")
            m4.metric("최종 업데이트", datetime.now().strftime('%H:%M'))

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

            st.subheader("📁 주제별 여론 분석")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            st.subheader("📋 분석 데이터 리스트")
            st.dataframe(final, use_container_width=True)
            st.download_button("결과 CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), f"analysis_{vid}.csv")







