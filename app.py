import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import re
import io
from datetime import datetime

# 1. API 초기화 및 보안 설정
# Streamlit Cloud의 Secrets 메뉴에서 YOUTUBE_API_KEY와 GEMINI_API_KEY를 확인하세요.
try:
    Y_KEY = st.secrets["YOUTUBE_API_KEY"]
    G_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("Secrets 설정에서 API 키를 확인해 주세요.")
    st.stop()

# 서비스 연결
youtube = build('youtube', 'v3', developerKey=Y_KEY)
genai.configure(api_key=G_KEY)

# 2. 데이터 수집 함수
@st.cache_data(ttl=600)
def get_video_info(v_id):
    """영상 기본 정보 및 통계 수집"""
    try:
        r = youtube.videos().list(part="snippet,statistics", id=v_id).execute()
        if not r.get('items'): return None
        item = r['items'][0]
        return {
            "title": item['snippet']['title'],
            "views": int(item['statistics']['viewCount']),
            "likes": int(item['statistics'].get('likeCount', 0)),
            "comms": int(item['statistics'].get('commentCount', 0))
        }
    except: return None

def get_comments_data(v_id, limit=50):
    """유튜브 댓글 수집 및 정제"""
    comments = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=100, order="time").execute()
        for item in r.get('items', []):
            snippet = item['snippet']['topLevelComment']['snippet']
            # HTML 태그 제거 및 한 줄 처리로 AI 분석 최적화
            clean_txt = re.sub('<[^<]+?>', '', snippet['textDisplay']).replace('\n', ' ')
            comments.append({"time": snippet['publishedAt'], "text": clean_txt})
            if len(comments) >= limit: break
        return pd.DataFrame(comments)
    except: return pd.DataFrame()

# 3. AI 분석 함수 (404 방지 및 데이터 유실 차단)
def analyze_with_gemini(df):
    """댓글 맥락 기반 맞춤형 주제 분석"""
    if df.empty: return pd.DataFrame()
    
    # 404 에러 해결: 모델명을 가장 단순하게 호출 (접두사 제거)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # 분석용 텍스트 가공
    raw_text = "\n".join([f"- {t[:150]}" for t in df['text']])
    
    prompt = f"""
    당신은 전문 데이터 분석가입니다. 아래 댓글들을 분석하여 보고서를 작성하세요.
    1. 핵심 주제(분류)를 영상 내용에 맞게 생성하세요 (최대 9개). 
    2. 모든 댓글을 [감성, 분류, 키워드, 내용]으로 분류하세요.
    3. 반드시 '|' 구분자를 사용한 CSV 형식으로만 출력하세요.
    4. 반드시 '감성|분류|키워드|내용' 헤더를 포함하고, 다른 말은 하지 마세요.
    
    댓글 목록:
    {raw_text}
    """
    
    try:
        # AI 응답 생성
        response = model.generate_content(prompt)
        res_txt = response.text.strip()
        
        # 데이터프레임 변환 (헤더를 기준으로 데이터 추출)
        if "감성|분류" in res_txt:
            start_pos = res_txt.find("감성|분류")
            clean_csv = res_txt[start_pos:].replace('```csv', '').replace('```', '').strip()
            
            # 파싱 오류 방지를 위해 engine='python' 사용
            final_df = pd.read_csv(io.StringIO(clean_csv), sep='|', on_bad_lines='skip', engine='python')
            # 컬럼명 공백 제거
            final_df.columns = [c.strip() for c in final_df.columns]
            return final_df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"AI 분석 오류: {e}")
        return pd.DataFrame()

# 4. 대시보드 화면 구성
st.set_page_config(page_title="유튜브 여론 분석", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

url = st.text_input("유튜브 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")

if url:
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if match:
        vid = match.group(1)
        
        with st.status("분석 데이터를 가져오는 중...", expanded=True) as status:
            info = get_video_info(vid)
            raw = get_comments_data(vid, limit=50)
            final = analyze_with_gemini(raw)
            if not final.empty:
                status.update(label="분석 완료!", state="complete", expanded=False)
            else:
                status.update(label="분석 결과 생성 실패", state="error", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 분석 영상: {info['title']}")
            
            # 메인 지표
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 조회수", f"{info['views']:,}")
            m2.metric("좋아요", f"{info['likes']:,}")
            m3.metric("댓글 수", f"{info['comms']:,}")
            m4.metric("분석 시각", datetime.now().strftime('%H:%M'))

            # 차트 영역
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📈 시간대별 댓글 분포")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt', markers=True), use_container_width=True)
            with col2:
                st.subheader("😊 감성 분포")
                s_counts = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_counts, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 주제별 여론 분석 (가로 막대)
            st.subheader("📁 주제별 여론 분석 (최대 9개)")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 데이터 상세 내역
            st.subheader("📋 분석 상세 데이터")
            st.dataframe(final, use_container_width=True)
            st.download_button("결과 CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), f"analysis_{vid}.csv")
        elif info:
            st.warning("데이터 수집은 성공했으나 AI가 분석 형식을 맞추지 못했습니다. 다시 시도해 보세요.")
    else:
        st.error("올바른 유튜브 주소가 아닙니다.")
