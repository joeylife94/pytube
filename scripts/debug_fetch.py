import sys
import os
import json
import traceback

# ensure repository root is on sys.path so local modules can be imported when running from scripts/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pytube_helper import get_video_streams

url = sys.argv[1] if len(sys.argv) > 1 else None
if not url:
    print('Usage: python debug_fetch.py <url>')
    sys.exit(2)

print('Testing URL:', url)
try:
    streams = get_video_streams(url)
    print('SUCCESS: backend=', streams.get('backend'))
    # print summary
    out = {k: (type(v).__name__ if not hasattr(v, '__len__') else f'len={len(v)}') for k, v in streams.items()}
    print(json.dumps(out, indent=2, ensure_ascii=False))
except Exception as e:
    print('ERROR:')
    traceback.print_exc()
    sys.exit(1)
