import sys, os
# ensure project root is on sys.path so local imports resolve when running from scripts/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from pytube_helper import extract_playlist_urls, get_video_streams, has_yt_dlp
import traceback

url = 'https://www.youtube.com/playlist?list=PLF9mJC4RrjIhS4MMm0x72-qWEn1LRvPuW'
print('Playlist URL:', url)

try:
    urls = extract_playlist_urls(url)
    print('Found', len(urls), 'items')
    for i, u in enumerate(urls[:50], start=1):
        title = None
        try:
            s = get_video_streams(u)
            title = s.get('title') if isinstance(s, dict) else str(s)
        except Exception as e:
            title = f'Error: {e}'
        print(f"{i:02d}: {title} | {u}")
except Exception as e:
    print('Extraction failed:')
    traceback.print_exc()
