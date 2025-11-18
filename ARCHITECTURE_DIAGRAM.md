# DownloaderManager Architecture Diagram

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        USER APPLICATION                               │
│  (Streamlit / Tkinter / CLI / Direct Python Script)                  │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     DownloaderManager                                 │
│  ┌────────────────────────────────────────────────────────┐          │
│  │  • manages concurrency (ThreadPoolExecutor)            │          │
│  │  • orchestrates batch downloads                        │          │
│  │  • max_workers configuration                           │          │
│  │  • error isolation per download                        │          │
│  └──────────────────────┬─────────────────────────────────┘          │
└─────────────────────────┼────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     YoutubeDownloader                                 │
│  ┌────────────────────────────────────────────────────────┐          │
│  │  • core download logic                                 │          │
│  │  • intelligent engine selection                        │          │
│  │  • routes to appropriate backend                       │          │
│  └──────────────────────┬─────────────────────────────────┘          │
└─────────────────────────┼────────────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
    ┌─────────────────┐     ┌─────────────────┐
    │  _select_engine │     │ _build_ytdlp_   │
    │      ()         │     │    opts()       │
    │                 │     │                 │
    │  Decides based  │     │ Builds options  │
    │  on mode:       │     │ dict for mode   │
    │  • video → user │     └─────────────────┘
    │    preference   │
    │  • mp3 → yt-dlp │
    │  • subs → yt-dlp│
    └────────┬────────┘
             │
    ┌────────┴────────┐
    ▼                 ▼
