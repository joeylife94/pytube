# DownloaderManager - Quick Reference Card

## 🚀 5-Second Start

```python
from downloader_manager import DownloaderManager

manager = DownloaderManager()
result = manager.download_single("https://youtu.be/xyz", mode="video")
```

## 📦 Installation

```bash
pip install yt-dlp          # Required
pip install pytube          # Optional
# Install ffmpeg (system-level, required for MP3)
```

## 🎯 The 4 Features

### 1️⃣ Batch Download
```python
urls = ["https://youtu.be/1", "https://youtu.be/2", "https://youtu.be/3"]
manager = DownloaderManager(max_workers=3)
results = manager.download_batch(urls, mode="video")
```

### 2️⃣ MP3 Conversion
```python
manager = DownloaderManager()
results = manager.download_batch(urls, mode="mp3")  # Auto-uses yt-dlp + ffmpeg
```

### 3️⃣ Video + Subtitles
```python
manager = DownloaderManager()
result = manager.download_single(url, mode="video_subs")  # Downloads video + subs
```

### 4️⃣ Subtitles Only
```python
manager = DownloaderManager()
results = manager.download_batch(urls, mode="subs_only")  # No video, just subs
```

## 🎛️ Configuration

```python
DownloaderManager(
    output_dir="downloads",      # Where to save files
    preferred_engine="pytube",   # or "yt-dlp"
    max_workers=3                # Concurrent downloads
)
```

## 📊 Modes

| Mode | Description | Engine | Output |
|------|-------------|--------|--------|
| `"video"` | Video download | User choice | `.mp4` |
| `"mp3"` | Audio + convert | yt-dlp (forced) | `.mp3` |
| `"video_subs"` | Video + subtitles | yt-dlp (forced) | `.mp4` + `.srt` |
| `"subs_only"` | Subtitles only | yt-dlp (forced) | `.srt` |

## 🔧 Result Object

```python
result = manager.download_single(url, mode="video")

if result.success:
    print(f"File: {result.file_path}")
    print(f"Engine: {result.engine}")
else:
    print(f"Error: {result.error}")
```

## 🎨 Progress Callback (Integration)

```python
from integration_examples import IntegratedDownloadService

service = IntegratedDownloadService()

def progress(current, total, url, status):
    print(f"[{current}/{total}] {url}: {status}")

results = service.download_videos(urls, progress_callback=progress)
```

## 🧪 Testing

```bash
# Run tests
python test_downloader_manager.py

# Run demo (dry-run)
python quick_start_demo.py

# Run actual downloads (edit DEMO_MODE first)
python quick_start_demo.py
```

## ⚡ Engine Selection (Automatic)

```
Video mode → Uses your preferred_engine
MP3 mode → ALWAYS uses yt-dlp (pytube can't convert)
Subtitle modes → ALWAYS uses yt-dlp (pytube unreliable)
```

## 📁 Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `downloader_manager.py` | Core implementation | 550 |
| `test_downloader_manager.py` | Test suite | 300 |
| `integration_examples.py` | Integration guide | 400 |
| `quick_start_demo.py` | Quick demo | 250 |
| `DOWNLOADER_MANAGER_README.md` | Full documentation | 500 |
| `IMPLEMENTATION_SUMMARY.md` | Summary report | 500 |
| `ARCHITECTURE_DIAGRAM.md` | Visual diagrams | 400 |

## 🆘 Troubleshooting

### "No module named 'yt_dlp'"
```bash
pip install yt-dlp
```

### "ffmpeg not found" (for MP3)
- Windows: Download from ffmpeg.org, add to PATH
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

### pytube HTTP 400 errors
- System automatically falls back to yt-dlp
- Or set `preferred_engine="yt-dlp"`

## 📚 Documentation

- **Quick Start**: This file
- **Full Docs**: `DOWNLOADER_MANAGER_README.md`
- **Architecture**: `ARCHITECTURE_DIAGRAM.md`
- **Summary**: `IMPLEMENTATION_SUMMARY.md`
- **Examples**: `integration_examples.py`
- **Tests**: `test_downloader_manager.py`

## 💡 Common Patterns

### Pattern 1: Batch MP3 with Progress
```python
manager = DownloaderManager(output_dir="music", max_workers=3)
results = manager.download_batch(playlist_urls, mode="mp3")

for r in results:
    if r.success:
        print(f"✓ {r.file_path}")
    else:
        print(f"✗ {r.url}: {r.error}")
```

### Pattern 2: Error Handling
```python
results = manager.download_batch(urls, mode="video")

successful = [r for r in results if r.success]
failed = [r for r in results if not r.success]

print(f"Downloaded: {len(successful)}/{len(urls)}")

if failed:
    for r in failed:
        print(f"Failed: {r.url} - {r.error}")
```

### Pattern 3: Single Download with Check
```python
result = manager.download_single(url, mode="video")

if result.success:
    file_size = os.path.getsize(result.file_path)
    print(f"Downloaded {file_size / 1024 / 1024:.2f} MB")
else:
    print(f"Failed: {result.error}")
```

## 🎓 Learning Path

1. **Start**: Run `python quick_start_demo.py`
2. **Try**: Use the examples above
3. **Test**: Run `python test_downloader_manager.py`
4. **Read**: Check `DOWNLOADER_MANAGER_README.md`
5. **Integrate**: See `integration_examples.py`

## 🚨 Important Rules

1. ⚠️ MP3 mode REQUIRES ffmpeg
2. ⚠️ MP3/subtitle modes FORCE yt-dlp (ignores preference)
3. ✅ One failed download won't crash the batch
4. ✅ Thread-safe for concurrent downloads
5. ✅ Detailed error messages in results

## 📞 Support

- Read docs in `DOWNLOADER_MANAGER_README.md`
- Check examples in `integration_examples.py`
- Run tests: `python test_downloader_manager.py`

---

**Version**: 1.0  
**Status**: Production Ready ✅  
**Total Code**: ~2,000 lines  
**Test Coverage**: All 4 features ✓
