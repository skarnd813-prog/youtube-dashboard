import streamlit as st
import pandas as pd
from collections import Counter
import re
import os
import time
from googleapiclient.discovery import build

# [요구사항 1, 10] 더미/샘플 데이터 생성 로직 및 단어(sample, dummy, mock 등) 전면 제거
# [요구사항 12] API 키 및 URL 검증 구조 유지
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="YouTube Marketing Dashboard", layout="wide")
st.title("📊 YouTube Marketing Dashboard")

# -----------------------------------------------------------------------------
# 제목 키워드 분석 함수
# -----------------------------------------------------------------------------
def get_top_keywords(titles):
    words = []
    for title in titles:
        cleaned = re.sub(r'[^\w\s]', '', title)
        words.extend([w for w in cleaned.split() if len(w) > 1])
    most_common = Counter(words).most_common(5)
    return ", ".join([f"'{k}'({c}회)" for k, c in most_common])

# -----------------------------------------------------------------------------
# [요구사항 4, 5, 6, 7, 11] 실제 YouTube API 호출 및 검증 함수
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_real_youtube_data(query, max_videos):
    if not YOUTUBE_API_KEY:
        return "API_KEY_MISSING", None

    try:
        # YouTube API 서비스 빌드
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        
        # [요구사항 4] search().list 호출하여 videoId 가져오기
        search_response = youtube.search().list(
            q=query,
            part="id",
            type="video",
            maxResults=max_videos
        ).execute()
        
        video_ids = [item["id"]["videoId"] for item in search_response.get("items", []) if "videoId" in item.get("id", {})]
        
        # [요구사항 3] 검색 결과가 없는 경우 처리
        if not video_ids:
            return "NO_RESULTS", None
            
        # [요구사항 5] videos().list 호출하여 실제 statistics 및 snippet 가져오기
        videos_response = youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,statistics"
        ).execute()
        
        real_data = []
        for idx, item in enumerate(videos_response.get("items", []), start=1):
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            v_id = item.get("id", "")
            
            # [요구사항 9, 12] 실제 YouTube URL 검증 및 생성
            if not v_id:
                continue
            video_url = f"https://www.youtube.com/watch?v={v_id}"
            
            # [요구사항 6, 7] API 응답값에서 영상 메타데이터 및 통계 추출
            real_data.append({
                "순위": idx,
                "영상 제목": snippet.get("title", ""),
                "채널명": snippet.get("channelTitle", ""),
                "조회수": int(statistics.get("viewCount", 0)),
                "좋아요": int(statistics.get("likeCount", 0)),
                "댓글": int(statistics.get("commentCount", 0)),
                "업로드일": snippet.get("publishedAt", "")[:10], # YYYY-MM-DD 형식 추출
                "영상 보기": video_url
            })
            
        df = pd.DataFrame(real_data)
        
        # [요구사항 11, 12] 실제 API 데이터인지 최종 검증
        if df.empty or "영상 보기" not in df.columns:
            return "VALIDATION_FAILED", None
            
        return "SUCCESS", df

    except Exception:
        # [요구사항 2] API 호출 자체에 실패한 경우
        return "API_CALL_FAILED", None

# -----------------------------------------------------------------------------
# 사이드바 설정 영역
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
    comment_val, caption_val = False, False

max_videos = st.sidebar.slider("최대 영상 수", min_value=1, max_value=50, value=default_max)
period = st.sidebar.selectbox("업로드 기간", ["전체", "최근 1주일", "최근 1개월", "최근 1년"])
sort_by = st.sidebar.selectbox("정렬 기준", ["조회수 순", "관련성 순", "최신 순"])
analyze_comments = st.sidebar.checkbox("댓글 분석 포함 (Gemini 연동)", value=comment_val, disabled=comment_disabled)
analyze_captions = st.sidebar.checkbox("자막 분석 포함 (Gemini 연동)", value=caption_val, disabled=caption_disabled)
include_shorts = st.sidebar.checkbox("쇼츠 포함", value=True)

# -----------------------------------------------------------------------------
# 본문 실행 영역
# -----------------------------------------------------------------------------
st.subheader("🔍 유튜브 검색 및 분석")
query = st.text_input("분석할 유튜브 링크나 키워드를 입력하세요:")

# [요구사항 9] 빠른 분석 모드 안내 문구
if analysis_mode == "빠른 분석":
    st.info("💡 빠른 분석은 Gemini 상세 분석 없이 YouTube 메타데이터 기반으로 결과를 제공합니다.")

if query:
    status_text = st.empty()
    status_text.markdown("🔄 **현재 단계:** `실시간 YouTube API 호출 및 데이터 수집 중`...")
    
    # 실제 YouTube 데이터 호출
    result_code, df = fetch_real_youtube_data(query, max_videos)
    
    # [요구사항 2, 3, 12] 결과 상태코드에 따른 예외 처리 및 가짜 데이터 생성 원천 차단
    if result_code == "API_KEY_MISSING":
        status_text.empty()
        st.error("Secrets에 YOUT
