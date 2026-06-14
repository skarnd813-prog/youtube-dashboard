import streamlit as st
import pandas as pd
from collections import Counter, defaultdict
import re
import os
import datetime
from urllib.parse import urlparse, parse_qs

from googleapiclient.discovery import build
import google.generativeai as genai


# -----------------------------------------------------------------------------
# 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="YouTube Marketing Dashboard", layout="wide")
st.title("📊 YouTube Marketing Dashboard")


def read_secret(name: str) -> str:
    try:
        return st.secrets.get(name, os.environ.get(name, ""))
    except Exception:
        return os.environ.get(name, "")


YOUTUBE_API_KEY = read_secret("YOUTUBE_API_KEY")
GEMINI_API_KEY = read_secret("GEMINI_API_KEY")


# -----------------------------------------------------------------------------
# 유틸 함수
# -----------------------------------------------------------------------------
def extract_video_id(text: str):
    """유튜브 URL에서 videoId 추출. 키워드면 None 반환."""
    try:
        parsed = urlparse(text.strip())

        if "youtu.be" in parsed.netloc:
            return parsed.path.strip("/").split("/")[0]

        if "youtube.com" in parsed.netloc:
            if parsed.path == "/watch":
                return parse_qs(parsed.query).get("v", [None])[0]

            if parsed.path.startswith("/shorts/"):
                return parsed.path.split("/shorts/")[1].split("/")[0]

            if parsed.path.startswith("/embed/"):
                return parsed.path.split("/embed/")[1].split("/")[0]

    except Exception:
        return None

    return None


def parse_iso8601_duration_to_seconds(duration: str) -> int:
    """PT1M30S 같은 YouTube duration을 초로 변환."""
    if not duration:
        return 0

    pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
    match = re.match(pattern, duration)

    if not match:
        return 0

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * 3600 + minutes * 60 + seconds


def get_published_after(period_option: str):
    now = datetime.datetime.utcnow()

    if period_option == "최근 1개월":
        target = now - datetime.timedelta(days=30)
    elif period_option == "최근 3개월":
        target = now - datetime.timedelta(days=90)
    elif period_option == "최근 6개월":
        target = now - datetime.timedelta(days=180)
    elif period_option == "최근 1년":
        target = now - datetime.timedelta(days=365)
    else:
        return None

    return target.replace(microsecond=0).isoformat("T") + "Z"


def get_top_keywords(titles, top_n=10):
    stopwords = {
        "다이소", "화장품", "관련", "영상", "추천", "리뷰", "그리고",
        "진짜", "너무", "있는", "없는", "하는", "하면", "이거", "그냥"
    }

    words = []
    for title in titles:
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", str(title))
        for word in cleaned.split():
            if len(word) > 1 and word not in stopwords:
                words.append(word)

    return Counter(words).most_common(top_n)


def classify_title_hook(title: str):
    title = str(title)

    categories = []

    if any(k in title for k in ["원가", "가격", "가성비", "저렴", "천원", "만원", "비싼", "싼"]):
        categories.append("가격/가성비 후킹")

    if any(k in title for k in ["성분", "피부", "좋아지는", "효과", "보습", "진정", "장벽", "트러블"]):
        categories.append("성분/피부 고민 후킹")

    if any(k in title for k in ["추천", "의사", "피부과", "원장", "전문가"]):
        categories.append("전문가/추천 후킹")

    if any(k in title for k in ["안 써보면", "모르는", "비밀", "진짜", "될까", "충격", "꼭"]):
        categories.append("호기심/검증 후킹")

    if any(k in title for k in ["메이크업", "학생", "데일리", "템", "꿀템", "필수템"]):
        categories.append("상황/루틴형 콘텐츠")

    if not categories:
        categories.append("일반 제품 소개형")

    return categories


