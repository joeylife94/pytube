# 🎬 YouTube 다운로더

yt-dlp 기반 YouTube 다운로더입니다. Streamlit 웹 UI와 REST API를 함께 제공합니다.
영상·MP3·원본 오디오를 받을 수 있고, 재생목록·채널·여러 URL·예약 다운로드를 지원합니다.
모든 다운로드는 백그라운드 대기열에서 처리되므로, 받는 동안에도 화면을 계속 쓸 수 있어요.

> 저장소 이름은 `pytube`지만 실제 다운로드는 유지보수가 활발한 **yt-dlp**가 합니다.
> pytube는 yt-dlp가 없을 때만 쓰는 예비 백엔드예요.

## 주요 기능

- **미리보기**: 썸네일, 제목, 채널, 길이, 조회수, 최대 화질, 예상 크기
- **형식 선택**: 🎬 영상(최고~360p) · 🎵 MP3 · 🎧 원본 오디오, 자막 받기
- **재생목록·채널**: 목록을 표로 불러와서 원하는 영상만 체크해서 받기. 이미 받은 영상은 자동으로 선택 해제
- **여러 URL**: 붙여넣거나 `.txt` 파일로 올리기. 중복 URL과 재생목록·채널 주소는 자동으로 걸러짐
- **예약 다운로드**: 정한 시각에 자동 시작
- **실시간 다운로드 현황**: 진행률·속도·남은 시간, 받는 중 취소, 실패한 항목 재시도, 완료된 파일을 폴더에서 열거나 브라우저로 내려받기
- **동시 다운로드** 1~8개, 속도 제한, 파일 이름 템플릿, 프록시, 쿠키(브라우저 또는 `cookies.txt`)
- **안전한 저장**: 받은 파일을 덮어쓰지 않아요. 이름이 겹치면 `제목 (1).mp4`처럼 저장돼요
- **설정 기억**: 마지막 설정이 `downloads/.app_settings.json`에 저장돼요

## 빠른 시작

Python **3.10 이상**이 필요해요.

```bash
python -m pip install -r requirements.txt
```

```bash
streamlit run app.py
```

브라우저에서 http://localhost:8501 이 열려요.

### 함께 설치하면 좋은 것

| 프로그램 | 용도 | 없으면 |
|---|---|---|
| **ffmpeg** | MP3 변환, 고화질 영상+소리 합치기 | MP3 변환이 안 되고, 영상이 낮은 화질로 받아질 수 있어요 |
| **Node.js** | YouTube 보호 영상 해석 (yt-dlp-ejs와 함께 사용) | 일부 영상이 실패할 수 있어요 |

Windows에서는 `winget install Gyan.FFmpeg`와 `winget install OpenJS.NodeJS.LTS`로 설치할 수 있어요.
ffmpeg를 PATH에 넣지 않았다면 환경변수 `FFMPEG_LOCATION`(또는 `FFMPEG_PATH`/`FFMPEG_BIN`)에
ffmpeg 실행 파일이나 그 폴더 경로를 지정하세요.

앱 상단 배지에서 yt-dlp·ffmpeg·JS 해석기 상태를 확인할 수 있어요.

## 로그인이 필요한 영상

"로그인이 필요해요" 오류가 나면 사이드바 **🍪 로그인 · 네트워크**에서 다음 중 하나를 설정하세요.

- **브라우저 쿠키**: YouTube에 로그인된 브라우저를 고르면 돼요. Windows의 Chrome·Edge는 쿠키 암호화 때문에 실패할 수 있어서 Firefox를 권장해요.
- **cookies.txt 업로드**: 브라우저 확장(예: *Get cookies.txt LOCALLY*)으로 내보낸 Netscape 형식 파일을 올리면 돼요.

프로젝트 폴더에 `cookies.txt`나 `www.youtube.com_cookies.txt`가 있으면 자동으로 써요.
쿠키 파일은 `.gitignore`와 `.dockerignore`에 들어 있어서 커밋되거나 Docker 이미지에 들어가지 않아요.

## REST API

```bash
python api_server.py --port 8000
```

- 기본은 이 PC에서만 접속돼요(`127.0.0.1`). 다른 기기에서 쓰려면 `--host 0.0.0.0`과 함께 환경변수 `API_TOKEN`을 설정하세요. 그러면 요청마다 `X-API-Key: <토큰>`(또는 `Authorization: Bearer <토큰>`) 헤더가 필요해요.
- `cookiefile`에는 프로젝트 폴더나 `downloads` 폴더 안의 파일만 지정할 수 있어요.
- 엔드포인트 목록과 예시는 http://localhost:8000/docs 와 앱의 「🔌 API」 탭에 있어요.

```bash
curl -X POST http://localhost:8000/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "audio_only": true, "convert_mp3": true}'
```

## Docker

```bash
docker compose up -d --build
```

- 웹 UI: http://localhost:8501 · API: http://localhost:8000
- 받은 파일은 `./downloads`에 저장돼요. 이미지에 ffmpeg와 Node.js가 들어 있어요.
- API 토큰을 쓰려면 `API_TOKEN=... docker compose up -d`처럼 실행하세요.

## 환경변수

| 이름 | 설명 |
|---|---|
| `PYTUBE_DOWNLOAD_DIR` | 기본 저장 폴더 (기본값: `./downloads`). 대기열·설정 파일도 여기에 저장돼요 |
| `FFMPEG_LOCATION` | ffmpeg 실행 파일 또는 폴더 경로 |
| `API_TOKEN` | 설정하면 API 요청에 토큰이 필요해요 |
| `CORS_ORIGINS` | API의 CORS 허용 출처 (쉼표 구분, 기본값 `*`) |

## 개발

```bash
python -m pip install -r dev-requirements.txt
```

```bash
python -m pytest -q tests
```

- `tests/test_app_ui.py`는 Streamlit `AppTest`로 네트워크 없이 UI를 검증해요.
- CI(GitHub Actions)는 Python 3.12·3.13에서 테스트를 돌리고, Playwright로 UI 스모크 테스트를 해요 (`scripts/playwright_test.py`).

### 구조

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit UI |
| `app_helpers.py` | UI용 순수 함수 (설정 저장, URL 파싱, 서식, 오류 메시지) |
| `api_server.py` | FastAPI REST API |
| `download_core.py` | yt-dlp 옵션과 다운로드 실행 (모든 경로가 여기로 모여요) |
| `download_queue.py` | 동시 다운로드 워커, 예약·취소·재시도, 상태 저장 |
| `queue_download_adapter.py` | 대기열 항목 → `download_core` 연결 |
| `download_db.py` | 다운로드 기록과 중복 검사 |
| `download_errors.py` | 오류 분류 (재시도 가능 여부 등) |
| `pytube_helper.py` | 메타데이터·재생목록·채널 추출, 이전 버전 호환 함수 |
