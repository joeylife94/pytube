import os
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pytube import YouTube, Playlist
from pytube.cli import on_progress
from typing import Callable, Optional, List
import time
import math
from urllib.parse import urlparse, parse_qs
import logging

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except Exception:
    YTDLP_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except Exception:
    PYDUB_AVAILABLE = False


def is_ffmpeg_available() -> bool:
    """Check whether ffmpeg is on PATH (used by pydub)."""
    return shutil.which('ffmpeg') is not None


# module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    # basic configuration for local debugging
    logging.basicConfig(level=logging.INFO)


def _normalize_video_url(url: str) -> str:
    """Normalize many YouTube URL forms to https://www.youtube.com/watch?v=<id>.

    This strips extra query params (for example `?si=...`) which can cause pytube's
    innertube requests to fail with HTTP 400 on some URLs (observed with youtu.be links).
    """
    try:
        parsed = urlparse(url)
        # handle youtu.be short links
        if parsed.netloc.endswith('youtu.be'):
            vid = parsed.path.lstrip('/')
            # remove any query/fragment
            if vid:
                return f'https://www.youtube.com/watch?v={vid}'

        # for youtube.com links, prefer the v= query param when present
        if parsed.netloc.endswith('youtube.com') or 'youtube' in parsed.netloc:
            qs = parse_qs(parsed.query)
            v = qs.get('v')
            if v:
                return f'https://www.youtube.com/watch?v={v[0]}'
            # handle /shorts/<id>
            parts = parsed.path.split('/')
            if 'shorts' in parts:
                idx = parts.index('shorts')
                if idx + 1 < len(parts):
                    return f'https://www.youtube.com/watch?v={parts[idx+1]}'
    except Exception:
        # if anything goes wrong, just return original URL
        return url
    return url


