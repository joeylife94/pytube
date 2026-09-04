"""Authoritative yt-dlp download core.

All runtime paths that need yt-dlp download execution should converge here.
UI/API/queue layers may adapt their own request models and progress displays, but
format selection, cookies, proxy, ffmpeg handling, JS runtime configuration,
and actual YoutubeDL execution belong in this module.
"""

from __future__ import annotations

import os
import shutil
from typing import Any, Callable, Dict, List, Optional

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal installs
    yt_dlp = None
    YTDLP_AVAILABLE = False


ProgressCallback = Callable[[str, int, int, float, float], None]


def get_ffmpeg_location_from_env() -> Optional[str]:
    """Return an explicitly configured ffmpeg binary/directory, if present."""
    for key in ("FFMPEG_LOCATION", "FFMPEG_PATH", "FFMPEG_BIN"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def _create_progress_hook(
    progress_callback: Optional[ProgressCallback],
    progress_file: Optional[str],
) -> Callable[[Dict[str, Any]], None]:
    """Create the single yt-dlp progress hook used by all core downloads."""

    def _hook(data: Dict[str, Any]) -> None:
        if data.get("status") != "downloading":
            return

        downloaded = int(data.get("downloaded_bytes", 0) or 0)
        total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
        speed = float(data.get("speed") or 0.0)
        eta = int(data.get("eta") or 0)
        filename = data.get("filename", "") or ""

        if progress_callback:
            try:
                progress_callback(filename, downloaded, total, speed, eta)
            except Exception:
                # UI/observer callback failures must not abort the media transfer.
                pass

        if progress_file:
            try:
                from progress_store import write_progress_file

                write_progress_file(
                    progress_file,
                    {
                        "status": "downloading",
                        "filename": filename,
                        "downloaded": downloaded,
                        "total": total,
                        "speed": speed,
                        "eta": eta,
                    },
                )
            except Exception:
                # Progress persistence is observability-only and must never abort a
                # successful media download.
                pass

    return _hook


def _auto_cookiefile(explicit_cookiefile: Optional[str]) -> Optional[str]:
    """Resolve an explicit or conventional workspace cookies.txt file."""
    if explicit_cookiefile:
        return explicit_cookiefile if os.path.isfile(explicit_cookiefile) else None

    search_dirs = [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]
    for search_dir in search_dirs:
        for candidate in ("cookies.txt", "www.youtube.com_cookies.txt"):
            path = os.path.join(search_dir, candidate)
            if os.path.isfile(path):
                return path
    return None


def build_ytdlp_options(
    output_path: str,
    *,
    audio_only: bool = False,
    convert_mp3: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    progress_file: Optional[str] = None,
    subtitle_langs: Optional[List[str]] = None,
    rate_limit_kbps: int = 0,
    cookies_from_browser: Optional[str] = None,
    resolution: Optional[str] = None,
    filename_template: Optional[str] = None,
    proxy: Optional[str] = None,
    cookiefile: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the canonical yt-dlp option dictionary for a download.

    This function is intentionally side-effect-light so queue/API adapters and unit
    tests can validate option semantics without making network requests.
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError("yt-dlp is not available")

    template = filename_template or "%(title)s"
    options: Dict[str, Any] = {
        "outtmpl": os.path.join(output_path, f"{template}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"],
                "player_skip": ["configs"],
            }
        },
        "nocheckcertificate": True,
        "no_check_certificate": True,
        "age_limit": None,
    }

    ffmpeg_location = get_ffmpeg_location_from_env()
    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location

    if audio_only and convert_mp3:
        if not ffmpeg_location and shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "MP3 conversion requires ffmpeg. Install ffmpeg and ensure it's on PATH, "
                "or set FFMPEG_LOCATION (or FFMPEG_PATH/FFMPEG_BIN) to the ffmpeg binary or directory."
            )

    if audio_only:
        options["format"] = "bestaudio/best"
        if convert_mp3:
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            options["postprocessors"] = []
    elif resolution and resolution != "best":
        res_num = resolution.replace("p", "").replace("k", "000").replace("K", "000")
        options["format"] = (
            f"bestvideo[height<={res_num}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={res_num}]+bestaudio"
            f"/best[height<={res_num}]/best"
        )
        options["merge_output_format"] = "mp4"

    if subtitle_langs:
        options["writesubtitles"] = True
        options["writeautomaticsub"] = True
        options["subtitleslangs"] = list(subtitle_langs)
        options["subtitlesformat"] = "srt/best"

    if rate_limit_kbps and rate_limit_kbps > 0:
        options["ratelimit"] = rate_limit_kbps * 1024

    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)

    resolved_cookiefile = _auto_cookiefile(cookiefile)
    if resolved_cookiefile:
        options["cookiefile"] = resolved_cookiefile

    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
        options["remote_components"] = ["ejs:github"]

    if proxy:
        options["proxy"] = proxy

    options["progress_hooks"] = [_create_progress_hook(progress_callback, progress_file)]
    return options


def _get_downloaded_filename(ydl: Any, info: Dict[str, Any]) -> str:
    requested = info.get("requested_downloads") or []
    if requested:
        return requested[0].get("filepath") or ydl.prepare_filename(info)
    return ydl.prepare_filename(info)


def _write_completion_status(progress_file: Optional[str], filename: str) -> None:
    if not progress_file:
        return
    try:
        from progress_store import write_progress_file

        write_progress_file(progress_file, {"status": "completed", "filename": filename})
    except Exception:
        pass


def download_with_ytdlp(
    url: str,
    output_path: str,
    audio_only: bool = False,
    convert_mp3: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    progress_file: Optional[str] = None,
    subtitle_langs: Optional[List[str]] = None,
    rate_limit_kbps: int = 0,
    cookies_from_browser: Optional[str] = None,
    resolution: Optional[str] = None,
    filename_template: Optional[str] = None,
    proxy: Optional[str] = None,
    cookiefile: Optional[str] = None,
) -> str:
    """Execute a download through the authoritative yt-dlp core."""
    if not YTDLP_AVAILABLE:
        raise RuntimeError("yt-dlp is not available")

    os.makedirs(output_path, exist_ok=True)
    options = build_ytdlp_options(
        output_path,
        audio_only=audio_only,
        convert_mp3=convert_mp3,
        progress_callback=progress_callback,
        progress_file=progress_file,
        subtitle_langs=subtitle_langs,
        rate_limit_kbps=rate_limit_kbps,
        cookies_from_browser=cookies_from_browser,
        resolution=resolution,
        filename_template=filename_template,
        proxy=proxy,
        cookiefile=cookiefile,
    )

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = _get_downloaded_filename(ydl, info)

    if audio_only and convert_mp3 and filename:
        base, _ext = os.path.splitext(filename)
        filename = base + ".mp3"

    _write_completion_status(progress_file, filename)
    return filename
