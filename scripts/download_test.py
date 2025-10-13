import sys
import time
import os
from pathlib import Path

# make sure the repository root is on sys.path so local imports work when run from scripts/
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from pytube_helper import get_video_streams, download_video


def human(n):
    # simple bytes -> human
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def download_with_progress(url, output_folder):
    streams = get_video_streams(url)
    title = streams['title']
    print(f"Title: {title}")
    # pick best progressive, else best adaptive
    stream = streams['progressive'][0] if streams['progressive'] else streams['adaptive_video'][0]

    start_time = None

    def progress_cb(received, total):
        nonlocal start_time
        now = time.time()
        if start_time is None:
            start_time = now
        elapsed = max(now - start_time, 1e-6)
        pct = int(received / total * 100)
        speed = received / elapsed
        remaining = max(total - received, 0)
        eta = remaining / speed if speed > 0 else float('inf')
        print(f"{pct}% — {human(received)} / {human(total)} — {human(speed)}/s — ETA {int(eta)}s", end='\r')

    # ensure output folder exists
    os.makedirs(output_folder, exist_ok=True)
    out = download_video(stream, output_folder, progress_callback=progress_cb)
    print('\nDownload finished:', out)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python download_test.py <youtube_url> [output_folder]')
        sys.exit(1)
    url = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    download_with_progress(url, outdir)
