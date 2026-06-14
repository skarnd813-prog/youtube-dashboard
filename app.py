import os
import re
import html
import datetime as dt
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.generativeai as genai


# =============================================================================
# Streamlit 기본 설정
# =============================================================================
st.set_page_config(
    page_title="YouTube Marketing Dashboard",
    page_icon="📊",
    layout="wide"
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    .main-title {
        font-size: 42px;
        font-weight: 800;
        letter-spacing: -0.04em;
        margin-bottom: 4px;
    }

    .sub-copy {
        color: #64748b;
        font-size: 15px;
        margin-bottom: 28px;
    }

    .section-title {
        font-size: 30px;
        font-weight: 800;
        letter-spacing: -0.04em;
        margin-top: 22px;
        margin-bottom: 18px;
    }

    .section-desc {
        color: #64748b;
        font-size: 14px;
        margin-top: -6px;
        margin-bottom: 18px;
    }

    .video-card {
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 16px 18px;
        margin: 8px 0 12px 0;
        background: #ffffff;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
        min-height: 142px;
    }

    .video-card-title {
        font-size: 15px;
        font-weight: 800;
        line-height: 1.45;
        margin-bottom: 8px;
    }

    .video-card-title a {
        text-decoration: none;
        color: #0f172a;
    }

    .video-card-title a:hover {
        color: #2563eb;
        text-decoration: underline;
    }

    .video-meta {
        color: #64748b;
        font-size: 13px;
        line-height: 1.6;
    }

    .insight-card {
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 18px 20px;
        margin: 12px 0 16px 0;
        background: #ffffff;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }

    .insight-card ul {
        padding-left: 20px;
        margin-bottom: 0;
    }

    .insight-card li {
        margin-bottom: 8px;
        line-height: 1.55;
    }

    .pill {
        display: inline-block;
        padding: 6px 11px;
        border-radius: 999px;
        font-size: 13px;
        font-weight: 800;
        margin: 0 6px 8px 0;
        white-space: nowrap;
    }

    .pill-price {
        background: #fff1e6;
        color: #b45309;
    }

    .pill-skin {
        background: #e8f7ef;
        color: #047857;
    }

    .pill-expert {
        background: #eef2ff;
        color: #4338ca;
    }

    .pill-curiosity {
        background: #fff7ed;
        color: #c2410c;
    }

    .pill-routine {
        background: #fdf2f8;
        color: #be185d;
    }

    .pill-compare {
        background: #ecfeff;
        color: #0e7490;
    }

    .pill-general {
        background: #f1f5f9;
        color: #475569;
    }

    .keyword-pill {
        display: inline-block;
        padding: 7px 12px;
        border-radius: 999px;
        background: #f1f5f9;
        color: #334155;
        font-size: 13px;
        font-weight: 700;
        margin: 0 6px 8px 0;
    }

    .note-box {
        padding: 14px 16px;
        border-radius: 14px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        color: #475569;
        font-size: 14px;
        line-height: 1.65;
    }

    .warning-soft {
        padding: 14px 16px;
        border-radius: 14px;
        background: #fff7ed;
        border: 1px solid #fed7aa;
        color: #9a3412;
        font-size: 14px;
        line-height: 1.65;
    }

    a {
        text-decoration: none;
    }

    a:hover {
        text-decoration: underline;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="main-title">📊 YouTube Marketing Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-copy">키워드를 입력하면 실제 YouTube API 검색 결과를 바탕으로 인기 영상, 반응 지표, 콘텐츠 기획 포인트를 정리합니다.</div>',
    unsafe_allow_html=True
)


# =============================================================================
# API KEY
# =============================================================================
def get_secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""

    return value or os.environ.get(name, "")


YOUTUBE_API_KEY = get_secret("YOUTUBE_API_KEY")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")


# =============================================================================
# 유틸 함수
# =============================================================================
def is_url_like(text: str) -> bool:
    if not text:
        return False

    value = text.strip().lower()

    return (
        value.startswith("http://")
        or value.startswith("https://")
        or "youtube.com" in value
        or "youtu.be" in value
    )


def parse_iso8601_duration_to_seconds(duration: str) -> int:
    if not duration:
        return 0

    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)

    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds


def get_published_after(period_option: str):
    now = dt.datetime.utcnow()

    days_map = {
        "최근 1개월": 30,
        "최근 3개월": 90,
        "최근 6개월": 180,
        "최근 1년": 365,
    }

    days = days_map.get(period_option)

    if not days:
        return None

    target = now - dt.timedelta(days=days)
    return target.replace(microsecond=0).isoformat("T") + "Z"


def clean_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def make_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def safe_html(value) -> str:
    return html.escape(str(value), quote=True)


def get_top_keywords(titles, top_n=10):
    stopwords = {
        "다이소",
        "화장품",
        "관련",
        "영상",
        "추천",
        "리뷰",
        "진짜",
        "너무",
        "있는",
        "없는",
        "하는",
        "하면",
        "이거",
        "그냥",
        "오늘",
        "내돈내산",
        "shorts",
        "쇼츠",
        "꿀템",
        "제품",
        "사용",
        "후기",
        "신상",
        "템",
    }

    words = []

    for title in titles:
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", str(title)).lower()

        for word in cleaned.split():
            if len(word) > 1 and word not in stopwords:
                words.append(word)

    return Counter(words).most_common(top_n)


def classify_title_hooks(title: str):
    title = str(title)
    hooks = []

    if any(k in title for k in ["원가", "가격", "가성비", "저렴", "천원", "만원", "비싼", "싼", "5천원", "5000"]):
        hooks.append("가격/가성비")

    if any(k in title for k in ["성분", "피부", "좋아지는", "효과", "보습", "진정", "장벽", "트러블", "민감"]):
        hooks.append("성분/피부 고민")

    if any(k in title for k in ["추천", "의사", "피부과", "원장", "전문가", "쌤"]):
        hooks.append("전문가/추천")

    if any(k in title for k in ["안 써보면", "모르는", "비밀", "진짜", "될까", "충격", "꼭", "알려주는", "살까", "말까"]):
        hooks.append("호기심/검증")

    if any(k in title for k in ["메이크업", "학생", "데일리", "루틴", "꿀템", "필수템", "파우치"]):
        hooks.append("상황/루틴")

    if any(k in title for k in ["비교", "대신", "vs", "VS", "차이"]):
        hooks.append("비교형")

    if not hooks:
        hooks.append("일반 제품 소개")

    return hooks


def hook_to_pill_class(hook: str) -> str:
    mapping = {
        "가격/가성비": "pill-price",
        "성분/피부 고민": "pill-skin",
        "전문가/추천": "pill-expert",
        "호기심/검증": "pill-curiosity",
        "상황/루틴": "pill-routine",
        "비교형": "pill-compare",
        "일반 제품 소개": "pill-general",
    }

    return mapping.get(hook, "pill-general")


def pill_html(hook: str, count: int = None) -> str:
    css_class = hook_to_pill_class(hook)

    label = f"{safe_html(hook)}"
    if count is not None:
        label += f" · {count}개"

    return f'<span class="pill {css_class}">{label}</span>'


def render_video_card(row, value_text: str):
    title = safe_html(row["영상 제목"])
    url = safe_html(row["영상 URL"])
    channel = safe_html(row["채널명"])
    uploaded = safe_html(row["업로드일"])
    format_name = safe_html(row["포맷"])

    st.markdown(
        f"""
        <div class="video-card">
            <div class="video-card-title">
                <a href="{url}" target="_blank">{title}</a>
            </div>
            <div class="video-meta">
                {channel}<br>
                {value_text}<br>
                {uploaded} · {format_name}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def build_rule_based_insights(df: pd.DataFrame):
    hook_counter = Counter()
    hook_examples = defaultdict(list)

    top_df = df.sort_values("조회수", ascending=False).head(min(10, len(df)))

    for _, row in top_df.iterrows():
        hooks = classify_title_hooks(row["영상 제목"])

        for hook in hooks:
            hook_counter[hook] += 1

            if len(hook_examples[hook]) < 3:
                hook_examples[hook].append(
                    {
                        "title": row["영상 제목"],
                        "url": row["영상 URL"],
                        "views": int(row["조회수"]),
                    }
                )

    return hook_counter, hook_examples


# =============================================================================
# YouTube API 데이터 수집
# =============================================================================
@st.cache_data(show_spinner=False, ttl=60 * 30)
def fetch_youtube_keyword_data(
    keyword: str,
    max_videos: int,
    order: str,
    period_option: str,
    include_shorts: bool,
    shorts_threshold_seconds: int,
    region_code: str,
    relevance_language: str,
):
    if not YOUTUBE_API_KEY:
        return "API_KEY_MISSING", None

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        search_max = 50 if not include_shorts else max_videos

        request_params = {
            "q": keyword,
            "part": "id",
            "type": "video",
            "maxResults": min(max(search_max, max_videos), 50),
            "order": order,
        }

        published_after = get_published_after(period_option)

        if published_after:
            request_params["publishedAfter"] = published_after

        if region_code != "전체":
            request_params["regionCode"] = region_code

        if relevance_language != "전체":
            request_params["relevanceLanguage"] = relevance_language

        search_response = youtube.search().list(**request_params).execute()

        video_ids = []

        for item in search_response.get("items", []):
            video_id = item.get("id", {}).get("videoId")

            if video_id:
                video_ids.append(video_id)

        video_ids = list(dict.fromkeys(video_ids))

        if not video_ids:
            return "NO_RESULTS", None

        videos_response = youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,statistics,contentDetails",
        ).execute()

        items_by_id = {
            item.get("id"): item
            for item in videos_response.get("items", [])
        }

        today = dt.date.today()
        rows = []

        for video_id in video_ids:
            item = items_by_id.get(video_id)

            if not item:
                continue

            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            title = snippet.get("title", "").strip()
            channel_title = snippet.get("channelTitle", "").strip()
            published_at = snippet.get("publishedAt", "")[:10]

            duration_seconds = parse_iso8601_duration_to_seconds(
                content.get("duration", "")
            )

            is_shorts = 0 < duration_seconds <= shorts_threshold_seconds

            if not include_shorts and is_shorts:
                continue

            try:
                published_date = dt.datetime.strptime(
                    published_at,
                    "%Y-%m-%d"
                ).date()

                days_elapsed = max((today - published_date).days, 1)

            except Exception:
                days_elapsed = 1

            view_count = clean_int(stats.get("viewCount"), 0)
            comment_count = clean_int(stats.get("commentCount"), 0)

            like_raw = stats.get("likeCount")
            like_count = clean_int(like_raw, 0) if like_raw is not None else None

            video_url = make_video_url(video_id)

            rows.append(
                {
                    "영상 제목": title,
                    "채널명": channel_title,
                    "조회수": view_count,
                    "좋아요": like_count,
                    "댓글": comment_count,
                    "업로드일": published_at,
                    "videoId": video_id,
                    "영상 URL": video_url,
                    "영상 보기": video_url,
                    "경과일": days_elapsed,
                    "일평균 조회수": round(view_count / days_elapsed, 1) if days_elapsed else 0,
                    "댓글률(%)": round((comment_count / view_count) * 100, 3) if view_count > 0 else 0,
                    "좋아요율(%)": round((like_count / view_count) * 100, 3) if like_count is not None and view_count > 0 else None,
                    "포맷": "쇼츠 추정" if is_shorts else "일반 영상 추정",
                    "영상 길이(초)": duration_seconds,
                }
            )

        if not rows:
            return "NO_RESULTS_AFTER_FILTER", None

        df = pd.DataFrame(rows)

        if order == "viewCount":
            df = df.sort_values("조회수", ascending=False)

        elif order == "date":
            df = df.sort_values("업로드일", ascending=False)

        else:
            df = df.reset_index(drop=True)

        df = df.head(max_videos).reset_index(drop=True)
        df.insert(0, "순위", range(1, len(df) + 1))

        if df["videoId"].isna().any() or (df["videoId"].astype(str).str.len() == 0).any():
            return "VIDEO_ID_MISSING", None

        return "SUCCESS", df

    except HttpError:
        return "API_CALL_FAILED", None

    except Exception:
        return "UNKNOWN_ERROR", None


# =============================================================================
# Gemini 인사이트
# =============================================================================
def get_gemini_insight(df: pd.DataFrame, keyword: str) -> str:
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되어 있지 않아 AI 상세 인사이트를 생성할 수 없습니다."

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")

        cols = [
            "영상 제목",
            "채널명",
            "조회수",
            "좋아요",
            "댓글",
            "업로드일",
            "댓글률(%)",
            "좋아요율(%)",
            "일평균 조회수",
            "포맷",
            "영상 URL",
        ]

        context = df[cols].to_string(index=False)

        prompt = f"""
너는 뷰티/리테일 실무 마케팅 전략가다.

아래 데이터는 사용자가 "{keyword}" 키워드로 검색해서 실제 YouTube API로 수집한 영상 데이터다.
없는 영상, 없는 수치, 없는 사실을 지어내지 말 것.
반드시 제공된 데이터 안에서만 해석할 것.
확정할 수 없는 내용은 "추정"이라고 표시할 것.

[실제 수집 데이터]
{context}

아래 구조로 답변하라.

1. 조회수 상위 영상의 성공 패턴
- 제목 후킹 방식
- 콘텐츠 소재
- 클릭을 유도했을 가능성이 높은 이유

2. 댓글률이 높은 영상의 대화 유발 요소
- 댓글이 달릴 만한 논쟁, 궁금증, 공감 포인트

3. 마케터가 바로 참고할 콘텐츠 기획 방향 3개
- 각 방향마다 실행 가능한 예시 제목 1개
- 실제 영상 제목을 그대로 베끼지 말 것

4. 브랜드/제품 마케팅 관점의 시사점
- 가격, 성분, 후기, 추천, 전문가성, 루틴 중 어떤 메시지가 유리해 보이는지

5. 피해야 할 뻔한 방향
- 데이터상 반응이 약해 보이는 접근
- 너무 흔해서 차별성이 약한 접근

한국어로 간결하지만 실무적으로 작성하라.
"""

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"Gemini 분석 중 오류가 발생했습니다. 확인 필요: {e}"


# =============================================================================
# 사이드바 옵션
# =============================================================================
st.sidebar.header("🛠️ 분석 옵션 설정")

analysis_mode = st.sidebar.selectbox(
    "분석 모드",
    ["빠른 분석", "표준 분석", "정밀 분석"],
    index=0,
)

default_max = {
    "빠른 분석": 10,
    "표준 분석": 20,
    "정밀 분석": 50,
}[analysis_mode]

max_videos = st.sidebar.slider(
    "최대 영상 수",
    min_value=1,
    max_value=50,
    value=default_max,
)

period_option = st.sidebar.selectbox(
    "업로드 기간",
    ["전체", "최근 1개월", "최근 3개월", "최근 6개월", "최근 1년"],
    index=0,
)

sort_label = st.sidebar.selectbox(
    "정렬 기준",
    ["조회수 순", "관련성 순", "최신순"],
    index=0,
)

order = {
    "조회수 순": "viewCount",
    "관련성 순": "relevance",
    "최신순": "date",
}[sort_label]

include_shorts = st.sidebar.checkbox("쇼츠 포함", value=True)

shorts_threshold_seconds = st.sidebar.slider(
    "쇼츠 추정 기준(초)",
    min_value=30,
    max_value=180,
    value=60,
    step=10,
    help="YouTube API가 Shorts 여부를 직접 제공하지 않아 영상 길이 기준으로 추정합니다.",
)

region_label = st.sidebar.selectbox(
    "검색 지역",
    ["대한민국", "전체"],
    index=0,
)

region_code = "KR" if region_label == "대한민국" else "전체"

language_label = st.sidebar.selectbox(
    "검색 언어",
    ["한국어", "전체"],
    index=0,
)

relevance_language = "ko" if language_label == "한국어" else "전체"

if analysis_mode == "빠른 분석":
    st.sidebar.caption("빠른 분석: Gemini 없이 YouTube 메타데이터 기반으로 분석합니다.")

elif analysis_mode == "표준 분석":
    st.sidebar.caption("표준 분석: YouTube 메타데이터 + Gemini 요약을 제공합니다.")

else:
    st.sidebar.caption("정밀 분석: 더 많은 영상 기반으로 Gemini 상세 인사이트를 제공합니다.")


# =============================================================================
# 입력 영역
# =============================================================================
st.markdown('<div class="section-title">🔎 키워드 분석</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-desc">유튜브 링크나 채널 링크가 아니라, 분석하고 싶은 검색 키워드만 입력하세요.</div>',
    unsafe_allow_html=True
)

with st.form("search_form", clear_on_submit=False):
    keyword = st.text_input(
        "분석할 키워드",
        placeholder="예: 다이소 화장품, 올리브영 선크림, PDRN 크림",
    )

    submitted = st.form_submit_button(
        "분석 시작",
        type="primary",
    )

if not submitted:
    st.info("키워드를 입력한 뒤 **분석 시작**을 눌러주세요.")
    st.stop()

keyword = keyword.strip()

if not keyword:
    st.warning("분석할 키워드를 입력해주세요.")
    st.stop()

if is_url_like(keyword):
    st.warning("이 대시보드는 키워드 분석 전용입니다. 유튜브 링크나 채널 링크가 아니라 검색 키워드만 입력해주세요.")
    st.stop()


# =============================================================================
# 데이터 수집 실행
# =============================================================================
with st.spinner("YouTube API에서 실제 영상 데이터를 수집하는 중입니다..."):
    status, df = fetch_youtube_keyword_data(
        keyword=keyword,
        max_videos=max_videos,
        order=order,
        period_option=period_option,
        include_shorts=include_shorts,
        shorts_threshold_seconds=shorts_threshold_seconds,
        region_code=region_code,
        relevance_language=relevance_language,
    )

if status == "API_KEY_MISSING":
    st.error("YouTube API 키가 설정되어 있지 않습니다. Streamlit Secrets의 YOUTUBE_API_KEY를 확인하세요.")
    st.stop()

if status == "NO_RESULTS":
    st.warning("검색 결과가 없습니다. 키워드 또는 필터 조건을 변경해주세요.")
    st.stop()

if status == "NO_RESULTS_AFTER_FILTER":
    st.warning("필터 적용 후 남은 영상이 없습니다. 쇼츠 포함 여부, 업로드 기간, 최대 영상 수를 변경해주세요.")
    st.stop()

if status == "VIDEO_ID_MISSING":
    st.error("영상 링크를 생성할 수 없습니다. YouTube API videoId 수집 로직을 확인하세요.")
    st.stop()

if status == "API_CALL_FAILED":
    st.error("YouTube API 호출에 실패했습니다. API 키, 할당량, YouTube Data API v3 활성화 상태를 확인하세요.")
    st.stop()

if status == "UNKNOWN_ERROR":
    st.error("알 수 없는 오류가 발생했습니다. 코드 또는 배포 로그 확인이 필요합니다.")
    st.stop()

if df is None or df.empty:
    st.error("실제 영상 데이터를 가져오지 못했습니다.")
    st.stop()

st.success("분석 완료!")


# =============================================================================
# 핵심 요약
# =============================================================================
st.divider()
st.markdown('<div class="section-title">📌 핵심 요약</div>', unsafe_allow_html=True)

avg_views = int(df["조회수"].mean())
avg_comments = int(df["댓글"].mean())

like_series = df["좋아요"].dropna()
avg_likes = int(like_series.mean()) if len(like_series) > 0 else None

avg_comment_rate = round(float(df["댓글률(%)"].mean()), 3)
latest_upload_in_df = df["업로드일"].max()

top_view_row = df.sort_values("조회수", ascending=False).iloc[0]
top_daily_row = df.sort_values("일평균 조회수", ascending=False).iloc[0]

shorts_count = len(df[df["포맷"] == "쇼츠 추정"])
shorts_ratio = round(shorts_count / len(df) * 100, 1) if len(df) > 0 else 0

c1, c2, c3 = st.columns(3)

c1.metric("분석된 영상 수", f"{len(df)}개")
c2.metric("평균 조회수", f"{avg_views:,}회")
c3.metric("평균 댓글률", f"{avg_comment_rate:.3f}%")

c4, c5, c6 = st.columns(3)

c4.metric("평균 댓글 수", f"{avg_comments:,}개")
c5.metric("평균 좋아요 수", f"{avg_likes:,}개" if avg_likes is not None else "확인 불가")
c6.metric("쇼츠 추정 비중", f"{shorts_ratio:.1f}%")

st.markdown(
    f"""
    <div class="note-box">
    🏆 <b>최고 조회수 영상</b><br>
    <a href="{safe_html(top_view_row['영상 URL'])}" target="_blank">{safe_html(top_view_row['영상 제목'])}</a>
    · {int(top_view_row['조회수']):,}회
    <br><br>
    ⚡ <b>일평균 조회수 최고 영상</b><br>
    <a href="{safe_html(top_daily_row['영상 URL'])}" target="_blank">{safe_html(top_daily_row['영상 제목'])}</a>
    · {float(top_daily_row['일평균 조회수']):,.1f}회/일
    </div>
    """,
    unsafe_allow_html=True
)

st.caption(
    f"분석 대상 중 최신 업로드일: {latest_upload_in_df} · "
    "이 날짜는 전체 YouTube 검색 결과의 최신일이 아니라, 현재 조건으로 수집된 영상 중 가장 최근 업로드일입니다. "
    "쇼츠 여부는 YouTube API 직접값이 아니라 영상 길이 기준 추정값입니다."
)


# =============================================================================
# 바로 참고할 인기 영상
# =============================================================================
st.divider()
st.markdown('<div class="section-title">🔥 바로 참고할 인기 영상</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-desc">조회수, 댓글률, 일평균 조회수 기준으로 바로 확인할 만한 영상을 정리했습니다.</div>',
    unsafe_allow_html=True
)

top_views = df.sort_values("조회수", ascending=False).head(3)
top_comment_rate = df.sort_values("댓글률(%)", ascending=False).head(3)
top_daily_views = df.sort_values("일평균 조회수", ascending=False).head(3)

b1, b2, b3 = st.columns(3)

with b1:
    st.markdown("### 📈 조회수 TOP 3")

    for _, row in top_views.iterrows():
        render_video_card(
            row,
            f"{int(row['조회수']):,}회"
        )

with b2:
    st.markdown("### 💬 댓글률 TOP 3")

    for _, row in top_comment_rate.iterrows():
        render_video_card(
            row,
            f"댓글률 {float(row['댓글률(%)']):.3f}% · 댓글 {int(row['댓글']):,}개"
        )

with b3:
    st.markdown("### ⚡ 일평균 조회수 TOP 3")

    for _, row in top_daily_views.iterrows():
        render_video_card(
            row,
            f"{float(row['일평균 조회수']):,.1f}회/일"
        )


# =============================================================================
# 마케터용 시사점
# =============================================================================
st.divider()
st.markdown('<div class="section-title">💡 마케터용 시사점</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-desc">조회수 상위 영상의 제목 패턴과 반응 지표를 바탕으로 콘텐츠 기획에 쓸 수 있는 방향을 정리했습니다.</div>',
    unsafe_allow_html=True
)

hook_counter, hook_examples = build_rule_based_insights(df)

st.markdown("### 상위권 영상에서 반복된 후킹 유형")

if hook_counter:
    pill_group = ""

    for hook, count in hook_counter.most_common(7):
        pill_group += pill_html(hook, count)

    st.markdown(pill_group, unsafe_allow_html=True)

else:
    st.markdown("분석 가능한 제목 패턴이 충분하지 않습니다.")

st.markdown("### 후킹 유형별 참고 영상")

if hook_counter:
    for hook, count in hook_counter.most_common(5):
        examples = hook_examples[hook]

        list_items = ""

        for example in examples:
            list_items += (
                f'<li><a href="{safe_html(example["url"])}" target="_blank">'
                f'{safe_html(example["title"])}</a> · {int(example["views"]):,}회</li>'
            )

        st.markdown(
            f"""
            <div class="insight-card">
                {pill_html(hook, count)}
                <ul>
                    {list_items}
                </ul>
            </div>
            """,
            unsafe_allow_html=True
        )

else:
    st.info("후킹 유형을 분류할 수 있는 영상 데이터가 부족합니다.")

st.markdown("### 콘텐츠 기획에 바로 쓸 수 있는 방향")

top_hooks = [hook for hook, _ in hook_counter.most_common(4)]

planning_points = []

if "가격/가성비" in top_hooks:
    planning_points.append(
        ("가격 대비 효능 비교형", "저렴한 제품을 단순 추천하는 것보다, 가격 대비 성분·사용감·효과를 비교하는 구조가 유리합니다.")
    )

if "성분/피부 고민" in top_hooks:
    planning_points.append(
        ("피부 고민 해결형", "피부 고민을 먼저 제시하고, 제품을 해결책처럼 보여주는 콘텐츠가 반응을 만들 가능성이 있습니다.")
    )

if "전문가/추천" in top_hooks:
    planning_points.append(
        ("큐레이션/추천형", "추천 구조는 클릭을 만들 수 있지만, 브랜드 공식 콘텐츠에서는 전문가 보증처럼 보이는 표현은 내부 검토가 필요합니다.")
    )

if "호기심/검증" in top_hooks:
    planning_points.append(
        ("검증/실험형", "“진짜 괜찮을까?”, “살까 말까?”처럼 소비자의 의심을 콘텐츠 주제로 가져오는 방식이 적합합니다.")
    )

if "상황/루틴" in top_hooks:
    planning_points.append(
        ("상황별 루틴형", "학생, 출근, 데일리, 파우치처럼 실제 사용 상황을 붙이면 콘텐츠 이해도가 높아집니다.")
    )

if "비교형" in top_hooks:
    planning_points.append(
        ("대체재 비교형", "고가 제품과 저가 제품의 성분·사용감 차이를 비교하는 포맷이 적합합니다.")
    )

if not planning_points:
    planning_points.append(
        ("제품 발견형", "현재 데이터에서는 뚜렷한 후킹 유형이 강하게 보이지 않으므로, 신상·숨은템·추천템 중심의 발견형 콘텐츠부터 테스트하는 것이 안전합니다.")
    )

for title, desc in planning_points[:4]:
    st.markdown(
        f"""
        <div class="insight-card">
            <b>{safe_html(title)}</b><br>
            <span class="video-meta">{safe_html(desc)}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("### 브랜드 관점에서 볼 포인트")

shorts_df = df[df["포맷"] == "쇼츠 추정"]
normal_df = df[df["포맷"] == "일반 영상 추정"]

brand_points = []

if not shorts_df.empty and not normal_df.empty:
    shorts_avg = shorts_df["조회수"].mean()
    normal_avg = normal_df["조회수"].mean()

    if shorts_avg > normal_avg:
        brand_points.append(
            f"현재 수집 결과에서는 쇼츠 추정 영상의 평균 조회수가 일반 영상보다 높습니다. 빠른 도달과 제품 발견 목적에는 쇼츠형 콘텐츠가 더 유리해 보입니다. 쇼츠 평균 {shorts_avg:,.0f}회, 일반 영상 평균 {normal_avg:,.0f}회."
        )

    else:
        brand_points.append(
            f"현재 수집 결과에서는 일반 영상 추정 콘텐츠의 평균 조회수가 쇼츠보다 높습니다. 성분 설명, 비교 리뷰, 사용 후기처럼 설득형 콘텐츠가 더 적합할 수 있습니다. 일반 영상 평균 {normal_avg:,.0f}회, 쇼츠 평균 {shorts_avg:,.0f}회."
        )

else:
    brand_points.append(
        "현재 수집 결과만으로는 쇼츠와 일반 영상의 성과 차이를 비교하기 어렵습니다."
    )

brand_points.append(
    "단순 제품 소개보다 가격 대비 효능, 실제 사용 검증, 피부 고민 해결, 비교 리뷰 구조가 마케터가 참고하기 좋은 방향입니다."
)

brand_points.append(
    "피부 개선, 전문가 추천, 의학적 효능처럼 보일 수 있는 표현은 브랜드 공식 콘텐츠에서 사용 전 내부 검토가 필요합니다."
)

brand_html = "".join([f"<li>{safe_html(point)}</li>" for point in brand_points])

st.markdown(
    f"""
    <div class="insight-card">
        <ul>
            {brand_html}
        </ul>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("### 제목 키워드 보조 분석")

keywords = get_top_keywords(df["영상 제목"].tolist(), top_n=10)

if keywords:
    keyword_html = ""

    for word, count in keywords:
        keyword_html += f'<span class="keyword-pill">{safe_html(word)} · {count}회</span>'

    st.markdown(keyword_html, unsafe_allow_html=True)

else:
    st.markdown("키워드 빈도를 계산할 수 없습니다.")


# =============================================================================
# Gemini 상세 인사이트
# =============================================================================
if analysis_mode in ["표준 분석", "정밀 분석"]:
    st.divider()
    st.markdown('<div class="section-title">🤖 AI 상세 인사이트</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-desc">실제 수집된 영상 데이터만 Gemini에 전달해 추가 해석을 생성합니다.</div>',
        unsafe_allow_html=True
    )

    with st.spinner("Gemini가 실제 수집 데이터만 바탕으로 상세 인사이트를 작성 중입니다..."):
        gemini_text = get_gemini_insight(df, keyword)

    st.markdown(gemini_text)


# =============================================================================
# 분석 대상 영상 테이블
# =============================================================================
st.divider()
st.markdown('<div class="section-title">📺 분석 대상 영상</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-desc">아래 목록은 입력한 키워드와 옵션에 따라 YouTube API에서 실제 수집한 영상입니다. 영상 보기를 누르면 유튜브로 이동합니다.</div>',
    unsafe_allow_html=True
)

display_df = df[
    [
        "순위",
        "영상 제목",
        "채널명",
        "조회수",
        "좋아요",
        "댓글",
        "댓글률(%)",
        "좋아요율(%)",
        "일평균 조회수",
        "업로드일",
        "포맷",
        "영상 보기",
    ]
].copy()

st.dataframe(
    display_df,
    column_config={
        "순위": st.column_config.NumberColumn("순위", format="%d"),
        "조회수": st.column_config.NumberColumn("조회수", format="%d"),
        "좋아요": st.column_config.NumberColumn("좋아요", format="%d"),
        "댓글": st.column_config.NumberColumn("댓글", format="%d"),
        "댓글률(%)": st.column_config.NumberColumn("댓글률(%)", format="%.3f"),
        "좋아요율(%)": st.column_config.NumberColumn("좋아요율(%)", format="%.3f"),
        "일평균 조회수": st.column_config.NumberColumn("일평균 조회수", format="%.1f"),
        "영상 보기": st.column_config.LinkColumn(
            "영상 보기",
            display_text="영상 보기",
        ),
    },
    hide_index=True,
    use_container_width=True,
)


# =============================================================================
# 보조 데이터
# =============================================================================
st.divider()
st.markdown('<div class="section-title">📊 보조 데이터</div>', unsafe_allow_html=True)

format_summary = df.groupby("포맷").agg(
    영상수=("영상 제목", "count"),
    평균조회수=("조회수", "mean"),
    평균댓글수=("댓글", "mean"),
    평균댓글률=("댓글률(%)", "mean"),
    평균일조회수=("일평균 조회수", "mean"),
).reset_index()

st.markdown("### 포맷별 평균 반응")

st.dataframe(
    format_summary,
    column_config={
        "평균조회수": st.column_config.NumberColumn("평균 조회수", format="%.0f"),
        "평균댓글수": st.column_config.NumberColumn("평균 댓글 수", format="%.0f"),
        "평균댓글률": st.column_config.NumberColumn("평균 댓글률(%)", format="%.3f"),
        "평균일조회수": st.column_config.NumberColumn("평균 일조회수", format="%.1f"),
    },
    hide_index=True,
    use_container_width=True,
)
