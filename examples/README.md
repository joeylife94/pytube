# examples

예전 `DownloaderManager` 데모와 수동 테스트 스크립트예요. 앱(`app.py`, `api_server.py`)은 이 폴더를 쓰지 않아요.

저장소 루트에서 실행하세요. 각 스크립트가 루트를 import 경로에 넣어서 `downloader_manager` 같은 앱 모듈을 찾아요.

```bash
python examples/quick_start_demo.py
```

| 파일 | 내용 |
|---|---|
| `quick_start_demo.py` | DownloaderManager 4가지 기능 데모 (기본은 실제로 받지 않는 dry-run) |
| `integration_examples.py` | Streamlit·Tkinter·CLI 연동 예시. 직접 실행하면 샘플 영상 하나를 실제로 받아요 |
| `demo_interactive.py` | URL과 모드를 입력받아 다운로드하는 대화형 데모 |
| `app_demo.py` | DownloaderManager용 Streamlit 데모 (`streamlit run examples/app_demo.py`) |
| `app_tkinter.py` | 예전 Tkinter GUI |
| `verify_features.py` | 다운로드 없이 설정·엔진 선택 확인 |
| `run_test.py`, `test_simple.py`, `test_downloader_manager.py` | 실제로 다운로드하는 수동 테스트 스크립트 |

`test_*.py` 파일도 pytest가 모으지 않아요. `pytest.ini`가 `tests/`만 보기 때문이에요.
