import os
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pytube import YouTube, Playlist
from pytube.cli import on_progress
from typing import Callable, Optional, List, Dict, Tuple, Any
import time
import math
from urllib.parse import urlparse, parse_qs
import logging

# Constants
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_FACTOR = 1.5
DEFAULT_CONCURRENCY = 3
SAFE_FILENAME_CHARS = " ._-()[]"

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
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


def _get_video_streams_with_ytdlp(url: str, original_error: Exception) -> Dict[str, Any]:
    """Fallback to yt-dlp for fetching video metadata.
    
    Args:
        url: YouTube video URL
        original_error: The exception from the pytube attempt
        
    Returns:
        Dictionary with minimal metadata from yt-dlp
        
    Raises:
        RuntimeError: If yt-dlp is not available or also fails
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError(
            f'pytube failed to fetch metadata for {url}: {original_error}.\n'
            'Consider installing yt-dlp (`pip install yt-dlp`) to enable a fallback or check the URL/connection.'
        ) from original_error
    
    try:
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            'backend': 'yt-dlp',
            'title': info.get('title'),
            'yt_dlp_info': info,
        }
    except Exception as ytdlp_error:
        logger.exception('yt-dlp fallback also failed for url=%s', url)
        raise RuntimeError(f'Failed to fetch metadata via yt-dlp for {url}') from ytdlp_error


def get_video_streams(url: str) -> Dict[str, Any]:
    """Return available streams for a YouTube URL.

    Args:
        url: YouTube video URL

    Returns:
        Dictionary with 'title', 'progressive', 'adaptive_video', 'audio' lists,
        and 'backend' indicating which library was used.

    Raises:
        RuntimeError: If metadata cannot be fetched by either pytube or yt-dlp
    """
    # Try pytube first. If it fails (e.g. HTTP 400 from innertube), and yt-dlp is
    # available, fall back to yt-dlp metadata extraction so the UI can continue.
    try:
        norm_url = _normalize_video_url(url)
        if norm_url != url:
            logger.info('Normalized URL: %s -> %s', url, norm_url)
        yt = YouTube(norm_url, on_progress_callback=on_progress)
        progressive = sorted(
            [s for s in yt.streams.filter(progressive=True, file_extension='mp4')],
            key=lambda s: int(s.resolution.replace('p', '')) if s.resolution else 0,
            reverse=True
        )
        adaptive_video = sorted(
            [s for s in yt.streams.filter(only_video=True, file_extension='mp4')],
            key=lambda s: int(s.resolution.replace('p', '')) if s.resolution else 0,
            reverse=True
        )
        audio_streams = sorted(
            [s for s in yt.streams.filter(only_audio=True)],
            key=lambda s: int(s.abr.replace('kbps', '')) if s.abr else 0,
            reverse=True
        )
        return {
            'backend': 'pytube',
            'title': yt.title,
            'progressive': progressive,
            'adaptive_video': adaptive_video,
            'audio': audio_streams,
        }
    except Exception as e:
        logger.exception('pytube failed to fetch metadata for url=%s', url)
        return _get_video_streams_with_ytdlp(url, e)


def download_video(stream, output_path: str, filename: Optional[str] = None, 
                   progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
    """Download a pytube Stream object to output_path.
    
    Args:
        stream: pytube Stream object
        output_path: Directory to save the file
        filename: Optional custom filename
        progress_callback: Optional callback(bytes_received, total_bytes)
    
    Returns:
        Path to the downloaded file
    """
    if progress_callback:
        return _download_with_progress(stream, output_path, filename, progress_callback)
    else:
        return stream.download(output_path=output_path, filename=filename) if filename else stream.download(output_path=output_path)


def _download_with_progress(stream, output_path: str, filename: Optional[str],
                            progress_callback: Callable[[int, int], None]) -> str:
    """Helper function to download with progress tracking.

    Args:
        stream: pytube Stream object
        output_path: Directory to save the file
        filename: Optional custom filename
        progress_callback: Callback(bytes_received, total_bytes)

    Returns:
        Path to the downloaded file
    """
    # pytube 15.x removed player_config_args, so per-chunk progress tracking via
    # register_on_progress_callback is not reachable through a stream object alone.
    # Fall back to a direct stream download (progress callback is silently ignored).
    return stream.download(output_path=output_path, filename=filename) if filename else stream.download(output_path=output_path)


def download_audio(stream, output_path: str, filename: Optional[str] = None, 
                   convert_mp3: bool = False, 
                   progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
    """Download audio-only stream. If convert_mp3 and pydub+ffmpeg available, convert to mp3.

    Args:
        stream: pytube Stream object
        output_path: Directory to save the file
        filename: Optional custom filename
        convert_mp3: Whether to convert to MP3 format
        progress_callback: Optional callback(bytes_received, total_bytes)
        
    Returns:
        Path to the downloaded file
    """
    if progress_callback:
        base_out = _download_with_progress(stream, output_path, filename, progress_callback)
    else:
        base_out = stream.download(output_path=output_path, filename=filename) if filename else stream.download(output_path=output_path)

    return _convert_to_mp3_if_needed(base_out, convert_mp3)


def _convert_to_mp3_if_needed(audio_file: str, convert_mp3: bool) -> str:
    """Convert audio file to MP3 if requested and tools are available.
    
    Args:
        audio_file: Path to the audio file
        convert_mp3: Whether to convert to MP3
        
    Returns:
        Path to the final audio file (MP3 or original)
    """
    if not convert_mp3 or not PYDUB_AVAILABLE or not is_ffmpeg_available():
        return audio_file
    
    try:
        name, _ext = os.path.splitext(audio_file)
        mp3_path = name + '.mp3'
        audio = AudioSegment.from_file(audio_file)
        audio.export(mp3_path, format='mp3')
        # Remove the original (non-MP3) file to avoid leaving duplicates on disk
        try:
            os.remove(audio_file)
        except OSError as rm_err:
            logger.warning(f'Could not remove original audio file {audio_file}: {rm_err}')
        return mp3_path
    except Exception as e:
        logger.error(f'Failed to convert to MP3: {e}')
        return audio_file


def has_yt_dlp() -> bool:
    return YTDLP_AVAILABLE


def _get_ffmpeg_location_from_env() -> Optional[str]:
    """Return ffmpeg location from env vars if configured.

    yt-dlp supports `ffmpeg_location` pointing to an ffmpeg binary or a directory.
    We keep this optional so normal PATH-based resolution still works.
    """
    for key in ("FFMPEG_LOCATION", "FFMPEG_PATH", "FFMPEG_BIN"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def download_with_ytdlp(url: str, output_path: str, audio_only: bool = False, 
                        convert_mp3: bool = False,
                        progress_callback: Optional[Callable[[str, int, int, float, float], None]] = None,
                        progress_file: Optional[str] = None,
                        subtitle_langs: Optional[List[str]] = None,
                        rate_limit_kbps: int = 0) -> str:
    """Download using yt-dlp programmatic API.

    Args:
        url: YouTube video URL
        output_path: Directory to save the file
        audio_only: Whether to download audio only
        convert_mp3: Whether to convert to MP3 (for audio)
        progress_callback: Optional callback(filename, received_bytes, total_bytes, speed, eta)
        progress_file: Optional path to write progress updates
        subtitle_langs: Optional list of subtitle language codes (e.g. ['en', 'ko'])
        rate_limit_kbps: Download speed limit in KB/s (0 = unlimited)
        
    Returns:
        Path to the downloaded file
        
    Raises:
        RuntimeError: If yt-dlp is not available
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError('yt-dlp is not available')

    # sensible defaults (mimic options used in downloader_manager._build_ytdlp_opts)
    ydl_opts = {
        'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web'],
                'player_skip': ['configs'],
            }
        },
        'nocheckcertificate': True,
        'no_check_certificate': True,
        'age_limit': None,
    }

    ffmpeg_location = _get_ffmpeg_location_from_env()
    if ffmpeg_location:
        ydl_opts['ffmpeg_location'] = ffmpeg_location

    if audio_only and convert_mp3:
        # yt-dlp invokes ffmpeg for FFmpegExtractAudio; fail early with a clear message.
        if not ffmpeg_location and shutil.which('ffmpeg') is None:
            raise RuntimeError(
                "MP3 conversion requires ffmpeg. Install ffmpeg and ensure it's on PATH, "
                "or set FFMPEG_LOCATION (or FFMPEG_PATH/FFMPEG_BIN) to the ffmpeg binary or directory."
            )

    if audio_only:
        ydl_opts['format'] = 'bestaudio/best'
        if convert_mp3:
            # Convert to MP3 using ffmpeg via yt-dlp postprocessor.
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            ydl_opts['postprocessors'] = []
    
    # Subtitles
    if subtitle_langs:
        ydl_opts['writesubtitles'] = True
        ydl_opts['writeautomaticsub'] = True
        ydl_opts['subtitleslangs'] = list(subtitle_langs)
        ydl_opts['subtitlesformat'] = 'srt/best'

    # Speed limit
    if rate_limit_kbps and rate_limit_kbps > 0:
        ydl_opts['ratelimit'] = rate_limit_kbps * 1024  # convert KB/s to B/s

    ydl_opts['progress_hooks'] = [_create_ytdlp_progress_hook(progress_callback, progress_file)]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        fname = _get_downloaded_filename(ydl, info)

    # yt-dlp returns the pre-postprocess filename in many cases; if we requested
    # MP3 conversion, the final file should be the same base name with .mp3.
    if audio_only and convert_mp3 and fname:
        base, _ext = os.path.splitext(fname)
        fname = base + '.mp3'
    
    _write_completion_status(progress_file, fname)
    return fname