def get_video_streams(url: str):
    """Return available streams for a YouTube URL.

    Returns dict with 'title', 'progressive', 'adaptive_video', 'audio' lists.
    """
    # Try pytube first. If it fails (e.g. HTTP 400 from innertube), and yt-dlp is
    # available, fall back to yt-dlp metadata extraction so the UI can continue.
    try:
        norm_url = _normalize_video_url(url)
        if norm_url != url:
            logger.info('Normalized URL: %s -> %s', url, norm_url)
        yt = YouTube(norm_url, on_progress_callback=on_progress)
        progressive = sorted([s for s in yt.streams.filter(progressive=True, file_extension='mp4')],
                            key=lambda s: int(s.resolution.replace('p','')) if s.resolution else 0,
                            reverse=True)
        adaptive_video = sorted([s for s in yt.streams.filter(only_video=True, file_extension='mp4')],
                                key=lambda s: int(s.resolution.replace('p','')) if s.resolution else 0,
                                reverse=True)
        audio_streams = sorted([s for s in yt.streams.filter(only_audio=True)],
                               key=lambda s: int(s.abr.replace('kbps','')) if s.abr else 0,
                               reverse=True)
        return {
            'backend': 'pytube',
            'title': yt.title,
            'progressive': progressive,
            'adaptive_video': adaptive_video,
            'audio': audio_streams,
        }
    except Exception as e:
        # log the underlying error for diagnostics
        logger.exception('pytube failed to fetch metadata for url=%s', url)
        # fallback: use yt-dlp to obtain metadata (if available)
        if YTDLP_AVAILABLE:
            try:
                ydl_opts = {'quiet': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                # return minimal metadata to the app; note: these formats are not pytube Stream objects
                return {
                    'backend': 'yt-dlp',
                    'title': info.get('title'),
                    'yt_dlp_info': info,
                }
            except Exception:
                logger.exception('yt-dlp fallback also failed for url=%s', url)
                # surface clearer error
                raise RuntimeError(f'Failed to fetch metadata via yt-dlp for {url}') from e
        # if yt-dlp is not available, raise a helpful error to the caller
        raise RuntimeError(
            f'pytube failed to fetch metadata for {url}: {e}.\n'
            'Consider installing yt-dlp (`pip install yt-dlp`) to enable a fallback or check the URL/connection.'
        ) from e


def download_video(stream, output_path, filename=None, progress_callback: Optional[Callable[[int, int], None]] = None):
    """Download a pytube Stream object to output_path. Optionally accepts a progress_callback(bytes_received, total_bytes).

    Returns output file path.
    """
    # If a progress_callback is provided, attach it to the YouTube object that owns this stream
    # Note: Stream has a reference to its player/yt via stream.player_config_args in older pytube; easiest approach is
    # to create a new YouTube object for the same video and find the matching stream there so we can register callback.
    try:
        if progress_callback:
            yt = YouTube(stream.player_config_args.get('url')) if hasattr(stream, 'player_config_args') else None
            # If we can't get the original YouTube instance, fall back to direct download without progress
            if yt is None:
                if filename:
                    out_file = stream.download(output_path=output_path, filename=filename)
                else:
                    out_file = stream.download(output_path=output_path)
                return out_file

            def _on_progress(s, chunk, bytes_remaining):
                total = s.filesize
                received = total - bytes_remaining
                try:
                    progress_callback(received, total)
                except Exception:
                    pass

            yt.register_on_progress_callback(_on_progress)
            # find matching stream on this yt instance
            candidate = None
            for s in yt.streams:
                if s.itag == stream.itag:
                    candidate = s
                    break
            if candidate is None:
                candidate = stream

            if filename:
                out_file = candidate.download(output_path=output_path, filename=filename)
            else:
                out_file = candidate.download(output_path=output_path)
            return out_file
        else:
            if filename:
                out_file = stream.download(output_path=output_path, filename=filename)
            else:
                out_file = stream.download(output_path=output_path)
            return out_file
    finally:
        # best-effort: unregister callbacks if possible (pytube does not expose unregister, so skip)
        pass


def download_audio(stream, output_path, filename=None, convert_mp3=False, progress_callback: Optional[Callable[[int, int], None]] = None):
    """Download audio-only stream. If convert_mp3 and pydub+ffmpeg available, convert to mp3.

    progress_callback is a function(bytes_received, total_bytes) for UI updates.
    Returns final file path.
    """
    # If progress_callback provided, attempt to attach via YouTube on_progress
    if progress_callback:
        try:
            yt = YouTube(stream.player_config_args.get('url')) if hasattr(stream, 'player_config_args') else None
        except Exception:
            yt = None

        if yt is None:
            base_out = stream.download(output_path=output_path, filename=filename)
        else:
            def _on_progress(s, chunk, bytes_remaining):
                total = s.filesize
                received = total - bytes_remaining
                try:
                    progress_callback(received, total)
                except Exception:
                    pass

            try:
                yt.register_on_progress_callback(_on_progress)
            except Exception:
                pass

            # find candidate stream
            candidate = None
            for s in yt.streams:
                if s.itag == stream.itag:
                    candidate = s
                    break
            if candidate is None:
                candidate = stream

            if filename:
                base_out = candidate.download(output_path=output_path, filename=filename)
            else:
                base_out = candidate.download(output_path=output_path)

    else:
        base_out = stream.download(output_path=output_path, filename=filename)

    if convert_mp3 and PYDUB_AVAILABLE and is_ffmpeg_available():
        name, _ext = os.path.splitext(base_out)
        mp3_path = name + '.mp3'
        audio = AudioSegment.from_file(base_out)
        audio.export(mp3_path, format='mp3')
        return mp3_path

    return base_out


def has_yt_dlp() -> bool:
    return YTDLP_AVAILABLE


def download_with_ytdlp(url: str, output_path: str, audio_only: bool = False, convert_mp3: bool = False,
                        progress_callback: Optional[Callable[[str, int, int, float, float], None]] = None,
                        progress_file: Optional[str] = None):
    """Download using yt-dlp programmatic API.

    progress_callback signature: fn(filename, received_bytes, total_bytes, speed_bytes_per_s, eta_seconds)
    Returns output filepath.
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError('yt-dlp is not available')

    ydl_opts = {
        'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
        'quiet': True,
    }
    if audio_only:
        # download best audio
        ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': []})
    # progress hook
    def _hook(d):
        status = d.get('status')
        if status == 'downloading':
            downloaded = d.get('downloaded_bytes') or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            speed = d.get('speed') or 0.0
            eta = d.get('eta') or 0
            filename = d.get('filename') or ''
            if progress_callback:
                try:
                    progress_callback(filename, downloaded, total, speed, eta)
                except Exception:
                    pass
            # write to progress file if provided
            if progress_file:
                try:
                    from progress_store import write_progress_file
                    write_progress_file(progress_file, {
                        'status': 'downloading',
                        'filename': filename,
                        'downloaded': int(downloaded),
                        'total': int(total),
                        'speed': float(speed),
                        'eta': int(eta),
                    })
                except Exception:
                    pass

    ydl_opts['progress_hooks'] = [_hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # try to determine filename
        if 'requested_downloads' in info and info['requested_downloads']:
            fname = info['requested_downloads'][0].get('filepath')
        else:
            fname = ydl.prepare_filename(info)
    # write completed status
    if progress_file:
        try:
            from progress_store import write_progress_file
            write_progress_file(progress_file, {
                'status': 'completed',
                'filename': fname,
            })
        except Exception:
            pass
        return fname


def download_fallback(url: str, output_path: str, audio_only: bool = False, convert_mp3: bool = False,
                      progress_callback: Optional[Callable[[str, int, int, float, float], None]] = None,
                      progress_file: Optional[str] = None):
    """Try pytube first, fallback to yt-dlp on error. progress_callback signature matches download_with_ytdlp.
    For pytube path we call progress_callback(filename, received, total, speed, eta) where speed/eta are estimated.
    """
    # Try pytube approach (single video)
    try:
        yt = YouTube(url)
        # pick best progressive
        streams = yt.streams.filter(progressive=True, file_extension='mp4')
        stream = None
        if streams:
            stream = sorted(streams, key=lambda s: int(s.resolution.replace('p','')) if s.resolution else 0, reverse=True)[0]
        else:
            # pick best adaptive video
            av = yt.streams.filter(only_video=True, file_extension='mp4')
            if av:
                stream = sorted(av, key=lambda s: int(s.resolution.replace('p','')) if s.resolution else 0, reverse=True)[0]

        if stream is None:
            raise RuntimeError('No suitable stream found for pytube')

        start = time.time()
        def _local_progress(received, total):
            now = time.time()
            elapsed = max(now - start, 1e-6)
            speed = received / elapsed
            eta = (total - received) / speed if speed > 0 else 0
            if progress_callback:
                try:
                    progress_callback(stream.default_filename if hasattr(stream, 'default_filename') else '', received, total, speed, int(eta))
                except Exception:
                    pass

        out = download_video(stream, output_path, progress_callback=_local_progress)
        return out
    except Exception:
        # fallback to yt-dlp if available
        if YTDLP_AVAILABLE:
            return download_with_ytdlp(url, output_path, audio_only=audio_only, convert_mp3=convert_mp3, progress_callback=progress_callback, progress_file=progress_file)
        raise


def download_playlist(playlist_url: str, output_path: str, resolution_preference: Optional[str] = None,
                      audio_only: bool = False, convert_mp3: bool = False, concurrency: int = 3,
                      per_item_callback: Optional[Callable[[str, str, str, int, int, int, float, int], None]] = None,
                      progress_dir: Optional[str] = None,
                      max_retries: int = 2, backoff_factor: float = 1.5) -> List[str]:
    """Download all videos in a playlist, optionally in parallel.

    - resolution_preference: '1080p', '720p', or None
    - audio_only: if True download audio streams
    - convert_mp3: if True and pydub+ffmpeg available convert audio to mp3
    - concurrency: max parallel downloads
    - per_item_callback: fn(title, status) called for status updates

    Returns list of downloaded file paths.
    """
    downloaded = []

    # Try to build a Playlist using pytube; if that fails, and yt-dlp is available,
    # try to extract the playlist entries using yt-dlp as a fallback.
    try:
        pl = Playlist(playlist_url)
        video_urls = pl.video_urls
    except Exception as e:
        # fallback: use yt-dlp to extract playlist entries (flat) if available
        if YTDLP_AVAILABLE:
            try:
                ydl_opts = {'quiet': True, 'extract_flat': True}
                video_urls = []
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(playlist_url, download=False)
                    entries = info.get('entries') or []
                    for entry in entries:
                        if isinstance(entry, dict):
                            url = entry.get('webpage_url') or entry.get('url')
                            if url:
                                video_urls.append(url)
            except Exception:
                raise RuntimeError(f'Could not parse playlist URL or extract entries: {e}')
        else:
            # re-raise with clearer message
            raise RuntimeError(f'Could not parse playlist URL: {e}. Install yt-dlp to enable fallback extraction.')

    if not video_urls:
        raise RuntimeError('No videos found in playlist')

    def _download_one(video_url, index=None):
        attempts = 0
        while attempts <= max_retries:
            try:
                streams = get_video_streams(video_url)
                title = streams['title']
                if audio_only:
                    if not streams['audio']:
                        return None, title, 'no-audio'
                    stream = streams['audio'][0]

                    def audio_cb(received, total):
                        if per_item_callback:
                            try:
                                per_item_callback(title, 'downloading', video_url, index, int(received), int(total), 0.0, 0.0)
                            except Exception:
                                pass
                        # write to per-item progress file if requested
                        if progress_dir:
                            try:
                                from progress_store import write_progress_file, progress_file_for_id
                                pf = progress_file_for_id(output_path, f'playlist_{index}')
                                write_progress_file(pf, {'title': title, 'status': 'downloading', 'downloaded': int(received), 'total': int(total)})
                            except Exception:
                                pass

                    out = download_audio(stream, output_path, filename=_safe_filename(title), convert_mp3=convert_mp3, progress_callback=audio_cb)
                    if per_item_callback:
                        try:
                            per_item_callback(title, 'completed', video_url, index, 0, 0, 0.0, 0.0)
                        except Exception:
                            pass
                    return out, title, 'ok'
                else:
                    # pick stream
                    stream = None
                    if resolution_preference:
                        for s in streams['progressive'] + streams['adaptive_video']:
                            if s.resolution == resolution_preference:
                                stream = s
                                break
                    if not stream:
                        if streams['progressive']:
                            stream = streams['progressive'][0]
                        elif streams['adaptive_video']:
                            stream = streams['adaptive_video'][0]
                    if stream is None:
                        return None, title, 'no-stream'

                    start_time = time.time()
                    last_received = {'v': 0}

                    def video_cb(received, total):
                        now = time.time()
                        elapsed = max(now - start_time, 1e-6)
                        speed = (received) / elapsed
                        eta = int((total - received) / speed) if speed > 0 else 0
                        last_received['v'] = received
                        if per_item_callback:
                            try:
                                per_item_callback(title, 'downloading', video_url, index, int(received), int(total), float(speed), int(eta))
                            except Exception:
                                pass
                        if progress_dir:
                            try:
                                from progress_store import write_progress_file, progress_file_for_id
                                pf = progress_file_for_id(output_path, f'playlist_{index}')
                                write_progress_file(pf, {'title': title, 'status': 'downloading', 'downloaded': int(received), 'total': int(total), 'speed': float(speed), 'eta': int(eta)})
                            except Exception:
                                pass

                    try:
                        out = download_video(stream, output_path, filename=_safe_filename(title), progress_callback=video_cb)
                        if per_item_callback:
                            try:
                                per_item_callback(title, 'completed', video_url, index, int(last_received['v']), 0, 0.0, 0.0)
                            except Exception:
                                pass
                        if progress_dir:
                            try:
                                from progress_store import write_progress_file, progress_file_for_id
                                pf = progress_file_for_id(output_path, f'playlist_{index}')
                                write_progress_file(pf, {'title': title, 'status': 'completed', 'downloaded': int(last_received['v'])})
                            except Exception:
                                pass
                        return out, title, 'ok'
                    except Exception:
                        # try yt-dlp for this single item if available
                        if YTDLP_AVAILABLE:
                            def ytdlp_cb(fn, downloaded, total, speed, eta):
                                if per_item_callback:
                                    try:
                                        per_item_callback(title, 'downloading', video_url, index, int(downloaded or 0), int(total or 0), float(speed or 0.0), int(eta or 0))
                                    except Exception:
                                        pass

                            out = download_with_ytdlp(video_url, output_path, audio_only=False, progress_callback=ytdlp_cb)
                            if per_item_callback:
                                try:
                                    per_item_callback(title, 'completed', video_url, index, 0, 0, 0.0, 0.0)
                                except Exception:
                                    pass
                            return out, title, 'ok'
                        else:
                            raise
            except Exception as e:
                attempts += 1
                if attempts > max_retries:
                    return None, video_url, f'error:{e}'
                # backoff
                sleep_time = backoff_factor * (2 ** (attempts - 1))
                time.sleep(sleep_time)

    futures = []
    fut_map = {}
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for i, video_url in enumerate(video_urls):
            fut = ex.submit(_download_one, video_url, i)
            futures.append(fut)
            fut_map[fut] = (video_url, i)

        for fut in as_completed(futures):
            out, title, status = fut.result()
            meta = fut_map.get(fut, (None, None))
            video_url_meta, index_meta = meta
            if per_item_callback:
                try:
                    per_item_callback(title, status, video_url_meta, index_meta)
                except Exception:
                    pass
            if status == 'ok' and out:
                downloaded.append(out)

    return downloaded


def _safe_filename(title):
    # basic sanitization for filenames
    keepchars = (" ._-()[]")
    return "".join(c for c in title if c.isalnum() or c in keepchars).strip()
