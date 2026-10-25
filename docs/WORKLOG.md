# Worklog — 2025-10-16 / 2025-10-17

This file summarizes the debugging and fixes performed, and lists next steps for follow-up work.

## Summary of work done

- Inspected project and ran unit tests locally.
- Reproduced pytube HTTP 400 error for some short/youtu.be URLs.
- Implemented URL normalization (`_normalize_video_url`) in `pytube_helper.py` to convert short/shorts URLs to `watch?v=` form.
- Added a yt-dlp fallback for metadata extraction and downloads when pytube fails.
- Improved `pytube_helper.py` logging and clearer error messages.
- Made Streamlit UI improvements in `app.py`:
  - Cache fetched streams in `st.session_state` so the download UI remains visible across reruns.
  - Add `show_live_progress` checkbox to optionally run yt-dlp inline so users see live progress in the UI.
  - Default output folder now `downloads/` and created if missing.
- Added Playwright automation scripts to reproduce UI flows and capture screenshots:
  - `scripts/playwright_test.py`
  - `scripts/playwright_debug.py`
- Installed `yt-dlp` and (local) ffmpeg for testing; reprocessed a downloaded file with ffmpeg to fix container issues.
- Moved existing downloaded media from repo root into `downloads/`.
- Cleaned repository: added `.gitignore` and untracked generated artifacts (screenshots, ffmpeg dir).
- Created `CHANGELOG.md` and updated `README.md` to cover new usage and notes.
- Added GitHub Actions workflow `.github/workflows/python-tests.yml` to run pytest on push.
- Ran full test suite: `2 passed, 1 warning`.
- Created and pushed tag `v0.1.0`.

## Files changed / added (high-level)

- Modified: `pytube_helper.py`, `app.py`, `tests/test_pytube_helper.py`, `README.md`
- Added: `CHANGELOG.md`, `WORKLOG.md`, `scripts/playwright_test.py`, `scripts/playwright_debug.py`, `.gitignore`, `.github/workflows/python-tests.yml`
- Created: `downloads/` folder and moved media files into it during cleanup

## Next steps / TODOs

1. Commit/verify CI workflow runs successfully on GitHub Actions (check run and logs).
2. Optional: add Playwright test job to CI (requires headless browser support and test failure handling).
3. Optional: implement server-side shared progress (file or websocket) so background downloads update any open UI session reliably.
4. Add `DEV_SETUP.md` / `CONTRIBUTING.md` with quick start (venv, pip install, playwright install steps).
5. If desired, create a GitHub Release from tag `v0.1.0` (CHANGELOG content can be used as release notes).

## Notes

- The project uses pytube but falls back to yt-dlp in cases where pytube fails; installing `yt-dlp` in your venv is recommended for robustness.
- Local ffmpeg was used for testing; avoid committing binaries to the repo. Use `.gitignore` to keep them out of version control.

---

# 작업 기록 / TODO (요약)

## 다음에 할 일 (우선순위 높은 항목들)

1. CI 실행 확인
  - GitHub Actions에 추가한 워크플로우가 정상적으로 동작하는지 확인하고, 실패 시 로그 분석.
2. DEV_SETUP.md 작성
  - 가상환경, 의존성 설치, Playwright 설치(브라우저 포함) 방법 정리.
3. 서버-사이드 진행 상태 공유(선택)
  - 배경 다운로드가 열린 UI 세션들에 안정적으로 반영되도록 파일 기반 또는 웹소켓 기반의 진행 상태 채널 설계/구현.

---

# 작업 이력 (시간 순서: 오래된 항목 먼저 -> 최신 항목 마지막)

1) 프로젝트 점검 및 초기 테스트
  - 저장소 파일들을 검토하고 `pytest`로 기본 테스트를 실행하여 환경을 확인했습니다.

