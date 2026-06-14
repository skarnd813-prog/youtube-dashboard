import streamlit as st
import pandas as pd
from collections import Counter
import re
import os
import datetime
from googleapiclient.discovery import build
import google.generativeai as genai

# API 키 설정 (Streamlit Secrets 활용)
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="YouTube Marketing Dashboard", layout="wide")
st.title("📊 YouTube Marketing Dashboard")

# -----------------------------------------------------------------------------
# 보조 데이터 분석용 키워드 추출 함수
# -----------------------------------------------------------------------------
def get_top_keywords(titles):
    words = []
    for title in titles:
        cleaned = re.sub(r'[^\w\s]', '', title)
        words.extend([w for w in cleaned.split() if len(w) > 1])
    most_common = Counter(words).most_common(5)
    return ", ".join([f"'{k}'({c}회)" for k, c in most_common])

# -----------------------------------------------------------------------------
# 실제 YouTube API 데이터 수집 및 엄격한 검증 함수
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_real_youtube_data_v2(query, max_videos):
    if not YOUTUBE_API_KEY:
        return "API_KEY_MISSING", None

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        
        # 1. search().list 호출
        search_response = youtube.search().list(
            q=query,
            part="id,snippet",
            type="video",
            maxResults=max_videos
        ).execute()
        
        items = search_response.get("items", [])
        if not items:
            return "NO_RESULTS", None
            
        video_ids = []
        for item in items:
            v_id = item.get("id", {}).get("videoId")
            if v_id:
                video_ids.append(v_id)
            else:
                return "VIDEO_ID_MISSING_ERROR", None
                
        if not video_ids:
            return "NO_RESULTS", None
            
        # 2. videos().list 호출
        videos_response = youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,statistics,contentDetails"
        ).execute()
        
        real_data = []
        current_date = datetime.date.today()
        
        for idx, item in enumerate(videos_response.get("items", []), start=1):
            v_id = item.get("id", "")
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            content_details = item.get("contentDetails", {})
            
            video_url = f"https://www.youtube.com/watch?v={v_id}"
            
            # 경과일 계산
            pub_date_str = snippet.get("publishedAt", "")[:10]
            try:
                pub_date = datetime.datetime.strptime(pub_date_str, "%Y-%m-%d").date()
                days_elapsed = (current_date - pub_date).days
                if days_elapsed <= 0:
                    days_elapsed = 1
            except:
                days_elapsed = 1
                
            # 쇼츠 여부 판단
            duration = content_details.get("duration", "")
            is_shorts = "쇼츠" if "M" not in duration and "H" not in duration else "일반 영상"
            
            views = int(statistics.get("viewCount", 0))
            likes = statistics.get("likeCount")
            likes_val = int(likes) if likes is not None else "확인 불가"
            comments = int(statistics.get("commentCount", 0))
            
            real_data.append({
                "순위": idx,
                "영상 제목": snippet.get("title", ""),
                "채널명": snippet.get("channelTitle", ""),
                "조회수": views,
                "좋아요": likes_val,
                "댓글": comments,
                "업로드일": pub_date_str,
                "videoId": v_id,
                "영상 URL": video_url,
                "영상 보기": video_url,
                "경과일": days_elapsed,
                "포맷": is_shorts
            })
            
        df = pd.DataFrame(real_data)
        return "SUCCESS", df

    except Exception:
        return "API_CALL_FAILED", None

# -----------------------------------------------------------------------------
# Gemini 마케팅 인사이트 생성 함수
# -----------------------------------------------------------------------------
def get_gemini_marketing_insight(df, query):
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되어 있지 않아 생성할 수 없습니다."
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        raw_context = ""
        for idx, row in df.iterrows():
            raw_context += f"제목: {row['영상 제목']}, 채널: {row['채널명']}, 조회수: {row['조회수']}, 좋아요: {row['좋아요']}, 댓글: {row['댓글']}, 포맷: {row['포맷']}\n"
            
        prompt = f"""
        당신은 실무 뷰티 마케팅 전략가입니다. 아래 제공된 '{query}' 관련 실제 유튜브 데이터셋을 바탕으로 기획 리포트를 작성하세요. 
        지어내지 말고 오직 주어진 영상의 특성만을 근거로 삼아야 합니다.

        {raw_context}

        아래 구조에 맞추어 구체적인 실무 인사이트를 출력하세요.
        1. 조회수 높은 영상들의 공통 후킹 포인트 (제목 표현 방식 및 후킹 요소 분석)
        2. 댓글이 많은 영상들의 대화 유발 요소
        3. 마케터가 참고할 콘텐츠 포맷 (기획 방향 3개 제안)
        4. 브랜드가 활용할 수 있는 메시지 방향
        5. 이 키워드 영역에서 피해야 할 뻔한 콘텐츠 방향
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini 연산 중 에러가 발생했습니다: {str(e)}"

# -----------------------------------------------------------------------------
# 본문 레이아웃 제어 및 시각화
# -----------------------------------------------------------------------------
st.sidebar.header("🛠️ 분석 옵션 설정")
analysis_mode = st.sidebar.selectbox("분석 모드 선택", ["빠른 분석", "표준 분석", "정밀 분석"], index=0)

if analysis_mode == "빠른 분석":
    default_max = 10
    comment_disabled, caption_disabled = True, True
    comment_val, caption_val = False, False
elif analysis_mode == "표준 분석":
    default_max = 20
    comment_disabled, caption_disabled = True, True
    comment_val, caption_val = False, False
else:
    default_max = 50
    comment_disabled, caption_disabled = False, False
    comment_val, caption_val