def _create_ytdlp_progress_hook(progress_callback: Optional[Callable], 
                                progress_file: Optional[str]) -> Callable:
    """Create a progress hook for yt-dlp downloads.
    
    Args:
        progress_callback: Optional callback for progress updates
        progress_file: Optional file path to write progress
        
    Returns:
        Progress hook function
    """
    def _hook(d: Dict[str, Any]):
        if d.get('status') != 'downloading':
            return
            
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        speed = d.get('speed') or 0.0  # yt-dlp returns None during initial buffering
        eta = d.get('eta') or 0
        filename = d.get('filename', '')
        
        if progress_callback:
            try:
                progress_callback(filename, downloaded, total, speed, eta)
            except Exception as e:
                logger.warning(f'Progress callback error: {e}')
        
        if progress_file:
            try:
                from progress_store import write_progress_file
                write_progress_file(progress_file, {
                    'status': 'downloading',
                    'filename': filename,
                    'downloaded': int(downloaded),
                    'total': int(total),
                    'speed': float(speed or 0.0),
                    'eta': int(eta or 0),
                })
            except Exception as e:
                logger.warning(f'Failed to write progress file: {e}')
    
    return _hook


def _get_downloaded_filename(ydl, info: Dict[str, Any]) -> str:
    """Extract the downloaded filename from yt-dlp info.
    
    Args:
        ydl: YoutubeDL instance
        info: Download info dictionary
        
    Returns:
        Path to the downloaded file
    """
    if 'requested_downloads' in info and info['requested_downloads']:
        return info['requested_downloads'][0].get('filepath')
    return ydl.prepare_filename(info)


