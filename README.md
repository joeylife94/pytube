# pytube Streamlit GUI

This small project provides a Streamlit GUI to download YouTube videos, audio-only files, and entire playlists using pytube.

Features
- Choose video resolution (or highest available)
- Download audio-only streams and optionally convert to MP3 (requires pydub + ffmpeg)
- Download entire playlists using pytube.Playlist

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
- MP3 conversion requires pydub and ffmpeg; if pydub isn't installed the option will be disabled.
- Playlist downloads skip items that fail and continue with the rest.
# pytube Streamlit GUI

This small project provides a Streamlit GUI to download YouTube videos, audio-only files, and entire playlists using pytube.

Features
- Choose video resolution (or highest available)
- Download audio-only streams and optionally convert to MP3 (requires pydub + ffmpeg)
- Download entire playlists using pytube.Playlist

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

Notes & limitations
- This app uses pytube; sometimes YouTube changes require pytube updates.
- MP3 conversion requires pydub and ffmpeg; if pydub isn't installed the option will be disabled.
- Playlist downloads skip items that fail and continue with the rest.