2) 버그 재현 및 원인 조사
  - 특정 짧은 형태의 YouTube URL(예: `youtu.be/...` + 쿼리 파라미터)에서 pytube의 innertube 호출이 HTTP 400을 반환하는 문제를 재현했습니다.
  - 문제의 전체 traceback을 캡처해 원인(innertube 요청/잘못된 URL 형태) 을 분석했습니다.

3) `pytube_helper.py` 개선
  - `_normalize_video_url(url)` 함수를 추가하여 `youtu.be` 및 `/shorts/` 형식을 `https://www.youtube.com/watch?v=<id>`로 정규화하도록 했습니다.
  - pytube로 메타데이터를 가져오는데 실패할 경우(예: HTTP 400), `yt-dlp`가 설치되어 있으면 yt-dlp로 메타데이터를 추출/대체하도록 페일백 로직을 추가했습니다.
  - 로깅을 추가하고, 사용자에게 전달할 수 있는 명확한 에러 메시지를 개선했습니다.

4) Streamlit UI 개선 (`app.py`)
  - `st.session_state`에 가져온 스트림/메타데이터를 캐시해 Streamlit의 재실행(리렌더)에도 다운로드 UI가 사라지지 않도록 수정했습니다.
  - "Show live progress in UI (blocks UI while downloading)" 체크박스를 추가하여, 사용자가 원하면 yt-dlp 다운로드를 메인 스레드에서 실행해 UI에서 실시간 진행을 볼 수 있게 했습니다.
  - 출력 폴더 기본값을 빈칸일 때 `downloads/` 폴더로 설정하고, 없으면 자동 생성하도록 했습니다.

5) yt-dlp 및 ffmpeg 도입 테스트
  - `yt-dlp`를 venv에 설치하고, yt-dlp로 메타데이터 추출 및 다운로드를 수행해 pytube 실패 케이스를 우회하는 것을 검증했습니다.
  - 로컬(레포지토리 내부) 사용자용으로 ffmpeg(정적 빌드)를 내려받아 `scripts/ffmpeg/`에 넣고, ffmpeg가 있는 환경에서 pydub 변환이 가능함을 확인했습니다.
  - ffmpeg로 다운로드한 파일을 빠른 카피(-c copy) 방식으로 재포장해 컨테이너/타임스탬프 경고를 제거했습니다.

6) UI 재현 자동화(Playwright)
  - Playwright를 설치하고 Chromium을 받아 `scripts/playwright_test.py`와 `scripts/playwright_debug.py`를 작성했습니다.
  - 자동화로 Streamlit 페이지에 접속해 URL 입력 → Start download → metadata 로드 대기 → "Download video now (yt-dlp)" 클릭까지 재현하고, 진행 상태의 스크린샷을 캡처해 `scripts/screenshots/`에 저장했습니다.

7) 저장소 정리 및 문서
  - 잘못 커밋되거나 추적되던 다운로드/스크린샷 파일을 `downloads/`로 이동하고, `.gitignore`를 추가해 자동생성물과 바이너리가 추적되지 않도록 했습니다.
  - `README.md`와 `CHANGELOG.md`를 업데이트/추가해 변경사항과 사용법을 정리했습니다.
  - 오늘 작업을 정리한 `WORKLOG.md`(이 파일)를 추가했습니다.

8) 버전 태그 및 원격 업로드
  - 로컬에서 수정사항을 커밋하고 `origin/main`으로 푸시했습니다.
  - 릴리스 태그 `v0.1.0`을 생성하고 원격에 푸시했습니다.

---

필요하면 다음에 제가 도와드릴 수 있는 작업

- CI(Playwright 포함) 자동화 워크플로 추가 및 디버그
- 서버-사이드 진행 상태 채널 설계/구현
- `DEV_SETUP.md` 및 `CONTRIBUTING.md` 작성
- GitHub Release 생성(CHANGELOG 기반)

원하시면 이 파일을 바로 커밋하고 푸시하겠습니다.