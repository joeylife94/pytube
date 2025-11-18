"""
DownloaderManager Streamlit 데모 앱
4가지 다운로드 모드를 브라우저에서 테스트할 수 있습니다.
"""

import streamlit as st
from downloader_manager import DownloaderManager
import os
from pathlib import Path

# 페이지 설정
st.set_page_config(
    page_title="YouTube Downloader",
    page_icon="📥",
    layout="wide"
)

# 제목
st.title("📥 YouTube Downloader - DownloaderManager")
st.markdown("---")

# 사이드바 - 설정
with st.sidebar:
    st.header("⚙️ 설정")
    
    output_dir = st.text_input(
        "다운로드 폴더",
        value="downloads",
        help="파일이 저장될 폴더 경로"
    )
    
    preferred_engine = st.selectbox(
        "선호 엔진",
        options=["yt-dlp", "pytube"],
        help="video 모드에서 사용할 엔진 (MP3/자막 모드는 자동으로 yt-dlp 사용)"
    )
    
    max_workers = st.slider(
        "동시 다운로드 수",
        min_value=1,
        max_value=5,
        value=3,
        help="배치 다운로드 시 동시에 처리할 개수"
    )
    
    st.markdown("---")
    st.info("""
    **💡 엔진 선택 규칙:**
    - video 모드: 선호 엔진 사용
    - mp3 모드: yt-dlp 자동 강제
    - video_subs: yt-dlp 자동 강제
    - subs_only: yt-dlp 자동 강제
    """)

# 메인 영역
col1, col2 = st.columns([2, 1])

with col1:
    st.header("📹 URL 입력")
    
    # URL 입력 방식 선택
    input_mode = st.radio(
        "입력 방식",
        options=["단일 URL", "배치 다운로드 (여러 URL)"],
        horizontal=True
    )
    
    if input_mode == "단일 URL":
        url = st.text_input(
            "YouTube URL",
            placeholder="https://youtu.be/...",
            help="다운로드할 YouTube 비디오 URL"
        )
        urls = [url] if url else []
    else:
        urls_text = st.text_area(
            "YouTube URLs (한 줄에 하나씩)",
            height=150,
            placeholder="https://youtu.be/...\nhttps://youtu.be/...\nhttps://youtu.be/...",
            help="여러 URL을 입력하세요 (줄바꿈으로 구분)"
        )
        urls = [u.strip() for u in urls_text.split('\n') if u.strip()]

with col2:
    st.header("🎯 다운로드 모드")
    
    mode = st.radio(
        "모드 선택",
        options=[
            "video",
            "mp3",
            "video_subs",
            "subs_only"
        ],
        format_func=lambda x: {
            "video": "📹 비디오 (MP4)",
            "mp3": "🎵 오디오 (MP3)",
            "video_subs": "📹📝 비디오 + 자막",
            "subs_only": "📝 자막만"
        }[x],
        help="다운로드 모드를 선택하세요"
    )
    
    st.markdown("---")
    
    # 모드별 설명
    mode_descriptions = {
        "video": "비디오를 MP4 형식으로 다운로드합니다.",
        "mp3": "오디오를 추출하여 MP3로 변환합니다. (ffmpeg 필요)",
        "video_subs": "비디오와 함께 자막을 다운로드합니다. (영어/한국어 우선)",
        "subs_only": "비디오는 건너뛰고 자막만 다운로드합니다."
    }
    
    st.info(f"**선택한 모드:**\n\n{mode_descriptions[mode]}")

# 다운로드 버튼
st.markdown("---")