# -----------------------------------------------------------------------------
# YouTube API 데이터 수집
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def fetch_youtube_data(query_or_url, max_videos, order, period_option, include_shorts):
    if not YOUTUBE_API_KEY:
        return "API_KEY_MISSING", None

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        maybe_video_id = extract_video_id(query_or_url)

        if maybe_video_id:
            video_ids = [maybe_video_id]
        else:
            request_params = {
                "q": query_or_url,
                "part": "id,snippet",
                "type": "video",
                "maxResults": 50 if not include_shorts else max_videos,
                "order": order,
            }

            published_after = get_published_after(period_option)
            if published_after:
                request_params["publishedAfter"] = published_after

            search_response = youtube.search().list(**request_params).execute()
            items = search_response.get("items", [])

            video_ids = []
            for item in items:
                video_id = item.get("id", {}).get("videoId")
                if video_id:
                    video_ids.append(video_id)

            if not video_ids:
                return "NO_RESULTS", None

        videos_response = youtube.videos().list(
            id=",".join(video_ids),
            part="snippet,statistics,contentDetails"
        ).execute()

        items_by_id = {item.get("id"): item for item in videos_response.get("items", [])}

        today = datetime.date.today()
        rows = []

        for video_id in video_ids:
            item = items_by_id.get(video_id)

            if not item:
                continue

            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            content_details = item.get("contentDetails", {})

            title = snippet.get("title", "")
            channel = snippet.get("channelTitle", "")
            published_at = snippet.get("publishedAt", "")[:10]

            duration = content_details.get("duration", "")
            duration_seconds = parse_iso8601_duration_to_seconds(duration)

            # 단순 추정: 60초 이하를 쇼츠로 분류
            is_shorts = duration_seconds <= 60 and duration_seconds > 0

            if not include_shorts and is_shorts:
                continue

            try:
                pub_date = datetime.datetime.strptime(published_at, "%Y-%m-%d").date()
                days_elapsed = max((today - pub_date).days, 1)
            except Exception:
                days_elapsed = 1

            views = int(statistics.get("viewCount", 0))
            comments = int(statistics.get("commentCount", 0))

            like_count_raw = statistics.get("likeCount")
            likes = int(like_count_raw) if like_count_raw is not None else None

            video_url = f"https://www.youtube.com/watch?v={video_id}"

            rows.append({
                "영상 제목": title,
                "채널명": channel,
                "조회수": views,
                "좋아요": likes,
                "댓글": comments,
                "업로드일": published_at,
                "videoId": video_id,
                "영상 보기": video_url,
                "영상 URL": video_url,
                "경과일": days_elapsed,
                "일평균 조회수": round(views / days_elapsed, 1),
                "댓글률": round(comments / views * 100, 3) if views > 0 else 0,
                "좋아요율": round(likes / views * 100, 3) if likes is not None and views > 0 else None,
                "포맷": "쇼츠 추정" if is_shorts else "일반 영상 추정",
                "영상 길이초": duration_seconds,
            })

        if not rows:
            return "NO_RESULTS_AFTER_FILTER", None

        df = pd.DataFrame(rows)

        # 현재 정렬 기준 반영
        if order == "viewCount":
            df = df.sort_values("조회수", ascending=False)
        elif order == "date":
            df = df.sort_values("업로드일", ascending=False)
        else:
            df = df.reset_index(drop=True)

        df = df.head(max_videos).reset_index(drop=True)
        df.insert(0, "순위", range(1, len(df) + 1))

        if "videoId" not in df.columns or df["videoId"].isna().any():
            return "VIDEO_ID_MISSING", None

        return "SUCCESS", df

    except Exception as e:
        return f"API_CALL_FAILED: {str(e)}", None


# -----------------------------------------------------------------------------
# Gemini 마케팅 인사이트
# -----------------------------------------------------------------------------
def get_gemini_marketing_insight(df, query):
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되어 있지 않아 AI 인사이트를 생성할 수 없습니다."

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")

        context_cols = [
            "영상 제목", "채널명", "조회수", "좋아요", "댓글",
            "업로드일", "댓글률", "좋아요율", "일평균 조회수", "포맷", "영상 URL"
        ]

        context_df = df[context_cols].copy()
        context = context_df.to_string(index=False)

        prompt = f"""
당신은 뷰티/리테일 마케팅 전략가입니다.

아래는 사용자가 "{query}"로 검색해서 실제 YouTube API로 수집한 영상 데이터입니다.
절대 없는 영상, 없는 수치, 없는 사실을 지어내지 마세요.
반드시 제공된 데이터 안에서만 해석하세요.

데이터:
{context}

아래 구조로 실무형 마케팅 인사이트를 작성하세요.

1. 조회수 상위 영상의 성공 패턴
- 제목 후킹 방식
- 콘텐츠 소재
- 왜 클릭을 유도했을 가능성이 높은지

2. 댓글률이 높은 영상의 대화 유발 요소
- 댓글이 달릴 만한 논쟁/궁금증/공감 포인트

3. 마케터가 바로 참고할 콘텐츠 기획 방향 3개
- 각 기획 방향마다 예시 제목 1개씩 제안
- 단, 실제 영상 제목을 그대로 베끼지 말 것

4. 브랜드/제품 마케팅 관점의 시사점
- 가격, 성분, 후기, 추천, 전문가성, 루틴 중 어떤 메시지가 유리해 보이는지

5. 피해야 할 뻔한 방향
- 데이터상 반응이 약해 보이는 접근 또는 너무 흔한 접근
"""

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"Gemini 연산 중 에러가 발생했습니다: {str(e)}"