┌─────────┐    ┌──────────┐
│ pytube  │    │  yt-dlp  │
│ engine  │    │  engine  │
└─────────┘    └──────────┘
```

## Feature → Engine Selection Flow

```
User Request:
  ├─ mode="video"
  │    └─→ Check preferred_engine
  │         ├─ "pytube" available? → USE PYTUBE ✓
  │         └─ else → USE YT-DLP ✓
  │
  ├─ mode="mp3"
  │    └─→ FORCE YT-DLP (pytube can't convert) ⚠️
  │         └─ Build opts with FFmpegExtractAudio
  │
  ├─ mode="video_subs"
  │    └─→ FORCE YT-DLP (pytube unreliable for subs) ⚠️
  │         └─ Build opts with writesubtitles=True
  │
  └─ mode="subs_only"
       └─→ FORCE YT-DLP (pytube can't skip video) ⚠️
            └─ Build opts with skip_download=True
```

## Batch Download Flow (Concurrent)

```
URLs: [url1, url2, url3, url4, url5]
max_workers = 3

ThreadPoolExecutor:
┌──────────────────────────────────────────────────┐
│  Worker 1          Worker 2          Worker 3    │
│  ───────────       ───────────       ─────────── │
│                                                   │
│  url1 (running)    url2 (running)    url3 (running)
│     ↓                  ↓                  ↓       │
│  Download...       Download...       Download... │
│     ↓                  ↓                  ↓       │
│  ✓ Success         ✗ Failed          ✓ Success   │
│     ↓                  ↓                  ↓       │
│  url4 (next)       url5 (next)       (idle)      │
│     ↓                  ↓                          │
│  Download...       Download...                   │
│     ↓                  ↓                          │
│  ✓ Success         ✓ Success                     │
└──────────────────────────────────────────────────┘

Results collected as futures complete:
[Result(url1, success=True),
 Result(url2, success=False, error="..."),
 Result(url3, success=True),
 Result(url4, success=True),
 Result(url5, success=True)]
```

## Data Flow: Video Download

```
1. User calls:
   manager.download_single("https://youtu.be/xyz", mode="video")

2. DownloaderManager:
   └─→ delegates to YoutubeDownloader.download()

3. YoutubeDownloader.download():
   ├─→ _select_engine(mode=VIDEO)
   │    └─→ returns PYTUBE (user preference)
   │
   └─→ _download_with_pytube(url)
        ├─→ YouTube(url)
        ├─→ streams.filter(progressive=True)
        ├─→ order_by('resolution').desc().first()
        └─→ stream.download(output_path)

4. Returns:
   DownloadResult(
       url="https://youtu.be/xyz",
       success=True,
       file_path="/downloads/Video Title.mp4",
       engine="pytube"
   )
```

## Data Flow: MP3 Download

```
1. User calls:
   manager.download_single("https://youtu.be/xyz", mode="mp3")

2. DownloaderManager:
   └─→ delegates to YoutubeDownloader.download()

3. YoutubeDownloader.download():
   ├─→ _select_engine(mode=MP3)
   │    └─→ FORCES YT-DLP (ignores user preference)
   │
   └─→ _download_with_ytdlp(url, mode=MP3)
        ├─→ _build_ytdlp_opts(MP3)
        │    └─→ {
        │         'format': 'bestaudio/best',
        │         'postprocessors': [{
        │             'key': 'FFmpegExtractAudio',
        │             'preferredcodec': 'mp3',
        │             'preferredquality': '192'
        │         }]
        │        }
        │
        └─→ yt_dlp.YoutubeDL(opts).download()
             └─→ calls ffmpeg for conversion

4. Returns:
   DownloadResult(
       url="https://youtu.be/xyz",
       success=True,
       file_path="/downloads/Video Title.mp3",
       engine="yt-dlp"
   )
```

## Error Handling Flow

```
Batch Download: [url1, url2_invalid, url3]

ThreadPoolExecutor spawns 3 workers:

Worker 1 (url1):
  try:
      download_with_ytdlp()
      ✓ Success
  except Exception as e:
      (not reached)
  → Result(url1, success=True, ...)

Worker 2 (url2_invalid):
  try:
      download_with_ytdlp()
      ✗ Raises HTTPError
  except Exception as e:
      logger.error(...)
  → Result(url2, success=False, error="HTTP Error 404")

Worker 3 (url3):
  try:
      download_with_ytdlp()
      ✓ Success
  except Exception as e:
      (not reached)
  → Result(url3, success=True, ...)

Final Results:
[Result(url1, ✓), Result(url2, ✗), Result(url3, ✓)]

Summary: 2/3 successful (batch didn't crash!)
```

## Class Relationship Diagram

```
┌─────────────────────────────────────────┐
│         DownloaderManager               │
│ ─────────────────────────────────────── │
│ - downloader: YoutubeDownloader         │
│ - max_workers: int                      │
│ ─────────────────────────────────────── │
│ + download_batch(urls, mode)            │
│ + download_single(url, mode)            │
└───────────────┬─────────────────────────┘
                │ has-a
                ▼
┌─────────────────────────────────────────┐
│        YoutubeDownloader                │
│ ─────────────────────────────────────── │
│ - output_dir: Path                      │
│ - preferred_engine: DownloadEngine      │
│ ─────────────────────────────────────── │
│ + download(url, mode)                   │
│ - _select_engine(mode)                  │
│ - _download_with_pytube(url)            │
│ - _download_with_ytdlp(url, mode)       │
│ - _build_ytdlp_opts(mode)               │
└───────────────┬─────────────────────────┘
                │ returns
                ▼
┌─────────────────────────────────────────┐
│          DownloadResult                 │
│ ─────────────────────────────────────── │
│ + url: str                              │
│ + success: bool                         │
│ + file_path: Optional[str]              │
│ + error: Optional[str]                  │
│ + engine: Optional[str]                 │
└─────────────────────────────────────────┘

┌─────────────────┐       ┌─────────────────┐
│  DownloadMode   │       │ DownloadEngine  │
│  (Enum)         │       │  (Enum)         │
│ ─────────────── │       │ ─────────────── │
│ • VIDEO         │       │ • PYTUBE        │
│ • MP3           │       │ • YTDLP         │
│ • VIDEO_SUBS    │       └─────────────────┘
│ • SUBS_ONLY     │
└─────────────────┘
```

## yt-dlp Options Builder Logic

```
_build_ytdlp_opts(mode):

mode = VIDEO:
  └─→ {
       'format': 'bestvideo+bestaudio/best',
       'merge_output_format': 'mp4'
      }

mode = MP3:
  └─→ {
       'format': 'bestaudio/best',
       'postprocessors': [{
           'key': 'FFmpegExtractAudio',
           'preferredcodec': 'mp3',
           'preferredquality': '192'
       }]
      }

mode = VIDEO_SUBS:
  └─→ {
       'format': 'bestvideo+bestaudio/best',
       'writesubtitles': True,
       'writeautomaticsub': True,
       'subtitleslangs': ['en', 'ko'],
       'postprocessors': [{
           'key': 'FFmpegSubtitlesConvertor',
           'format': 'srt'
       }]
      }

mode = SUBS_ONLY:
  └─→ {
       'skip_download': True,  ← KEY: No video download!
       'writesubtitles': True,
       'writeautomaticsub': True,
       'subtitleslangs': ['en', 'ko']
      }
```

## Integration Points Visualization

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌────────────┐  ┌────────────┐  ┌────────────┐
│ Streamlit  │  │  Tkinter   │  │    CLI     │
│    App     │  │    GUI     │  │  Script    │
└─────┬──────┘  └─────┬──────┘  └─────┬──────┘
      │               │               │
      └───────────────┼───────────────┘
                      ▼
        ┌──────────────────────────┐
        │ IntegratedDownloadService│
        └──────────┬───────────────┘
                   ▼
        ┌──────────────────────┐
        │  DownloaderManager   │
        └──────────────────────┘
```

## File Structure

```
pytube/
├── downloader_manager.py           ← Core implementation (550 lines)
│   ├── class DownloaderManager
│   ├── class YoutubeDownloader
│   ├── class DownloadResult
│   ├── enum DownloadMode
│   └── enum DownloadEngine
│
├── test_downloader_manager.py      ← Test suite (300 lines)
│   ├── test_scenario_1_basic_video_download()
│   ├── test_scenario_2_mp3_conversion()
│   ├── test_scenario_3_video_with_subtitles()
│   ├── test_scenario_4_subtitles_only()
│   ├── test_scenario_5_batch_concurrent()
│   └── test_scenario_6_engine_selection_logic()
│
├── integration_examples.py         ← Integration guide (400 lines)
│   ├── class IntegratedDownloadService
│   ├── streamlit_app_integration()
│   ├── tkinter_app_integration()
│   └── cli_integration()
│
├── quick_start_demo.py             ← Quick start demo (250 lines)
│   ├── demo_feature_1_batch_video()
│   ├── demo_feature_2_mp3()
│   ├── demo_feature_3_video_subs()
│   └── demo_feature_4_subs_only()
│
├── DOWNLOADER_MANAGER_README.md    ← Documentation (500 lines)
├── IMPLEMENTATION_SUMMARY.md       ← This summary (500 lines)
└── ARCHITECTURE_DIAGRAM.md         ← This file
```

## Summary

This architecture provides:

✅ **Separation of Concerns**: Each class has one responsibility
✅ **Extensibility**: Easy to add new download modes
✅ **Testability**: Clear interfaces for unit testing
✅ **Type Safety**: Full type hints throughout
✅ **Error Isolation**: Batch downloads don't crash on single failures
✅ **Intelligent Routing**: Automatic engine selection based on features
✅ **Production Ready**: Logging, error handling, documentation

**Total Package**: ~2,000 lines of production-quality code
