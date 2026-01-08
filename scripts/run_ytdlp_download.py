import os
import sys
import argparse
import os
import sys

# ensure repository root is on sys.path so local modules (pytube_helper) can be imported
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pytube_helper import download_with_ytdlp, extract_playlist_urls


def _print_progress(filename, received, total, speed, eta):
    try:
        total_s = str(total) if total else '?'
        print(f'DOWN {received}/{total_s} @ {speed} ETA {eta} :: {os.path.basename(filename) if filename else ""}')
    except Exception:
        pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='Quick yt-dlp download runner (single URL or playlist, sequential).')
    parser.add_argument('url', help='YouTube video URL or playlist URL')
    parser.add_argument('-o', '--output', default=os.path.join(os.getcwd(), 'downloads'), help='Output folder')
    parser.add_argument('--audio', action='store_true', help='Download audio only')
    parser.add_argument('--mp3', action='store_true', help='Convert audio to mp3 (requires ffmpeg)')
    parser.add_argument('--playlist', action='store_true', help='Treat URL as playlist and download sequentially')
    args = parser.parse_args(argv)

    os.makedirs(args.output, exist_ok=True)
    print('Output:', args.output)
    print('Mode:', 'playlist' if args.playlist else 'single', '| audio_only=', args.audio, '| mp3=', args.mp3)

    if args.mp3 and not args.audio:
        print('NOTE: --mp3 implies --audio; enabling audio-only mode.')
        args.audio = True

    if not args.playlist:
        fname = download_with_ytdlp(
            args.url,
            args.output,
            audio_only=args.audio,
            convert_mp3=args.mp3,
            progress_callback=_print_progress,
        )
        print('Done:', fname)
        return 0

    urls = extract_playlist_urls(args.url)
    print('Playlist items:', len(urls))
    ok = 0
    for i, u in enumerate(urls, start=1):
        print(f'[{i}/{len(urls)}] {u}')
        try:
            fname = download_with_ytdlp(
                u,
                args.output,
                audio_only=args.audio,
                convert_mp3=args.mp3,
                progress_callback=_print_progress,
            )
            print('  OK:', fname)
            ok += 1
        except Exception as e:
            print('  FAIL:', repr(e))
    print(f'Completed: {ok}/{len(urls)}')
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