# -----------------------------------------------------------------------------
# 사이드바 옵션
# -----------------------------------------------------------------------------
st.sidebar.header("🛠️ 분석 옵션 설정")

analysis_mode = st.sidebar.selectbox(
    "분석 모드 선택",
    ["빠른 분석", "표준 분석", "정밀 분석"],
    index=0
)

if analysis_mode == "빠른 분석":
    default_max = 10
elif analysis_mode == "표준 분석":
    default_max = 20
else:
    default_max = 50

max_videos = st.sidebar.slider("최대 영상 수", 1, 50, default_max)

period_option = st.sidebar.selectbox(
    "업로드 기간",
    ["전체", "최근 1개월", "최근 3개월", "최근 6개월", "최근 1년"],
    index=0
)

sort_label = st.sidebar.selectbox(
    "정렬 기준",
    ["관련성 순", "조회수 순", "최신순"],
    index=1
)

order_map = {
    "관련성 순": "relevance",
    "조회수 순": "viewCount",
    "최신순": "date",
}

order = order_map[sort_label]

include_shorts = st.sidebar.checkbox("쇼츠 포함", value=True)

if analysis_mode == "빠른 분석":
    st.sidebar.caption("빠른 분석은 Gemini 없이 YouTube 메타데이터 기반으로 분석합니다.")
elif analysis_mode == "표준 분석":
    st.sidebar.caption("표준 분석은 YouTube 메타데이터 + Gemini 요약을 제공합니다.")
else:
    st.sidebar.caption("정밀 분석은 더 많은 영상을 바탕으로 Gemini 인사이트를 제공합니다.")


# -----------------------------------------------------------------------------
# 입력창: 이 부분이 사라졌던 핵심
# -----------------------------------------------------------------------------
st.markdown("## 🔎 유튜브 링크 또는 키워드 분석")

with st.form("search_form", clear_on_submit=False):
    query_or_url = st.text_input(
        "분석할 유튜브 링크나 키워드를 입력하세요",
        placeholder="예: 다이소 화장품 또는 https://www.youtube.com/watch?v=..."
    )
    submitted = st.form_submit_button("분석 시작")

if not submitted:
    st.info("키워드 또는 유튜브 링크를 입력한 뒤 '분석 시작'을 눌러주세요.")
    st.stop()

query_or_url = query_or_url.strip()

if not query_or_url:
    st.warning("분석할 키워드 또는 유튜브 링크를 입력해주세요.")
    st.stop()


# -----------------------------------------------------------------------------
# 데이터 수집
# -----------------------------------------------------------------------------
st.info(f"'{query_or_url}' 기준으로 실제 YouTube 데이터를 수집합니다.")

with st.spinner("YouTube API에서 실제 영상 데이터를 가져오는 중입니다..."):
    status, df = fetch_youtube_data(
        query_or_url=query_or_url,
        max_videos=max_videos,
        order=order,
        period_option=period_option,
        include_shorts=include_shorts
    )

if status == "API_KEY_MISSING":
    st.error("YouTube API 키가 설정되어 있지 않습니다. Streamlit Secrets의 YOUTUBE_API_KEY를 확인하세요.")
    st.stop()

if status == "NO_RESULTS":
    st.warning("검색 결과가 없습니다. 키워드 또는 필터 조건을 변경해주세요.")
    st.stop()

if status == "NO_RESULTS_AFTER_FILTER":
    st.warning("필터 적용 후 남은 영상이 없습니다. 쇼츠 포함 여부 또는 업로드 기간을 변경해주세요.")
    st.stop()

if status == "VIDEO_ID_MISSING":
    st.error("영상 링크를 생성할 수 없습니다. YouTube API videoId 수집 로직을 확인해주세요.")
    st.stop()

if status.startswith("API_CALL_FAILED"):
    st.error("YouTube API 호출에 실패했습니다. API 키, 할당량, API 활성화 상태를 확인해주세요.")
    st.caption(status)
    st.stop()

