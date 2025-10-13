import os
import sys
# ensure repository root is on sys.path so local modules (pytube_helper) can be imported
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pytube_helper import download_with_ytdlp

if len(sys.argv) < 2:
    print('Usage: python run_ytdlp_download.py <url> [output_folder]')
    sys.exit(1)

url = sys.argv[1]
output = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(os.getcwd(), 'downloads')
os.makedirs(output, exist_ok=True)
print('Downloading to', output)
try:
    fname = download_with_ytdlp(url, output, audio_only=False, progress_callback=lambda f,r,t,s,e: print(f'DOWN {r}/{t} @ {s} ETA {e}'))
    print('Done, file:', fname)
except Exception as e:
    print('ERROR during download:', repr(e))
    raise
