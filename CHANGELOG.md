# Changelog

All notable changes to this project are documented here.

## 2026-10-18 — UI 개편 · 최신화

### UI
- Streamlit UI를 새로 짰어요 (한국어). 형식·화질 옵션을 상단 한 곳에 모으고, 고급 설정은 사이드바로 옮겼어요.
- 모든 다운로드가 백그라운드 대기열로 가요. 받는 동안 화면이 멈추지 않고, 하단 「다운로드 현황」이 실시간으로 갱신돼요 (진행률·속도·남은 시간·취소·재시도·브라우저로 받기).
- 영상 URL을 넣으면 미리보기가 자동으로 떠요 (조회수, 최대 화질, 예상 크기 포함). 「정보 가져오기」 단계를 없앴어요.
- 재생목록·채널 영상을 표에서 골라서 받을 수 있어요. 이미 받은 영상은 자동으로 선택 해제돼요.
- 오류를 한국어 안내로 보여줘요 (쿠키 필요, 지역 제한, 삭제된 영상 등).
- 설정이 `downloads/.app_settings.json`에 저장돼서 다음에 열어도 유지돼요.
- 좁은 창에서도 레이아웃이 깨지지 않아요.

### 버그 수정
- 오디오를 받을 때 같은 이름의 기존 영상 파일을 삭제하던 문제를 고쳤어요. 이제 다운로드마다 임시 폴더에서 받은 뒤 옮기고, 이름이 겹치면 `(1)`을 붙여요.
- 대기열의 동시 다운로드 설정이 무시되던 문제를 고쳤어요 (워커가 1개뿐이었어요).
- 브라우저 탭마다 대기열이 따로 생겨 `.queue.json`을 서로 덮어쓰던 문제를 고쳤어요.
- 재생목록 순서 파일 이름이 `NA_제목`으로 나오던 문제를 고쳤어요.
- `watch?v=…&list=…` 주소를 넣으면 재생목록 전체가 받아질 수 있던 문제를 고쳤어요.
- 재시도·파일 열기 버튼이 눌러도 동작하지 않던 문제가 새 UI에서 없어졌어요.
- `FFMPEG_LOCATION`으로만 ffmpeg를 지정한 경우에도 ffmpeg가 있다고 인식해요.

### 다운로드
- 같은 화질이면 mp4/m4a를 우선해서 받아요 (예전에는 webm으로 받아지는 경우가 많았어요).
- 강제로 지정하던 android/ios 클라이언트, 오래된 User-Agent, `nocheckcertificate` 설정을 없앴어요.
- `yt-dlp[default]>=2026.8.19`를 쓰고, JS 해석기(yt-dlp-ejs)는 로컬 패키지를 써요.
- pytube·pydub을 필수 의존성에서 뺐어요 (yt-dlp가 없을 때만 쓰는 예비 백엔드로 남겨뒀어요).

### API · 보안
- 기본 바인딩을 `127.0.0.1`로 바꿨어요. `API_TOKEN`을 설정하면 토큰 인증을 해요.
- `cookiefile`은 프로젝트·downloads 폴더 안의 파일만 허용해요 (yt-dlp가 이 파일을 다시 쓰기 때문에 임의 경로를 허용하면 아무 파일이나 덮어쓸 수 있었어요).
- API 대기열을 `.api_queue.json`으로 분리했어요.
- `/api/info`가 yt-dlp 메타데이터를 반환하고, 대기열 응답에 속도·남은 시간이 들어가요.
- Docker 이미지에 Node.js를 넣었고, 쿠키 파일이 이미지에 들어가지 않게 했어요.

### 개발
- Streamlit 1.66, FastAPI 0.143, uvicorn 0.54, pytest 9, Playwright 1.64 기준으로 최신화했어요.
- CI가 Python 3.12·3.13에서 테스트하고, pip 캐시를 써요.
- UI 테스트(`AppTest`)와 대기열·API 보안·다운로드 코어 테스트를 추가했어요.

## Unreleased (2025-10-16)

- Fix: Normalize YouTube URLs (convert `youtu.be` and `/shorts/` to standard `watch?v=`) to reduce pytube innertube HTTP 400 errors.
- Fix: Add `yt-dlp` fallback for metadata extraction and downloads when pytube fails.
- Improvement: Cache fetched streams in `st.session_state` to keep download UI visible across Streamlit reruns.
- Improvement: Default output folder set to `downloads/` (created automatically when blank).
- Feature: Add Playwright automation scripts (`scripts/playwright_test.py`, `scripts/playwright_debug.py`) to reproduce UI interactions and capture screenshots for debugging.
- Misc: Move existing downloaded media into `downloads/` during cleanup.


## Previous

- Initial project scaffolding and Streamlit GUI for pytube-based downloads.