if df is None or df.empty:
    st.error("실제 영상 데이터를 가져오지 못했습니다.")
    st.stop()

st.success("분석 완료!")


# -----------------------------------------------------------------------------
# A. 핵심 요약
# -----------------------------------------------------------------------------
st.divider()
st.markdown("## 📌 A. 핵심 요약")

avg_views = int(df["조회수"].mean())
avg_comments = int(df["댓글"].mean())

valid_likes = df["좋아요"].dropna()
avg_likes = int(valid_likes.mean()) if len(valid_likes) > 0 else None

latest_upload = df["업로드일"].max()

top_view_row = df.sort_values("조회수", ascending=False).iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("분석된 영상 수", f"{len(df)}개")
col2.metric("평균 조회수", f"{avg_views:,}회")
col3.metric("최신 업로드일", latest_upload)

col4, col5, col6 = st.columns(3)
col4.metric("평균 댓글 수", f"{avg_comments:,}개")
col5.metric("평균 좋아요 수", f"{avg_likes:,}개" if avg_likes is not None else "확인 불가")
col6.metric("쇼츠 포함 여부", "포함" if include_shorts else "제외")

st.markdown(
    f"🏆 **최고 인기 영상:** "
    f"[{top_view_row['영상 제목']}]({top_view_row['영상 URL']}) "
    f"({top_view_row['조회수']:,}회)"
)


# -----------------------------------------------------------------------------
# B. 바로 참고할 인기 영상
# -----------------------------------------------------------------------------
st.divider()
st.markdown("## 🔥 B. 바로 참고할 인기 영상")

def render_link_list(dataframe, value_col, value_suffix):
    for _, row in dataframe.iterrows():
        value = row[value_col]
        if isinstance(value, float):
            value_text = f"{value:,.2f}{value_suffix}"
        else:
            value_text = f"{value:,}{value_suffix}"

        st.markdown(
            f"- [{row['영상 제목']}]({row['영상 URL']})  \n"
            f"  `{row['채널명']}` · {value_text}"
        )

top_views = df.sort_values("조회수", ascending=False).head(3)
top_comment_rate = df[df["조회수"] > 0].sort_values("댓글률", ascending=False).head(3)
top_daily_views = df.sort_values("일평균 조회수", ascending=False).head(3)

c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("### 📈 조회수 TOP 3")
    render_link_list(top_views, "조회수", "회")

with c2:
    st.markdown("### 💬 댓글률 TOP 3")
    render_link_list(top_comment_rate, "댓글률", "%")

with c3:
    st.markdown("### ⚡ 일평균 조회수 TOP 3")
    render_link_list(top_daily_views, "일평균 조회수", "회/일")


# -----------------------------------------------------------------------------
# C. 마케터용 시사점
# -----------------------------------------------------------------------------
st.divider()
st.markdown("## 💡 C. 마케터용 시사점")

hook_counter = Counter()
hook_examples = defaultdict(list)

for _, row in df.iterrows():
    hooks = classify_title_hook(row["영상 제목"])
    for hook in hooks:
        hook_counter[hook] += 1
        if len(hook_examples[hook]) < 2:
            hook_examples[hook].append((row["영상 제목"], row["영상 URL"]))

st.markdown("### 1. 조회수 상위 영상에서 보이는 성공 패턴")

if hook_counter:
    for hook, count in hook_counter.most_common(5):
        st.markdown(f"**{hook}** · {count}개 영상에서 관찰")

        for title, url in hook_examples[hook]:
            st.markdown(f"- 근거 영상: [{title}]({url})")

st.markdown("### 2. 콘텐츠 기획에 바로 쓸 수 있는 포인트")

st.markdown("""
- **가격 대비 효능 비교형 콘텐츠**: 다이소 화장품은 가격 접근성이 강하므로, “저렴한데 실제로 쓸 만한가?” 구조가 유리합니다.
- **피부 고민 해결형 콘텐츠**: 단순 제품 소개보다 피부 좋아짐, 성분, 원가, 추천 같은 문제 해결형 제목이 클릭을 만들 가능성이 큽니다.
- **검증/실험형 콘텐츠**: “진짜 써도 될까?”, “안 써보면 모르는”, “비싼 제품 성분과 비교” 같은 검증형 포맷이 마케터 입장에서 참고 가치가 높습니다.
""")

