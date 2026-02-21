import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import re
import io
from datetime import datetime

# [1] 설정 및 API 연결
# Streamlit Secrets에 YOUTUBE_API_KEY와 GEMINI_API_KEY가 있어야 합니다.
Y_KEY = st.secrets["YOUTUBE_API_KEY"]
G_KEY = st.secrets["GEMINI_API_KEY"]

# API 서비스 초기화
youtube = build('youtube', 'v3', developerKey=Y_KEY)
genai.configure(api_key=G_KEY)

# [2] 데이터 수집 함수 (기능별 분리)
@st.cache_data(ttl=600)
def get_video_info(v_id):
    try:
        r = youtube.videos().list(part="snippet,statistics", id=v_id).execute()
        item = r['items'][0]
        return {
            "title": item['snippet']['title'],
            "views": int(item['statistics']['viewCount']),
            "likes": int(item['statistics']['likeCount']),
            "comms": int(item['statistics']['commentCount'])
        }
    except: return None

def get_comments_data(v_id, limit=30):
    comments = []
    try:
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=50, order="time").execute()
        for item in r['items']:
            txt = item['snippet']['topLevelComment']['snippet']['textDisplay']
            time = item['snippet']['topLevelComment']['snippet']['publishedAt']
            clean_txt = re.sub('<[^<]+?>', '', txt).replace('\n', ' ')
            comments.append({"time": time, "text": clean_txt})
            if len(comments) >= limit: break
        return pd.DataFrame(comments)
    except: return pd.DataFrame()

# [3] AI 분석 함수 (표준 호출 방식 사용)
def analyze_with_gemini(df):
    if df.empty: return pd.DataFrame()
    
    # 모델 선언 (가장 표준적인 방식)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    raw_text = "\n".join([f"- {t[:100]}" for t in df['text']])
    prompt = f"""
    유튜브 댓글 분석 결과를 '|' 구분자의 CSV 형식으로만 출력해줘.
    분류(주제)는 최대 9개 이내로 생성해.
    형식: 감성|분류|키워드|내용
    (감성: 긍정, 중립, 부정 중 하나)
    
    댓글 목록:
    {raw_text}
    """
    
    try:
        response = model.generate_content(prompt)
        res_txt = response.text.strip()
        
        # 불필요한 마크다운 제거
        clean_csv = re.sub(r'```csv\n|```', '', res_txt)
        if "감성|분류" in clean_csv:
            start = clean_csv.find("감성|분류")
            final_df = pd.read_csv(io.StringIO(clean_csv[start:]), sep='|', on_bad_lines='skip', engine='python')
            final_df.columns = [c.strip() for c in final_df.columns]
            return final_df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"AI 분석 중 오류 발생: {e}")
        return pd.DataFrame()

# [4] 대시보드 UI 구성
st.set_page_config(page_title="유튜브 모니터링", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

video_url = st.text_input("유튜브 URL을 입력하세요")

if video_url:
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', video_url)
    if match:
        vid = match.group(1)
        
        with st.status("분석 중...", expanded=True) as status:
            info = get_video_info(vid)
            raw = get_comments_data(vid)
            final = analyze_with_gemini(raw)
            status.update(label="처리 완료!", state="complete", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 {info['title']}")
            
            # 지표 영역
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("조회수", f"{info['views']:,}")
            m2.metric("좋아요", f"{info['likes']:,}")
            m3.metric("댓글수", f"{info['comms']:,}")
            m4.metric("분석기준", datetime.now().strftime('%Y-%m-%d'))

            # 차트 영역
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📈 시간대별 댓글 추이")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt', markers=True), use_container_width=True)
            with c2:
                st.subheader("😊 감성 분석")
                s_data = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_data, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 분류별 분석
            st.subheader("📁 주제별 여론 분포 (최대 9개)")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 데이터 테이블
            st.subheader("📋 분석 상세 데이터")
            st.dataframe(final, use_container_width=True)
            st.download_button("결과 CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), "result.csv")
        elif info:
            st.warning("데이터는 가져왔으나 AI가 분석 결과를 생성하지 못했습니다. 잠시 후 다시 시도해 보세요.")
    else:
        st.error("올바른 유튜브 주소가 아닙니다.")
