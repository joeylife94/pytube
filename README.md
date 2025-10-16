# pytube Streamlit GUI

This small project provides a Streamlit GUI to download YouTube videos, audio-only files, and entire playlists using pytube.

Features
- Choose video resolution (or highest available)
- Download audio-only streams and optionally convert to MP3 (requires pydub + ffmpeg)
- Download entire playlists using pytube.Playlist

Requirements
- Python 3.8+
- Install Python packages from `requirements.txt`:
# pytube Streamlit GUI

This small project provides a Streamlit GUI to download YouTube videos, audio-only files, and entire playlists using pytube and (optionally) yt-dlp as a fallback.

Features
- Choose video resolution (or highest available)
- Download audio-only streams and optionally convert to MP3 (requires pydub + ffmpeg)
- Download entire playlists using pytube.Playlist (with optional yt-dlp fallback)

Requirements
- Python 3.8+
- Install Python packages from `requirements.txt`:

Windows PowerShell example:

```powershell
python -m pip install -r requirements.txt
```

Note: To convert to MP3 you need `ffmpeg` installed and available on PATH. Download from https://ffmpeg.org/ and add to PATH.

Run the app

```powershell
streamlit run app.py
```

Usage
- Paste a YouTube video or playlist URL.
- For playlists, check "Is this a playlist?".
- Choose Video or Audio mode.
- Select preferred resolution or audio bitrate.
- (Optional) Check "Convert audio to MP3" if you have pydub and ffmpeg.
- Click "Start download" and then use the immediate download buttons shown.

Default downloads folder
- If you leave the "Output folder" field blank the app will save files into a repo-local `downloads/` directory (created automatically). You can change this to any absolute path if desired.

ffmpeg installation (Windows)

MP3 conversion requires `ffmpeg`. Common installation options on Windows:

- Manual download
  - Download a static build from https://ffmpeg.org/download.html, unzip, and add the folder containing `ffmpeg.exe` to your PATH. Restart terminals.

- Chocolatey (recommended if you already use Chocolatey)
  - Open an elevated (Administrator) PowerShell and run:

```powershell
choco install ffmpeg -y
```

- winget (Windows 10/11)
  - Search first to find the authoritative package name:

```powershell
winget search ffmpeg
```

  - Then install using the appropriate package id, for example:

```powershell
winget install --id <PACKAGE_ID>
```

For convenience there's a small helper script included at `scripts/install_ffmpeg.ps1` that prints guidance and can run `choco install ffmpeg` only when called explicitly with `-Install` (see script header for usage).

Notes & limitations
- This app uses pytube; sometimes YouTube changes require pytube updates.
- If pytube fails to fetch metadata or download, the app can optionally use `yt-dlp` as a fallback (install `yt-dlp` in the environment to enable this).
- MP3 conversion requires pydub and ffmpeg; if pydub isn't installed the option will be disabled.
- Playlist downloads skip items that fail and continue with the rest.

Recent changes (local development)
- Added URL normalization to reduce pytube innertube HTTP 400 errors for short/youtu.be links.
- Added yt-dlp fallback for metadata extraction and downloads when pytube fails.
- Cache fetched metadata in `st.session_state` to keep download UI visible across Streamlit reruns.
- Default output folder now `downloads/` (created automatically).
- Added Playwright-based UI automation scripts under `scripts/` for reproducing UI flows during debugging.

UI testing with Playwright
- A lightweight Playwright script is included at `scripts/playwright_test.py` that can automate the browser to exercise the Streamlit UI (fill URL, click Start download, click download button, capture screenshots) for debugging. Playwright must be installed and browsers downloaded before running:

```powershell
. .\.venv\Scripts\Activate.ps1
python -m pip install playwright
python -m playwright install
python scripts\playwright_test.py
```

If you'd prefer not to run Playwright, you can manually test the UI in your local browser at `http://localhost:8501` while the app is running.

If you make code changes, please run unit tests with `pytest` and re-run the app to validate behavior.

Contact / support
- If you find a reproducible failure (pytube HTTP errors, missing metadata, or UI issues), open an issue with the URL and a copy of the console logs. The `scripts/` folder contains helpers used during debugging.
