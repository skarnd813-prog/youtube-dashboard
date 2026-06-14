import streamlit as st
import os

# 1. 다른 사람들에게 API 키 입력창을 안 보여주기 위해 서버 Secrets에서 자동으로 가져옵니다.
try:
    youtube_api_key = st.secrets["YOUTUBE_API_KEY"]
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    # 혹시 모를 에러를 대비한 예외 처리
    youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")

# 2. 대시보드 제목 설정
st.title("📊 YouTube Marketing Dashboard")

# 3. 이제 화면에 구질구질한 API 키 입력창(st.text_input)은 완전히 제외되었습니다!
# 팀원들이 들어오면 아래 기능만 바로 보이고 즉시 조회할 수 있습니다.

st.subheader("🔍 유튜브 링크 또는 키워드 분석")
query = st.text_input("분석할 유튜브 링크나 키워드를 입력하세요:")

if query:
    st.write(f"'{query}'에 대한 분석을 시작합니다...")
    # 이 아래에 원래 작동하던 사용자님의 데이터 수집 및 분석 로직이 이어집니다.
