# Development setup (Windows / PowerShell)

This guide helps you get a local development environment ready for working on the pytube Streamlit GUI project.

Prerequisites
- Python 3.10+ (3.12 recommended). Ensure `python` is on your PATH.
- Git
- PowerShell (Windows PowerShell or PowerShell Core)

1) Create and activate a virtual environment

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

2) Upgrade pip and install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Notes:
- `requirements.txt` includes runtime deps used by the app (streamlit, pytube, pydub, pytest...).
- If you plan to run Playwright UI automation, install Playwright as shown below.

3) (Optional) Install Playwright for UI automation

```powershell
# install the Python package
python -m pip install playwright
# download browsers and supporting components
python -m playwright install --with-deps chromium
```

4) (Optional) Install yt-dlp for more robust extraction/downloads

```powershell
python -m pip install yt-dlp
```

5) (Optional) Install ffmpeg for audio conversion (pydub)

Options on Windows:
- Manual: Download a static build from https://ffmpeg.org/download.html, extract and add the folder containing `ffmpeg.exe` to your PATH.
- Chocolatey (admin): `choco install ffmpeg -y` (run in elevated PowerShell)

After installing ffmpeg, restart your terminal.

6) Run tests

```powershell
. .\.venv\Scripts\Activate.ps1
python -m pytest -q
```

7) Run the Streamlit app

```powershell
. .\.venv\Scripts\Activate.ps1
streamlit run app.py
```

Open the URL shown by Streamlit (typically http://localhost:8501) in your browser.

8) Developer notes and tips

- Downloads folder: If the "Output folder" is left blank in the UI, files will be stored in a repo-local `downloads/` directory which the app creates automatically.
- Tests: The repo includes a small test suite under `tests/`. Run `pytest` regularly when changing code.
- Playwright: The included Playwright scripts are under `scripts/playwright_test.py` and `scripts/playwright_debug.py`. Use these to reproduce UI flows and capture screenshots.
- Avoid committing generated artifacts: `.gitignore` is configured to exclude `.venv`, screenshots, `scripts/ffmpeg/`, and other generated files.

9) Troubleshooting

- If you see pytube HTTP 400 errors for short URLs, the helper includes URL normalization; ensure you use the latest `pytube` and/or install `yt-dlp` to use the fallback.
- If Playwright tests fail on CI with browser install error, ensure `python -m playwright install --with-deps chromium` runs successfully on the runner (may need additional packages on Linux runners).

---

If you'd like, I can also:
- Add a `dev-requirements.txt` with Playwright and test helpers.
- Add a GitHub Actions job to run Playwright tests (will increase job runtime because browsers must be downloaded).

Dev requirements
----------------
If you plan to run the Playwright automation or developer tests, install the dev requirements:

```powershell
python -m pip install -r dev-requirements.txt
python -m playwright install --with-deps chromium
```

`dev-requirements.txt` in this repo includes:
- playwright
- pytest
- yt-dlp

CI notes
--------
On CI (GitHub Actions) we recommend:
- Install the dev requirements and run `python -m playwright install --with-deps chromium` before running Playwright scripts.
- Start Streamlit and poll `http://localhost:8501/` until ready before executing Playwright.
