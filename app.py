import streamlit as st
from googleapiclient.discovery import build
import google.generativeai as genai
import pandas as pd
import re

# 대시보드 기본 설정
st.set_page_config(page_title="AI 유튜브 마케팅 대시보드", layout="wide")
st.title("📊 AI 기반 유튜브 마케팅 & 경쟁사 분석 대시보드")
st.caption("유튜브 채널, 댓글 VOC, 키워드 트렌드를 AI(Gemini)로 분석하는 마케팅 도구입니다.")

# 사이드바에서 API 키 입력 받기 (보안을 위해 화면에서 입력)
st.sidebar.header("🔑 API 설정")
youtube_api_key = st.sidebar.text_input("YouTube API Key", type="password", value="")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", value="")

# 유튜브 및 제미나이 초기화 함수
def init_services(yt_key, gem_key):
    try:
        youtube = build('youtube', 'v3', developerKey=yt_key)
        genai.configure(api_key=gem_key)
        model = genai.GenerativeModel('gemini-1.5-pro')
        return youtube, model
    except Exception as e:
        return None, None

# 유튜브 영상 ID 추출 함수
def extract_video_id(url):
    pattern = r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|e\/|watch\?v%3D|watch\?feature=player_embedded&v=)([^#\&\?]*22?)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

# 유튜브 채널 ID 추출 함수
def extract_channel_id(youtube, url):
    if "channel/" in url:
        return url.split("channel/")[-1].split("/")[0]
    elif "c/" in url or "@" in url:
        handle = url.split("@")[-1].split("/")[0]
        try:
            response = youtube.search().list(q=handle, type='channel', part='id', maxResults=1).execute()
            if response.get('items'):
                return response['items'][0]['id']['channelId']
        except:
            return None
    return None

# API 키가 입력되었을 때만 구동
if youtube_api_key and gemini_api_key:
    youtube, gemini_model = init_services(youtube_api_key, gemini_api_key)
    
    # 3개의 탭 구성
    tab1, tab2, tab3 = st.tabs(["📌 1. 유튜브 채널 분석", "📌 2. 댓글 기반 AI VOC 분석", "📌 3. 키워드 트렌드 분석"])
    
    # ----------------------------------------------------
    # TAB 1: 유튜브 채널 분석
    # ----------------------------------------------------
    with tab1:
        st.header("🏢 유튜브 채널 분석 (Channel Deep-Dive)")
        channel_url = st.text_input("분석할 유튜브 채널 URL을 입력하세요 (예: https://www.youtube.com/@채널명)")