def _write_completion_status(progress_file: Optional[str], filename: str):
    """Write completion status to progress file if provided.
    
    Args:
        progress_file: Optional progress file path
        filename: Downloaded file path
    """
    if not progress_file:
        return
        
    try:
        from progress_store import write_progress_file
        write_progress_file(progress_file, {
            'status': 'completed',
            'filename': filename,
        })
    except Exception as e:
        logger.warning(f'Failed to write completion status: {e}')


def download_fallback(url: str, output_path: str, audio_only: bool = False, 
                      convert_mp3: bool = False,
                      progress_callback: Optional[Callable[[str, int, int, float, float], None]] = None,
                      progress_file: Optional[str] = None) -> str:
    """Try pytube first, fallback to yt-dlp on error.
    
    Args:
        url: YouTube video URL
        output_path: Directory to save the file
        audio_only: Whether to download audio only
        convert_mp3: Whether to convert to MP3
        progress_callback: Optional callback(filename, received, total, speed, eta)
        progress_file: Optional progress file path
        
    Returns:
        Path to the downloaded file
        
    Raises:
        Exception: If both pytube and yt-dlp fail
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


def download_playlist(playlist_url: str, output_path: str,
                      resolution_preference: Optional[str] = None,
                      audio_only: bool = False, convert_mp3: bool = False,
                      concurrency: int = DEFAULT_CONCURRENCY,
                      max_items: Optional[int] = None,
                      per_item_callback: Optional[Callable] = None,
                      prefer_ytdlp: bool = True,
                      progress_dir: Optional[str] = None,
                      max_retries: int = DEFAULT_MAX_RETRIES,
                      backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
                      subtitle_langs: Optional[List[str]] = None,
                      rate_limit_kbps: int = 0,
                      preset_urls: Optional[List[str]] = None) -> List[str]:
    """Download all videos in a playlist, optionally in parallel.

    Args:
        playlist_url: URL of the YouTube playlist
        output_path: Directory to save files
        resolution_preference: Preferred resolution (e.g., '1080p', '720p') or None for highest
        audio_only: Whether to download audio only
        convert_mp3: Whether to convert audio to MP3
        concurrency: Maximum number of parallel downloads
        per_item_callback: Optional callback for per-item status updates
        progress_dir: Optional directory for progress files
        max_retries: Maximum number of retry attempts per video
        backoff_factor: Exponential backoff factor for retries

    Returns:
        List of paths to downloaded files
        
    Raises:
        RuntimeError: If playlist cannot be parsed or no videos found
    """
    downloaded = []

    # Clean up leftover .part files to prevent WinError 32 rename failures
    cleanup_part_files(output_path)

    # Extract playlist URLs (skip extraction when caller provides pre-fetched list)
    if preset_urls is not None:
        video_urls = list(preset_urls)
    elif YTDLP_AVAILABLE:
        try:
            video_urls = _extract_playlist_urls_with_ytdlp(playlist_url)
        except Exception:
            video_urls = _extract_playlist_urls(playlist_url)
    else:
        video_urls = _extract_playlist_urls(playlist_url)

    if max_items is not None:
        try:
            max_n = int(max_items)
        except Exception:
            max_n = 0
        if max_n > 0:
            video_urls = video_urls[:max_n]

    total_items = len(video_urls)
    logger.info('Playlist has %d items to download', total_items)

    def _notify(title, status, video_url, index):
        """Safely invoke per_item_callback with a consistent 4-arg signature."""
        if per_item_callback:
            try:
                per_item_callback(title, status, video_url, index)
            except Exception:
                pass

    def _download_one_item(video_url, index):
        """Download a single playlist item. Always uses yt-dlp when available."""
        attempts = 0
        while attempts <= max_retries:
            try:
                _notify(video_url, f'downloading ({index+1}/{total_items})', video_url, index)

                if YTDLP_AVAILABLE:
                    out = download_with_ytdlp(
                        video_url, output_path,
                        audio_only=audio_only,
                        convert_mp3=convert_mp3,
                        subtitle_langs=subtitle_langs,
                        rate_limit_kbps=rate_limit_kbps,
                    )
                else:
                    # Fallback to pytube for environments without yt-dlp
                    streams = get_video_streams(video_url)
                    if audio_only:
                        if not streams.get('audio'):
                            return None, video_url, 'no-audio'
                        stream = streams['audio'][0]
                        out = download_audio(stream, output_path,
                                             filename=_safe_filename(streams.get('title', 'audio')),
                                             convert_mp3=convert_mp3)
                    else:
                        stream = None
                        if resolution_preference:
                            for s in streams.get('progressive', []) + streams.get('adaptive_video', []):
                                if s.resolution == resolution_preference:
                                    stream = s
                                    break
                        if not stream:
                            if streams.get('progressive'):
                                stream = streams['progressive'][0]
                            elif streams.get('adaptive_video'):
                                stream = streams['adaptive_video'][0]
                        if stream is None:
                            return None, streams.get('title', video_url), 'no-stream'
                        out = download_video(stream, output_path,
                                             filename=_safe_filename(streams.get('title', 'video')))

                _notify(out or video_url, f'completed ({index+1}/{total_items})', video_url, index)
                return out, video_url, 'ok'

            except Exception as e:
                attempts += 1
                if attempts > max_retries:
                    logger.error('Failed to download %s after %d attempts: %s', video_url, max_retries, e)
                    _notify(video_url, f'error: {e}', video_url, index)
                    return None, video_url, f'error:{e}'
                sleep_time = backoff_factor * (2 ** (attempts - 1))
                logger.warning('Retrying %s in %.1fs (attempt %d/%d)', video_url, sleep_time, attempts, max_retries)
                time.sleep(sleep_time)

    # Execute downloads (sequential or parallel)
    futures = []
    fut_map = {}
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for i, video_url in enumerate(video_urls):
            fut = ex.submit(_download_one_item, video_url, i)
            futures.append(fut)
            fut_map[fut] = (video_url, i)

        for fut in as_completed(futures):
            out, title, status = fut.result()
            if status == 'ok' and out:
                downloaded.append(out)

    logger.info('Playlist download complete: %d/%d items succeeded', len(downloaded), total_items)
    return downloaded


def _extract_playlist_urls(playlist_url: str) -> List[str]:
    """Extract video URLs from a playlist.
    
    Args:
        playlist_url: URL of the YouTube playlist
        
    Returns:
        List of video URLs
        
    Raises:
        RuntimeError: If playlist cannot be parsed or no videos found
    """
    try:
        pl = Playlist(playlist_url)
        # force evaluation of the playlist generator so extraction errors
        # from pytube are raised here and can be caught for fallback.
        video_urls = list(pl.video_urls)
    except Exception as e:
        if not YTDLP_AVAILABLE:
            raise RuntimeError(
                f'Could not parse playlist URL: {e}. '
                'Install yt-dlp to enable fallback extraction.'
            ) from e

        try:
            video_urls = _extract_playlist_urls_with_ytdlp(playlist_url)
        except Exception as ytdlp_error:
            raise RuntimeError(
                f'Could not parse playlist URL or extract entries: {e} / {ytdlp_error}'
            ) from ytdlp_error
    
    if not video_urls:
        raise RuntimeError('No videos found in playlist')
    
    return video_urls


def extract_playlist_urls(playlist_url: str) -> List[str]:
    """Public wrapper for playlist URL extraction with yt-dlp fallback."""
    return _extract_playlist_urls(playlist_url)


def extract_playlist_urls_with_titles(playlist_url: str) -> Dict[str, Any]:
    """Extract playlist URLs AND titles in one pass using yt-dlp.

    Returns a dict:
        {
            'playlist_title': 'My Playlist',
            'items': [{'url': '...', 'title': '...'}, ...]
        }
    Falls back to URL-only extraction if yt-dlp is not available.
    """
    playlist_title = 'Playlist'
    if YTDLP_AVAILABLE:
        try:
            results = []
            ydl_opts = {'quiet': True, 'extract_flat': True, 'no_warnings': True, 'ignoreerrors': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                playlist_title = info.get('title') or 'Playlist'
                entries = info.get('entries') or []
                for entry in entries:
                    if isinstance(entry, dict):
                        url = entry.get('webpage_url') or entry.get('url') or ''
                        title = entry.get('title') or url
                        if url:
                            results.append({'url': url, 'title': title})
            if results:
                return {'playlist_title': playlist_title, 'items': results}
        except Exception as e:
            logger.warning('yt-dlp flat extraction failed: %s', e)

    # Fallback: extract URLs only, use URL as title
    urls = _extract_playlist_urls(playlist_url)
    return {'playlist_title': playlist_title, 'items': [{'url': u, 'title': u} for u in urls]}


def cleanup_part_files(output_path: str) -> int:
    """Remove leftover .part files in the output directory to avoid WinError 32.

    Returns the number of files removed.
    """
    removed = 0
    try:
        for f in os.listdir(output_path):
            if f.endswith('.part'):
                fpath = os.path.join(output_path, f)
                try:
                    os.remove(fpath)
                    removed += 1
                    logger.info('Removed leftover .part file: %s', fpath)
                except OSError as e:
                    logger.warning('Could not remove .part file %s: %s', fpath, e)
    except Exception as e:
        logger.warning('Error scanning for .part files: %s', e)
    return removed


def extract_channel_videos(channel_url: str, max_items: Optional[int] = None) -> Dict[str, Any]:
    """Extract all video URLs from a YouTube channel.

    Args:
        channel_url: YouTube channel URL (e.g. https://www.youtube.com/@ChannelName)
        max_items: Maximum number of videos to extract (None = all)

    Returns:
        Dict with 'channel_title' and 'items' list of {'url', 'title'} dicts.
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError('Channel extraction requires yt-dlp')

    channel_title = 'Channel'
    items = []
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'no_warnings': True,
    }
    if max_items and max_items > 0:
        ydl_opts['playlistend'] = max_items

    try:
        # Ensure we target the /videos tab for channel URLs
        normalized = channel_url.strip().rstrip('/')
        if '/@' in normalized or '/channel/' in normalized or '/c/' in normalized:
            if not normalized.endswith('/videos'):
                normalized += '/videos'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(normalized, download=False)
            channel_title = info.get('channel') or info.get('uploader') or info.get('title') or 'Channel'
            entries = info.get('entries') or []
            for entry in entries:
                if isinstance(entry, dict):
                    url = entry.get('webpage_url') or entry.get('url') or ''
                    title = entry.get('title') or url
                    if url:
                        items.append({'url': url, 'title': title})
    except Exception as e:
        logger.error('Channel extraction failed: %s', e)
        raise RuntimeError(f'Failed to extract channel videos: {e}') from e

    return {'channel_title': channel_title, 'items': items}