st.markdown("### 3. 브랜드 마케팅 관점의 해석")

if "쇼츠 추정" in df["포맷"].values and "일반 영상 추정" in df["포맷"].values:
    shorts_avg = df[df["포맷"] == "쇼츠 추정"]["조회수"].mean()
    normal_avg = df[df["포맷"] == "일반 영상 추정"]["조회수"].mean()

    if shorts_avg > normal_avg:
        st.markdown("- 현재 결과에서는 **쇼츠형 콘텐츠의 평균 조회수 반응이 더 높게 나타납니다.** 빠른 도달용 콘텐츠로 쇼츠를 우선 검토할 수 있습니다.")
    else:
        st.markdown("- 현재 결과에서는 **일반 영상의 평균 조회수 반응이 더 높게 나타납니다.** 성분 설명, 비교 리뷰, 사용 후기처럼 설득형 콘텐츠에 적합해 보입니다.")
else:
    st.markdown("- 현재 수집 결과만으로는 쇼츠/일반 영상 간 성과 차이를 단정하기 어렵습니다.")

st.markdown("""
- 브랜드가 직접 콘텐츠를 만들 경우, 단순히 “제품 좋다”보다 **가격 대비 효능, 성분 비교, 실제 사용 검증** 구조가 더 설득력 있습니다.
- “피부과 의사 추천”, “전문가 추천”류 표현은 반응은 좋아 보일 수 있으나, 브랜드 공식 커뮤니케이션에서는 표현 리스크 검토가 필요합니다.
""")

st.markdown("### 4. 제목 키워드 보조 분석")

keyword_result = get_top_keywords(df["영상 제목"].tolist(), top_n=10)

if keyword_result:
    st.markdown(
        " · ".join([f"**{word}**({count}회)" for word, count in keyword_result])
    )
else:
    st.markdown("키워드 빈도를 계산할 수 없습니다.")


# -----------------------------------------------------------------------------
# Gemini 인사이트: 표준/정밀 분석에서만
# -----------------------------------------------------------------------------
if analysis_mode in ["표준 분석", "정밀 분석"]:
    st.divider()
    st.markdown("## 🤖 D. Gemini 기반 상세 인사이트")

    with st.spinner("Gemini가 실제 수집 데이터를 바탕으로 마케팅 인사이트를 작성 중입니다..."):
        insight = get_gemini_marketing_insight(df, query_or_url)

    st.markdown(insight)

    table_section_title = "## 📺 E. 이번 분석 대상 영상"
else:
    table_section_title = "## 📺 D. 이번 분석 대상 영상"


# -----------------------------------------------------------------------------
# 이번 분석 대상 영상
# -----------------------------------------------------------------------------
st.divider()
st.markdown(table_section_title)

st.caption(
    "아래 목록은 입력한 키워드와 옵션에 따라 YouTube API에서 실제로 수집한 영상입니다. "
    "각 영상의 제목을 확인하고, '영상 보기'를 눌러 직접 검증할 수 있습니다."
)

display_df = df[
    [
        "순위",
        "영상 제목",
        "채널명",
        "조회수",
        "좋아요",
        "댓글",
        "댓글률",
        "일평균 조회수",
        "업로드일",
        "포맷",
        "영상 보기",
    ]
].copy()

st.dataframe(
    display_df,
    column_config={
        "조회수": st.column_config.NumberColumn("조회수", format="%d"),
        "좋아요": st.column_config.NumberColumn("좋아요", format="%d"),
        "댓글": st.column_config.NumberColumn("댓글", format="%d"),
        "댓글률": st.column_config.NumberColumn("댓글률", format="%.3f%%"),
        "일평균 조회수": st.column_config.NumberColumn("일평균 조회수", format="%.1f"),
        "영상 보기": st.column_config.LinkColumn(
            "영상 보기",
            display_text="영상 보기"
        ),
    },
    hide_index=True,
    use_container_width=True
)


# -----------------------------------------------------------------------------
# 보조 데이터
# -----------------------------------------------------------------------------
st.divider()
st.markdown("## 📊 보조 데이터")

format_summary = df.groupby("포맷").agg(
    영상수=("영상 제목", "count"),
    평균조회수=("조회수", "mean"),
    평균댓글수=("댓글", "mean"),
    평균일조회수=("일평균 조회수", "mean"),
).reset_index()

st.markdown("### 포맷별 평균 반응")
st.dataframe(format_summary, hide_index=True, use_container_width=True)
