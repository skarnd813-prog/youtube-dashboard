import streamlit as st
import pandas as pd
from collections import Counter
import re
import os
import datetime
from googleapiclient.discovery import build
import google.generativeai as genai

# [요구사항 8] API 키 로드 및 검증 구조 유지
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="YouTube Marketing Dashboard", layout="wide")
st.title("📊 YouTube Marketing Dashboard")

# -----------------------------------------------------------------------------
# 보조 분석용 단순 텍스트 토큰화 함수
# -----------------------------------------------------------------------------
def get_top_keywords(titles):
    words = []
    for title in titles:
        cleaned = re.sub(r'[^\w\s]', '', title)
        words.extend([w for w in cleaned.split() if len(w) > 1])
    most_common = Counter(words).most_common(5)
    return ", ".join([f"'{k}'({c}회)" for k, c in most_common])

# -----------------------------------------------------------------------------
# [요구사항 1, 2, 8] 실제 YouTube API 데이터 수집 및 엄격한 검증 함수
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_real_youtube_data_v2(query, max_videos):
    if not YOUTUBE_API_KEY:
        return "API_KEY_MISSING", None

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        
        # 1. search().list 호출하여 뼈대 데이터 수집
        search_response = youtube.search().list(
            q=query,
            part="id,snippet",
            type="video",
            maxResults=max_videos
        ).execute()
        
        items = search_response.get("items", [])
        if not items:
            return "NO_RESULTS", None
            
        # [요구사항 1-1, 8-1] videoId 추출 및 엄격한 누락 검증
        video_ids = []
        video_snippets = {}
        for item in items:
            v_id = item.get("id", {}).get("videoId")
            if v_id:
                video_ids.append(v_id)
                video_snippets[v_id] = item.get("snippet", {})
            else:
                # [요구사항 1-7, 8-2] videoId가 없는 결과는 원천 제외 및 에러 처리 분기 목적
                return "VIDEO_ID_MISSING_ERROR", None
                
        if not video_ids:
            return "NO_RESULTS", None
            
        # 2. videos().list 호출하여 실제 마케팅 수치(statistics) 가져오기
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
            
            # [요구사항 1-2, 7] 영상 URL 규칙 적용
            video_url = f"https://www.youtube.com/watch?v={v_id}"
            
            # 일평균 조회수 계산용 경과일 연산
            pub_date_str = snippet.get("publishedAt", "")[:10]
            try:
                pub_date = datetime.datetime.strptime(pub_date_str, "%Y-%m-%d").date()
                days_elapsed = (current_date - pub_date).days
                if days_elapsed <= 0:
                    days_elapsed = 1
            except:
                days_elapsed = 1
                
            # 쇼츠 판단 (재생시간 기반 포맷 식별 보조)
            duration = content_details.get("duration", "")
            is_shorts = "쇼츠" if "M" not in duration and "H" not in duration else "일반 영상"
            
            # 데이터 매핑 (좋아요 수 누락 예외방어 포함)
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
                "영상 보기": video_url, # [요구사항 7] 링크 전용 복제 컬럼
                "경과일": days_elapsed,
                "포맷": is_shorts
            })
            
        df = pd.DataFrame(real_data)
        return "SUCCESS", df

    except Exception:
        return "API_CALL_FAILED", None

# -----------------------------------------------------------------------------
# [요구사항 5] 표준/정밀 분석 전용 Gemini 마케터 관점 가공 함수
# -----------------------------------------------------------------------------
def get_gemini_marketing_insight(df, query, mode):
    if not GEMINI_API_KEY:
        return "Gemini API 키가 Secrets에 설정되어 있지 않아 분석 리포트 출력을 건너뜁니다."
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # [요구사항 5-1] 오직 수집된 원본 메타데이터 요약본만 원천 근거로 전송
        raw_context = ""
        for idx, row in df.iterrows():
            raw_context += f"제목: {row['영상 제목']}, 채널: {row['채널명']}, 조회수: {row['조회수']}, 좋아요: {row['좋아요']}, 댓글: {row['댓글']}, 포맷: {row['포맷']}, URL: {row['영상 URL']}\n"
            
        prompt = f"""
        당신은 대한민국 최고의 뷰티/제품 마케팅 전략가입니다.
        아래 제공된 데이터는 유튜브에서 실시간으로 수집한 '{query}' 키워드의 실제 영상 데이터셋입니다.
        반드시 제공된 실제 데이터의 영상 제목, 채널명, 수치적 성과만을 100% 근거로 삼아 마케터가 바로 카피라이팅 및 콘텐츠 기획에 참고할 수 있는 리포트를 작성하세요.
        존재하지 않는 가짜 영상 제목이나 허구의 통계치를 지어내는 것은 절대 엄금합니다.

        [분석 대상 데이터]
        {raw_context}

        아래 5가지 요구항목에 대해 마케터가 실무 보고서에 바로 복사하여 사용할 수 있도록 구체적인 문장과 마크다운 형식을 사용하여 한글로 작성하세요.

        1. 조회수 높은 영상들의 공통 후킹 포인트 (제목 표현 방식, 콘텐츠 소재, 가격/성분/추천/비교/후기 중 어떤 요소가 소비자를 자극했는지 파악)
        2. 댓글이 많은 영상들의 대화 유발 요소 (조회수 대비 시청자가 댓글 탭을 열고 반응을 남기게 만든 트리거 행동이나 의문점 분석)
        3. 마케터가 참고할 콘텐츠 포맷 (A/B/C 유형으로 구체적인 기획 방향 3개 네이밍 및 실행 전략 제안)
        4. 브랜드가 활용할 수 있는 핵심 메시지 방향 (소비자 인식을 전환시킬 마케팅 메시지 제안)
        5. 이 키워드 영역에서 피해야 할 유저가 피로감을 느끼는 뻔한 콘텐츠 방향
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini 분석 연산 중 오류가 발생했습니다: {str(e)}"

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
# 본문 검색 영역
# -----------------------------------------------------------------------------
st.subheader("🔍 유튜브 검색 및 분석")
query = st.text_input("분석할 유튜브 링크나 키워드를 입력하세요:")

if analysis_mode == "빠른 분석":
    st.info("💡 빠른 분석은 Gemini 상세 분석 없이 YouTube 메타데이터 기반으로 통계적 마케팅 시사점을 제공합니다.")

if query:
    status_text = st.empty()
    status_text.markdown("🔄 **현재 단계:** `유튜브 실시간 데이터 수집 및 무결성 검증 중`...")
    
    # 데이터 수집 호출
    result_code, df = fetch_real_youtube_data_v2(query, max_videos
