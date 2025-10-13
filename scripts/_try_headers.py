from pathlib import Path
import sys
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# set pytube request headers before importing YouTube
import pytube.request as pyt_req
pyt_req.default_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36'
}

from pytube_helper import get_video_streams
url = 'https://www.youtube.com/watch?v=EszTviyRK2c'
print('Trying get_video_streams with custom headers...')
try:
    streams = get_video_streams(url)
    print('Success: title=', streams['title'])
    print('progressive count=', len(streams['progressive']))
except Exception as e:
    import traceback
    traceback.print_exc()
    print('Failed with', e)
