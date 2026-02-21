import streamlit as st
from googleapiclient.discovery import build
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import re
import io
from datetime import datetime

# 1. API 설정 (Secrets 활용)
Y_KEY = st.secrets["YOUTUBE_API_KEY"]
G_KEY = st.secrets["GEMINI_API_KEY"]

youtube = build('youtube', 'v3', developerKey=Y_KEY)
genai.configure(api_key=G_KEY)

# 2. 영상 정보 및 댓글 수집
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

def get_comments_data(v_id, limit=50):
    comments = []
    try:
        # 댓글 190개가 있다면 maxResults를 100으로 설정해 넉넉히 가져옵니다.
        r = youtube.commentThreads().list(part="snippet", videoId=v_id, maxResults=100, order="time").execute()
        for item in r['items']:
            txt = item['snippet']['topLevelComment']['snippet']['textDisplay']
            time = item['snippet']['topLevelComment']['snippet']['publishedAt']
            # 태그 제거 및 정제
            clean_txt = re.sub('<[^<]+?>', '', txt).replace('\n', ' ')
            comments.append({"time": time, "text": clean_txt})
            if len(comments) >= limit: break
        return pd.DataFrame(comments)
    except: return pd.DataFrame()

# 3. AI 분석 함수 (404 에러 방지용 표준 호출)
def analyze_with_gemini(df):
    if df.empty: return pd.DataFrame()
    
    # [해결 포인트] 모델 선언 시 불필요한 경로를 제거하고 이름만 전달합니다.
    # 라이브러리가 내부적으로 최적의 API 엔드포인트를 찾도록 유도합니다.
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    raw_text = "\n".join([f"- {t[:150]}" for t in df['text']])
    prompt = f"""
    당신은 전문 데이터 분석가입니다. 다음 댓글들을 분석하여 보고서를 작성하세요.
    1. 주제(분류)를 영상 내용에 맞게 직접 생성해 (최대 9개).
    2. 모든 댓글을 [감성, 분류, 키워드, 내용]으로 분류해.
    3. 결과는 반드시 '|' 구분자를 사용한 CSV 형식으로만 출력해.
    4. 헤더 '감성|분류|키워드|내용' 외에 어떤 설명도 하지 마.
    
    댓글 목록:
    {raw_text}
    """
    
    try:
        # 가장 단순한 형태의 호출 방식을 사용합니다.
        response = model.generate_content(prompt)
        res_txt = response.text.strip()
        
        # 정제 및 데이터프레임화
        clean_csv = re.sub(r'```csv\n|```', '', res_txt)
        if "감성|분류" in clean_csv:
            start = clean_csv.find("감성|분류")
            final_df = pd.read_csv(io.StringIO(clean_csv[start:]), sep='|', on_bad_lines='skip', engine='python')
            final_df.columns = [c.strip() for c in final_df.columns]
            return final_df
        return pd.DataFrame()
    except Exception as e:
        # 에러 발생 시 로그를 명확히 남깁니다.
        st.error(f"AI 분석 중 오류 발생: {e}")
        return pd.DataFrame()

# 4. 대시보드 레이아웃
st.set_page_config(page_title="유튜브 여론 분석", layout="wide")
st.title("📊 유튜브 실시간 여론 분석 대시보드")

video_url = st.text_input("유튜브 URL을 입력하세요", placeholder="https://www.youtube.com/watch?v=...")

if video_url:
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', video_url)
    if match:
        vid = match.group(1)
        
        with st.status("유튜브 데이터 및 AI 분석 처리 중...", expanded=True) as status:
            info = get_video_info(vid)
            raw = get_comments_data(vid, limit=50) # 댓글 수집량 증가
            final = analyze_with_gemini(raw)
            status.update(label="처리 완료!", state="complete", expanded=False)

        if info and not final.empty:
            st.divider()
            st.subheader(f"🎥 분석 영상: {info['title']}")
            
            # 지표 영역
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 조회수", f"{info['views']:,}")
            m2.metric("좋아요", f"{info['likes']:,}")
            m3.metric("댓글 수", f"{info['comms']:,}")
            m4.metric("분석일", datetime.now().strftime('%Y-%m-%d'))

            # 차트 영역
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📈 시간대별 댓글 추이")
                raw['time'] = pd.to_datetime(raw['time'])
                trend = raw.set_index('time').resample('H').size().reset_index(name='cnt')
                st.plotly_chart(px.line(trend, x='time', y='cnt', markers=True), use_container_width=True)
            with col2:
                st.subheader("😊 감성 분포")
                s_counts = final['감성'].value_counts().reset_index()
                st.plotly_chart(px.pie(s_counts, names='감성', values='count', 
                                       color='감성', color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 분류별 분석
            st.subheader("📁 주제별 여론 분포 (최대 9개)")
            b_data = final.groupby(['분류', '감성']).size().reset_index(name='v')
            st.plotly_chart(px.bar(b_data, x='v', y='분류', color='감성', orientation='h',
                                   color_discrete_map={'긍정':'#00CC96','부정':'#EF553B','중립':'#AB63FA'}), use_container_width=True)

            # 상세 데이터 테이블
            st.subheader("📋 전체 분석 상세 데이터")
            st.dataframe(final, use_container_width=True)
            st.download_button("결과 CSV 다운로드", final.to_csv(index=False).encode('utf-8-sig'), "youtube_analysis.csv")
        elif info:
            st.warning("데이터 수집은 성공했으나, AI 분석 결과 생성에 실패했습니다. API 키의 모델 권한을 확인해 보세요.")
    else:
        st.error("올바른 유튜브 주소 형식이 아닙니다.")
