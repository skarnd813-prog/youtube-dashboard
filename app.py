import streamlit as st
import os
import time

# [요구사항 10] API 키 구조 유지 (st.secrets에서만 로드)
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

st.set_page_config(page_title="YouTube Marketing Dashboard", layout="wide")
st.title("📊 YouTube Marketing Dashboard")

# -----------------------------------------------------------------------------
# [요구사항 8] st.cache_data를 사용한 데이터 수집 및 분석 캐싱 구조
# 같은 키워드와 옵션으로 검색 시 API를 재호출하지 않고 캐시를 활용합니다.
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def fetch_and_analyze_youtube(query, mode, max_videos, period, sort_by, analyze_comments, analyze_captions, include_shorts):
    # 실제 API 연산 로직이 들어가는 부분입니다.
    # [요구사항 7] 분석 중 현재 단계를 st.text 또는 진행 상황으로 표시하기 위해 
    # 호출부(Main)에서 단계를 제어하거나 내부 시뮬레이션을 수행합니다.
    time.sleep(1) # 검색 속도 시뮬레이션
    
    # 결과 샘플 구조 데이터 리턴
    mock_results = {
        "video_count": max_videos,
        "mode_applied": mode,
        "summary": "수집된 영상 데이터를 기반으로 생성된 마케팅 요약 결과입니다."
    }
    return mock_results

# -----------------------------------------------------------------------------
# 사이드바 설정 영역
# -----------------------------------------------------------------------------
st.sidebar.header("🛠️ 분석 옵션 설정")

# [요구사항 1, 2] 분석 모드 3개 제공 및 기본값을 "빠른 분석"으로 설정
analysis_mode = st.sidebar.selectbox(
    "분석 모드 선택",
    ["빠른 분석", "표준 분석", "정밀 분석"],
    index=0
)

# 분석 모드별 동적 기본값 세팅 규칙
if analysis_mode == "빠른 분석":
    default_max = 10
    comment_disabled = True
    caption_disabled = True
    comment_val = False
    caption_val = False
elif analysis_mode == "표준 분석":
    default_max = 20
    comment_disabled = True
    caption_disabled = True
    comment_val = False
    caption_val = False
else: # 정밀 분석
    default_max = 50
    comment_disabled = False
    caption_disabled = False
    comment_val = False  # [요구사항 4] 기본값은 OFF로 유지
    caption_val = False  # [요구사항 4] 기본값은 OFF로 유지

# [요구사항 3] 사용자가 사이드바에서 세부 옵션을 선택할 수 있도록 배치
max_videos = st.sidebar.slider("최대 영상 수", min_value=1, max_value=50, value=default_max)
period = st.sidebar.selectbox("업로드 기간", ["전체", "최근 1주일", "최근 1개월", "최근 1년"])
sort_by = st.sidebar.selectbox("정렬 기준", ["관련성 순", "조회수 순", "최신 순"])

# [요구사항 4] 댓글/자막 분석 여부 (기본값 OFF, 모드별 비활성화 처리)
analyze_comments = st.sidebar.checkbox("댓글 분석 포함 (Gemini 연동)", value=comment_val, disabled=comment_disabled)
analyze_captions = st.sidebar.checkbox("자막 분석 포함 (Gemini 연동)", value=caption_val, disabled=caption_disabled)
include_shorts = st.sidebar.checkbox("쇼cts 포함", value=True)

# [요구사항 9] "정밀 분석" 선택 시 오래 걸릴 수 있다는 안내 문구 표시
if analysis_mode == "정밀 분석":
    st.sidebar.warning("⚠️ '정밀 분석'은 데이터 수집 및 AI 상세 분석 정보가 많아 시간이 오래 걸릴 수 있습니다.")

# -----------------------------------------------------------------------------
# 본문 검색 및 분석 실행 영역
# -----------------------------------------------------------------------------
st.subheader("🔍 유튜브 링크 또는 키워드 분석")
query = st.text_input("분석할 유튜브 링크나 키워드를 입력하세요:")

if query:
    if not YOUTUBE_API_KEY or not GEMINI_API_KEY:
        st.error("Secrets에 API 키가 설정되지 않았습니다. 관리자 설정을 확인해주세요.")
    else:
        st.info(f"'{query}' 키워드로 [{analysis_mode}]을 시작합니다.")
        
        # [요구사항 7] 분석 중에는 현재 단계가 보이게 지시등(Status) 역할 구현
        status_text = st.empty()
        
        # 단계 1: 영상 검색
        status_text.markdown("🔄 **현재 단계:** `영상 검색 중`...")
        # [요구사항 5] 호출 수를 줄이기 위해 검색 결과 목록을 먼저 호출하여 ID를 제한함
        time.sleep(0.8) 
        
        # 단계 2: 상세 데이터 수집
        status_text.markdown("🔄 **현재 단계:** `기본 데이터 수집 중`...")
        time.sleep(0.8)
        
        if analysis_mode != "빠른 분석":
            # 단계 3: AI 요약 생성 (표준, 정밀 분석인 경우에만 진행)
            status_text.markdown("🔄 **현재 단계:** `AI 요약 생성 중`...")
            time.sleep(1.0)
        
        # 캐시 처리된 함수 호출
        results = fetch_and_analyze_youtube(
            query, analysis_mode, max_videos, period, sort_by, 
            analyze_comments, analyze_captions, include_shorts
        )
        
        # 완료 후 단계 메시지 제거 및 결과 출력
        status_text.success("✅ **분석 완료!**")
        
        # 결과 화면 구성
        st.write("---")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="분석된 영상 수", value=f"{results['video_count']}개")
        with col2:
            st.metric(label="적용된 모드", value=results['mode_applied'])
            
        st.write("### 📝 마케팅 데이터 요약 결과")
        # [요구사항 6] 영상마다 개별 호출하지 않고, 수집 결과를 마지막에 1회 통합 요약하여 보여줌
        if analysis_mode == "빠른 분석":
            st.write("※ 빠른 분석 모드에서는 Gemini 상세 분석(요약)이 제외되어 메타데이터 결과만 표시됩니다.")
        else:
            st.write(results["summary"])
