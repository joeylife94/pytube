# DownloaderManager - YouTube Downloader with Hybrid Engine Support

A robust, production-ready YouTube downloader that intelligently selects between `pytube` and `yt-dlp` based on feature requirements.

## Features

### ✅ The 4 Core Capabilities

1. **Batch Download** - Download multiple videos concurrently using ThreadPoolExecutor
2. **MP3 Conversion** - Extract audio and convert to MP3 using ffmpeg
3. **Video + Subtitles** - Download video with best available subtitles (manual/auto-generated)
4. **Subtitles Only** - Download only subtitle files (skip video/audio)

### 🎯 Intelligent Engine Selection

The system automatically selects the best engine based on the task:

| Mode | Preferred Engine | Forced Engine | Reason |
|------|-----------------|---------------|--------|
| `video` | User preference (pytube/yt-dlp) | - | Either engine works |
| `mp3` | ❌ | ✅ yt-dlp | pytube doesn't support MP3 conversion |
| `video_subs` | ❌ | ✅ yt-dlp | pytube has unreliable subtitle support |
| `subs_only` | ❌ | ✅ yt-dlp | pytube cannot skip video download |

**Critical Rule**: MP3 and subtitle features ALWAYS use yt-dlp, regardless of user preference.

## Installation

```bash
# Required
pip install yt-dlp

# Optional (for plain video downloads)
pip install pytube

# Ensure ffmpeg is installed and in PATH (required for MP3 conversion)
# Windows: Download from https://ffmpeg.org/download.html
# macOS: brew install ffmpeg
# Linux: sudo apt install ffmpeg
```

## Quick Start

### Basic Usage

```python
from downloader_manager import DownloaderManager

# Initialize manager
manager = DownloaderManager(
    output_dir="downloads",
    preferred_engine="pytube",  # or "yt-dlp"
    max_workers=3  # concurrent downloads
)

# Single video download
result = manager.download_single(
    url="https://youtu.be/dQw4w9WgXcQ",
    mode="video"
)

if result.success:
    print(f"Downloaded: {result.file_path}")
else:
    print(f"Failed: {result.error}")
```

### Batch Download (Concurrent)

```python
urls = [
    "https://youtu.be/xyz123",
    "https://youtu.be/abc456",
    "https://youtu.be/def789"
]

# Download all concurrently (max 3 at a time)
results = manager.download_batch(urls, mode="video")

# Check results
for result in results:
    if result.success:
        print(f"✓ {result.url} -> {result.file_path}")
    else:
        print(f"✗ {result.url} -> {result.error}")
```

## Usage Examples

### 1. Video Download (Standard Quality)

```python
manager = DownloaderManager(
    output_dir="downloads/videos",
    preferred_engine="pytube"  # Fast for simple videos
)

result = manager.download_single(
    "https://youtu.be/dQw4w9WgXcQ",
    mode="video"
)
```

### 2. MP3 Audio Extraction

```python
# Automatically uses yt-dlp + ffmpeg
manager = DownloaderManager(
    output_dir="downloads/music",
    preferred_engine="pytube"  # Will be overridden to yt-dlp
)

urls = [
    "https://youtu.be/song1",
    "https://youtu.be/song2",
    "https://youtu.be/song3"
]

# Download as MP3 files
results = manager.download_batch(urls, mode="mp3")
```

**Note**: Requires ffmpeg in system PATH.

### 3. Video with Subtitles

```python
manager = DownloaderManager(
    output_dir="downloads/with_subs",
    max_workers=2
)

# Downloads video + subtitles (en, ko priority)
result = manager.download_single(
    "https://youtu.be/video_with_subs",
    mode="video_subs"
)

# Output: video.mp4 + video.en.srt + video.ko.srt
```

**Subtitle Priority**:
1. Manual English subtitles
2. Manual Korean subtitles
3. Auto-generated English
4. Auto-generated Korean

### 4. Subtitles Only (No Video)

```python
manager = DownloaderManager(
    output_dir="downloads/subtitles",
    max_workers=5
)

# Download ONLY subtitles (skips video/audio)
results = manager.download_batch(
    urls=["https://youtu.be/video1", "https://youtu.be/video2"],
    mode="subs_only"
)

# Output: Only .srt/.vtt files
```

**Use case**: Create subtitle archives, translation projects, etc.