def _extract_playlist_urls_with_ytdlp(playlist_url: str) -> List[str]:
    """Extract playlist URLs using yt-dlp.
    
    Args:
        playlist_url: URL of the YouTube playlist
        
    Returns:
        List of video URLs
    """
    # Try an initial shallow extraction (fast). If that returns no entries
    # some playlist pages require full extraction — retry with
    # `extract_flat=False` to obtain concrete entries.
    video_urls = []
    ydl_opts = {'quiet': True, 'extract_flat': True, 'ignoreerrors': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
        entries = info.get('entries') or []
        for entry in entries:
            if isinstance(entry, dict):
                url = entry.get('webpage_url') or entry.get('url')
                if url:
                    video_urls.append(url)

    if not video_urls:
        # Fall back to full extraction (may be slower) to collect entries.
        ydl_opts = {'quiet': True, 'extract_flat': False, 'ignoreerrors': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get('entries') or []
            for entry in entries:
                if isinstance(entry, dict):
                    url = entry.get('webpage_url') or entry.get('url')
                    if url:
                        video_urls.append(url)
    
    return video_urls


def _safe_filename(title: str) -> str:
    """Sanitize a title for use as a filename.
    
    Args:
        title: Original title string
        
    Returns:
        Sanitized filename-safe string
    """
    return "".join(c for c in title if c.isalnum() or c in SAFE_FILENAME_CHARS).strip()
