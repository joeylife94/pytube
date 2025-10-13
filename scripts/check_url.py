import sys, traceback
import shutil

if len(sys.argv) < 2:
    print("Usage: python check_url.py <url>")
    sys.exit(1)

url = sys.argv[1]
print("URL:", url)

try:
    import pytube
    from pytube import YouTube
    print("pytube version:", getattr(pytube, '__version__', 'unknown'))
except Exception as e:
    print("Failed to import pytube:", e)

# check ffmpeg availability
print("ffmpeg on PATH:", shutil.which('ffmpeg') is not None)

# Test pytube
try:
    print("\n--- pytube test ---")
    yt = YouTube(url)
    print("pytube: title:", yt.title)
    streams = yt.streams
    print("pytube: streams count:", len(list(streams)))
except Exception as e:
    print("pytube ERROR:", repr(e))
    traceback.print_exc()

# Test yt-dlp
try:
    print("\n--- yt-dlp test ---")
    import yt_dlp
    print("yt-dlp version:", getattr(yt_dlp, '__version__', 'unknown'))
    ydl_opts = {'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        print("yt-dlp: title:", info.get('title'))
        if 'formats' in info:
            fmts = info['formats']
            print("yt-dlp: formats count:", len(fmts))
            # print a few formats
            for f in fmts[:5]:
                print(" -", f.get('format_id'), f.get('format_note'), f.get('ext'), f.get('acodec'), f.get('vcodec'))
except Exception as e:
    print("yt-dlp ERROR:", repr(e))
    traceback.print_exc()