## API Reference

### `DownloaderManager`

Main class for orchestrating downloads.

#### Constructor

```python
DownloaderManager(
    output_dir: str = "downloads",
    preferred_engine: str = "pytube",
    max_workers: int = 3
)
```

**Parameters**:
- `output_dir`: Directory for downloaded files
- `preferred_engine`: `"pytube"` or `"yt-dlp"` (only for video mode)
- `max_workers`: Max concurrent downloads

#### Methods

**`download_single(url: str, mode: str) -> DownloadResult`**

Download a single video.

**`download_batch(urls: List[str], mode: str) -> List[DownloadResult]`**

Download multiple videos concurrently.

**Modes**:
- `"video"` - Standard video download
- `"mp3"` - Audio extraction + MP3 conversion
- `"video_subs"` - Video + subtitles
- `"subs_only"` - Subtitles only

### `DownloadResult`

Result object for each download.

**Attributes**:
- `url: str` - Original URL
- `success: bool` - Whether download succeeded
- `file_path: str | None` - Path to downloaded file
- `error: str | None` - Error message if failed
- `engine: str | None` - Engine used ("pytube" or "yt-dlp")

## Error Handling

The system is designed for robustness:

```python
urls = [
    "https://youtu.be/valid_video",
    "https://invalid-url",  # Will fail gracefully
    "https://youtu.be/another_valid"
]

results = manager.download_batch(urls, mode="video")

# One failure doesn't crash the batch
successful = [r for r in results if r.success]
failed = [r for r in results if not r.success]

print(f"Success: {len(successful)}/{len(urls)}")
```

**Error handling features**:
- Individual download failures don't crash the batch
- Detailed error messages in `DownloadResult.error`
- Automatic fallback to yt-dlp if pytube fails
- Thread-safe concurrent execution

## Architecture

```
DownloaderManager (High-level API)
    ├─ manages concurrency (ThreadPoolExecutor)
    └─ delegates to YoutubeDownloader
            ├─ _select_engine() - chooses pytube or yt-dlp
            ├─ _download_with_pytube() - simple video downloads
            └─ _download_with_ytdlp() - advanced features
                    └─ _build_ytdlp_opts() - mode-specific options
```

## Advanced: Custom yt-dlp Options

For advanced users who need custom yt-dlp configuration:

```python
from downloader_manager import YoutubeDownloader
from downloader_manager import DownloadMode

# Direct access to YoutubeDownloader
downloader = YoutubeDownloader(
    output_dir="downloads",
    preferred_engine="yt-dlp"
)

# Manually build and modify yt-dlp options
opts = downloader._build_ytdlp_opts(DownloadMode.VIDEO)
opts['format'] = 'bestvideo[height<=720]+bestaudio'  # Limit to 720p
opts['ratelimit'] = 1000000  # 1MB/s rate limit

# Use custom options (requires direct yt_dlp usage)
import yt_dlp
with yt_dlp.YoutubeDL(opts) as ydl:
    ydl.download(['https://youtu.be/video'])
```

## Testing

Run the test suite to verify functionality:

```bash
python test_downloader_manager.py
```

**Test scenarios**:
1. Basic video download
2. MP3 conversion (engine forcing)
3. Video + subtitles
4. Subtitles only
5. Batch concurrent downloads
6. Engine selection logic verification

## Requirements

- Python 3.8+
- `yt-dlp` (required)
- `pytube` (optional, for faster simple downloads)
- `ffmpeg` (required for MP3 conversion)

## Troubleshooting

### "No download engine available"
```bash
pip install yt-dlp
```

### "ffmpeg not found" (for MP3 mode)
- **Windows**: Download from ffmpeg.org, add to PATH
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

### pytube HTTP 400 errors
- This is why the system auto-switches to yt-dlp for advanced features
- For plain videos, try setting `preferred_engine="yt-dlp"`

### Subtitle not found
- Not all videos have subtitles
- The system tries manual → auto-generated fallback
- Check `result.error` for details

## License

This code is provided as-is for the YouTube downloader project.

## Contributing

To add new download modes:

1. Add enum to `DownloadMode`
2. Implement option builder in `_build_ytdlp_opts()`
3. Update `_select_engine()` if forcing yt-dlp is needed
4. Add test scenario in `test_downloader_manager.py`
