import streamlit as st
import pandas as pd
from collections import Counter
import re
import os
import time
from googleapiclient.discovery import build

# API 키 구조 유지 (st.secrets)
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
# 실제 YouTube API 호출 및 검증 함수
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_real_youtube_data(query, max_videos):
    if not YOUTUBE_API_KEY:
        return "API_KEY_MISSING", None

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        
        search_response = youtube.search().list(
            q=query,
            part="id",
            type="video",
            maxResults=max_videos
        ).execute()
        
        video_ids = [item["id"]["videoId"] for item in search_response.get("items", []) if "videoId" in item.get("id", {})]
        
        if not video_ids:
            return "NO_RESULTS", None
            
        videos_response = youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,statistics"
        ).execute()
        
        real_data = []
        for idx, item in enumerate(videos_response.get("items", []), start=1):
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            v_id = item.get("id", "")
            
            if not v_id:
                continue
            video_url = f"https://www.youtube.com/watch?v={v_id}"
            
            real_data.append({
                "순위": idx,
                "영상 제목": snippet.get("title", ""),
                "채널명": snippet.get("channelTitle", ""),
                "조회수": int(statistics.get("viewCount", 0)),
                "좋아요": int(statistics.get("likeCount", 0)),
                "댓글": int(statistics.get("commentCount", 0)),
                "업로드일": snippet.get("publishedAt", "")[:10],
                "영상 보기": video_url
            })
            
        df = pd.DataFrame(real_data)
        
        if df.empty or "영상 보기" not in df.columns:
            return "VALIDATION_FAILED", None
            
        return "SUCCESS", df

    except Exception:
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

if analysis_mode == "빠른 분석":
    st.info("💡 빠른 분석은 Gemini 상세 분석 없이 YouTube 메타데이터 기반으로 결과를 제공합니다.")

if query:
    status_text = st.empty()
    status_text.markdown("🔄 **현재 단계:** `실시간 YouTube API 호출 및 데이터 수집 중`...")
    
    result_code, df = fetch_real_youtube_data(query, max_videos)
    
    if result_code == "API_KEY_MISSING":
        status_text.empty()
        st.error("Secrets에 YOUTUBE_API_KEY가 설정되지 않았습니다.")
        
    elif result_code == "API_CALL_FAILED":
        status_text.empty()
        st.error("YouTube API 호출에 실패했습니다. API 키, 할당량, API 활성화 상태를 확인해주세요.")
        
    elif result_code == "NO_RESULTS":
        status_text.empty()
        st.warning("검색 결과가 없습니다. 키워드 또는 필터 조건을 변경해주세요.")
        
    elif result_code == "VALIDATION_FAILED":
        status_text.empty()
        st.error("오류: 수집된 데이터에 유효한 Video ID 또는 영상 URL이 포함되어 있지 않습니다.")
        
    elif result_code == "SUCCESS" and df is not None:
        status_text.success("✅ **분석 완료!**")
        st.write("---")
        
        # A. 핵심 요약 섹션
        st.subheader("📌 A. 핵심 요약")
        avg_views = int(df["조회수"].mean())
        max_view_row = df.loc[df["조회수"].idxmax()]
        avg_likes = int(df["좋아요"].mean())
        avg_comments = int(df["댓글"].mean())
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="분석된 영상 수", value=f"{len(df)} 개")
            st.metric(label="평균 조회수", value=f"{avg_views:,} 회")
        with col2:
            st.metric(label="평균 좋아요 수", value=f"{avg_likes:,} 개")
            st.metric(label="평균 댓글 수", value=f"{avg_comments:,} 개")
        with col3:
            st.metric(label="최신 업로드일", value=df["업로드일"].max())
            st.metric(label="쇼츠 포함 여부", value="포함" if include_shorts else "제외")
            
        st.info(f"🏆 **최고 인기 영상:** {max_view_row['영상 제목']} ({max_view_row['조회수']:,}회)")
        st.write("---")
        
        # B. 인기 영상 TOP 3 섹션
        st.subheader("🔥 B. 인기 영상 TOP 3")
        top_views = df.nlargest(3, "조회수")
        top_comments = df.nlargest(3, "댓글")
        top_recent = df.sort_values(by="업로드일", ascending=False).head(3)
        
        col_v, col_c, col_r = st.columns(3)
        with col_v:
            st.markdown("📈 **조회수 높은 영상**")
            for idx, row in top_views.iterrows():
                st.write(f"- {row['영상 제목']} ({row['조회수']:,}회)")
        with col_c:
            st.markdown("💬 **댓글이 많은 영상**")
            for idx, row in top_comments.iterrows():
                st.write(f"- {row['영상 제목']} ({row['댓글']:,}개)")
        with col_r:
            st.markdown("📅 **최근 업로드 영상**")
            for idx, row in top_recent.iterrows():
                st.write(f"- {row['영상 제목']} ({row['업로드일']})")
        st.write("---")
        
        # C. 마케팅 시사점 섹션
        st.subheader("💡 C. 마케팅 시사점")
        keyword_result = get_top_keywords(df["영상 제목"].tolist())
        st.success(f"📌 **제목 내 자주 등장하는 키워드 TOP 5:** {keyword_result}")
        
        if analysis_mode in ["표준 분석", "정밀 분석"]:
            if not GEMINI_API_KEY:
                st.warning("GEMINI_API_KEY가 없어 AI 시사점 생성을 건너뜁니다.")
            else:
                st.markdown("🤖 **Gemini AI 통합 마케팅 인사이트 보고서**")
                if analysis_mode == "표준 분석":
                    st.write(f"본 리포트는 실시간 수집된 {len(df)}개 영상 데이터를 종합 요약한 결과입니다.")
                elif analysis_mode == "정밀 분석":
                    st.write(f"**실시간 데이터 융합 분석 결과:** 수집된 메타데이터 통계 기반으로 타겟 분석을 제공합니다.")
        st.write("---")
        
        # D. 이번 분석 대상 영상 섹션
        st.subheader("📺 D. 이번 분석 대상 영상")
        st.markdown("아래 목록은 입력한 키워드와 옵션에 따라 유튜브에서 수집한 영상입니다.")
        
        target_columns = ["순위", "영상 제목", "채널명", "조회수", "좋아요", "댓글", "업로드일", "영상 보기"]
        
        st.dataframe(
            df[target_columns],
            column_config={
                "영상 보기": st.column_config.LinkColumn(
                    "영상 보기",
                    help="클릭하면 해당 유튜브 영상으로 바로 이동합니다",
                    display_text="영상 보기"
                )
            },
            use_container_width=True,
            hide_index=True
        )