if st.button("🚀 다운로드 시작", type="primary", use_container_width=True):
    if not urls:
        st.error("❌ URL을 입력해주세요!")
    else:
        # DownloaderManager 초기화
        manager = DownloaderManager(
            output_dir=output_dir,
            preferred_engine=preferred_engine,
            max_workers=max_workers
        )
        
        # 진행 상태 표시
        st.markdown("### 📊 다운로드 진행 상황")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 다운로드 실행
        if len(urls) == 1:
            # 단일 다운로드
            status_text.text(f"다운로드 중: {urls[0]}")
            result = manager.download_single(urls[0], mode=mode)
            results = [result]
        else:
            # 배치 다운로드
            status_text.text(f"{len(urls)}개 URL 배치 다운로드 중...")
            results = manager.download_batch(urls, mode=mode)
        
        progress_bar.progress(1.0)
        
        # 결과 표시
        st.markdown("---")
        st.markdown("### 📋 다운로드 결과")
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        # 요약
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("전체", len(results))
        with col2:
            st.metric("✅ 성공", len(successful))
        with col3:
            st.metric("❌ 실패", len(failed))
        
        # 성공한 다운로드
        if successful:
            st.markdown("#### ✅ 성공한 다운로드")
            for i, result in enumerate(successful, 1):
                with st.expander(f"#{i} - {result.url[:60]}..."):
                    st.success(f"**파일:** `{result.file_path}`")
                    st.info(f"**엔진:** {result.engine}")
                    
                    # 파일 크기 표시
                    if result.file_path and os.path.exists(result.file_path):
                        size_mb = os.path.getsize(result.file_path) / (1024 * 1024)
                        st.metric("파일 크기", f"{size_mb:.2f} MB")
        
        # 실패한 다운로드
        if failed:
            st.markdown("#### ❌ 실패한 다운로드")
            for i, result in enumerate(failed, 1):
                with st.expander(f"#{i} - {result.url[:60]}..."):
                    st.error(f"**에러:** {result.error}")
                    st.info(f"**엔진:** {result.engine}")

# 하단 정보
st.markdown("---")

with st.expander("ℹ️ 사용 방법 및 정보"):
    st.markdown("""
    ### 📖 사용 방법
    
    1. **URL 입력**: 단일 URL 또는 여러 URL을 입력하세요
    2. **모드 선택**: 원하는 다운로드 모드를 선택하세요
    3. **설정 조정**: 사이드바에서 엔진, 폴더, 동시 다운로드 수를 설정하세요
    4. **다운로드**: "다운로드 시작" 버튼을 클릭하세요
    
    ### 🎯 4가지 다운로드 모드
    
    - **📹 video**: 일반 비디오 다운로드 (MP4)
    - **🎵 mp3**: 오디오 추출 + MP3 변환 (yt-dlp 자동 사용)
    - **📹📝 video_subs**: 비디오 + 자막 다운로드 (yt-dlp 자동 사용)
    - **📝 subs_only**: 자막만 다운로드 (비디오 건너뛰기, yt-dlp 자동 사용)
    
    ### ⚙️ 하이브리드 엔진 로직
    
    - **video 모드**: 사용자가 선택한 엔진 사용 (pytube 또는 yt-dlp)
    - **mp3/자막 모드**: 자동으로 yt-dlp 사용 (pytube는 이 기능 미지원)
    
    ### ⚠️ 주의사항
    
    - MP3 변환에는 시스템에 ffmpeg가 설치되어 있어야 합니다
    - YouTube의 봇 탐지로 인해 HTTP 403/429 에러가 발생할 수 있습니다
    - 배치 다운로드 시 일부 실패해도 나머지는 계속 진행됩니다
    
    ### 📦 시스템 정보
    
    - **DownloaderManager**: 동시 다운로드 지원 (ThreadPoolExecutor)
    - **엔진**: pytube (빠른 비디오) + yt-dlp (고급 기능)
    - **에러 처리**: 개별 실패가 전체 배치에 영향 없음
    """)

with st.expander("🔧 기술 스택"):
    st.markdown("""
    - **Backend**: DownloaderManager (Python)
    - **Download Engines**: pytube + yt-dlp
    - **Concurrency**: ThreadPoolExecutor
    - **Frontend**: Streamlit
    - **Audio Conversion**: ffmpeg
    
    **구현된 기능:**
    - ✅ 배치 다운로드 (동시 처리)
    - ✅ MP3 변환 (자동 yt-dlp)
    - ✅ 비디오 + 자막
    - ✅ 자막만 다운로드
    - ✅ 하이브리드 엔진 선택
    - ✅ 완벽한 에러 처리
    """)

# 푸터
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "DownloaderManager v1.0 | Made with ❤️ using Streamlit"
    "</div>",
    unsafe_allow_html=True
)
