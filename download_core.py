"""Authoritative yt-dlp download core.

All runtime paths that need yt-dlp download execution should converge here.
UI/API/queue layers may adapt their own request models and progress displays, but
format selection, cookies, proxy, ffmpeg handling, JS runtime configuration,
and actual YoutubeDL execution belong in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional

from download_errors import DownloadCancelled

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal installs
    yt_dlp = None
    YTDLP_AVAILABLE = False

try:
    # Installed by yt-dlp[default]; bundles the YouTube JS challenge solver locally.
    import yt_dlp_ejs  # noqa: F401
    YTDLP_EJS_AVAILABLE = True
except ImportError:
    YTDLP_EJS_AVAILABLE = False


ProgressCallback = Callable[[str, int, int, float, float], None]

# Hidden per-download working folders inside the output folder (see download_with_ytdlp_result)
STAGING_PREFIX = ".dl-"


@dataclass(frozen=True)
class DownloadResult:
    """Stable result returned by the core to adapters that need metadata."""

    filepath: str
    title: str = ""


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
            except DownloadCancelled:
                # The only callback exception allowed to stop the transfer.
                raise
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
    subtitles_only: bool = False,
    convert_subtitles_to_srt: bool = False,
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

    YouTube client selection and User-Agent are left to yt-dlp's defaults: forcing
    the android/ios clients drops most formats (including audio-only ones) now that
    YouTube serves those clients SABR-only streams.
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError("yt-dlp is not available")

    template = filename_template or "%(title)s"
    options: Dict[str, Any] = {
        "outtmpl": os.path.join(output_path, f"{template}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
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

    if subtitles_only:
        options["skip_download"] = True
    elif audio_only:
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
    else:
        # Highest resolution first; at equal resolution prefer mp4/m4a so the merged
        # file is a widely playable .mp4 instead of .webm.
        options["format_sort"] = ["res", "ext:mp4:m4a"]
        if resolution and resolution != "best":
            res_num = resolution.replace("p", "").replace("k", "000").replace("K", "000")
            options["format"] = (
                f"bv*[height<={res_num}]+ba/b[height<={res_num}]/bv*+ba/b"
            )

    if subtitle_langs or subtitles_only:
        options["writesubtitles"] = True
        options["writeautomaticsub"] = True
        options["subtitleslangs"] = list(subtitle_langs or ["en"])
        options["subtitlesformat"] = "srt/best"
        if convert_subtitles_to_srt:
            options.setdefault("postprocessors", []).append(
                {
                    "key": "FFmpegSubtitlesConvertor",
                    "format": "srt",
                }
            )

    if rate_limit_kbps and rate_limit_kbps > 0:
        options["ratelimit"] = rate_limit_kbps * 1024

    if cookies_from_browser:
        options["cookiesfrombrowser"] = (cookies_from_browser,)

    resolved_cookiefile = _auto_cookiefile(cookiefile)
    if resolved_cookiefile:
        options["cookiefile"] = resolved_cookiefile

    # JS runtime for YouTube's n-challenge / SABR-protected videos. The solver script
    # comes from yt-dlp-ejs when installed, otherwise yt-dlp fetches it from GitHub.
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
        if not YTDLP_EJS_AVAILABLE:
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


def download_with_ytdlp_result(
    url: str,
    output_path: str,
    audio_only: bool = False,
    convert_mp3: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    progress_file: Optional[str] = None,
    subtitle_langs: Optional[List[str]] = None,
    subtitles_only: bool = False,
    convert_subtitles_to_srt: bool = False,
    rate_limit_kbps: int = 0,
    cookies_from_browser: Optional[str] = None,
    resolution: Optional[str] = None,
    filename_template: Optional[str] = None,
    proxy: Optional[str] = None,
    cookiefile: Optional[str] = None,
) -> DownloadResult:
    """Execute a download and return the stable adapter-facing result.

    yt-dlp writes into a private staging folder inside output_path and the
    finished files are then moved next to the user's other downloads. Without
    this, an audio download whose intermediate file shares a name with an
    earlier video (e.g. both "Title.webm") is treated as "already downloaded",
    converted from the video, and the video is deleted afterwards. It also keeps
    concurrent downloads of same-titled videos from sharing .part files.
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError("yt-dlp is not available")

    os.makedirs(output_path, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=output_path)
    try:
        options = build_ytdlp_options(
            staging,
            audio_only=audio_only,
            convert_mp3=convert_mp3,
            progress_callback=progress_callback,
            progress_file=progress_file,
            subtitle_langs=subtitle_langs,
            subtitles_only=subtitles_only,
            convert_subtitles_to_srt=convert_subtitles_to_srt,
            rate_limit_kbps=rate_limit_kbps,
            cookies_from_browser=cookies_from_browser,
            resolution=resolution,
            filename_template=filename_template,
            proxy=proxy,
            cookiefile=cookiefile,
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = "" if subtitles_only else _get_downloaded_filename(ydl, info)

        if audio_only and convert_mp3 and filename:
            base, _ext = os.path.splitext(filename)
            filename = base + ".mp3"

        moved = _move_staged_files(staging, output_path)
        if subtitles_only:
            title = info.get("title", "subtitle") or "subtitle"
            filename = os.path.join(output_path, f"{title}.*.srt")
        elif filename:
            key = os.path.normcase(os.path.abspath(filename))
            filename = moved.get(key, filename)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    _write_completion_status(progress_file, filename)
    return DownloadResult(filepath=filename, title=info.get("title", "") or "")


def _reserve_unique_path(path: str) -> str:
    """Atomically claim path, or "name (1).ext", "name (2).ext", ... if taken.

    The name is reserved by creating an empty placeholder with O_EXCL, so two
    workers (or the web UI and API processes) finishing same-named files at the
    same moment can never pick the same destination.
    """
    base, ext = os.path.splitext(path)
    n = 0
    while True:
        candidate = path if n == 0 else f"{base} ({n}){ext}"
        try:
            os.close(os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return candidate
        except FileExistsError:
            n += 1


def _move_staged_files(staging: str, output_path: str) -> Dict[str, str]:
    """Move finished files from staging into output_path without overwriting anything.

    Returns {normcase(abs staged path): final path}.
    """
    moved: Dict[str, str] = {}
    for root, _dirs, files in os.walk(staging):
        for name in files:
            if name.endswith((".part", ".ytdl", ".temp")):
                continue
            src = os.path.join(root, name)
            target = os.path.join(output_path, os.path.relpath(src, staging))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            dest = _reserve_unique_path(target)
            try:
                # Staging lives inside output_path, so this is a same-volume rename
                # that atomically replaces our own empty placeholder.
                os.replace(src, dest)
            except OSError:
                os.remove(dest)
                raise
            moved[os.path.normcase(os.path.abspath(src))] = dest
    return moved


def download_with_ytdlp(
    url: str,
    output_path: str,
    audio_only: bool = False,
    convert_mp3: bool = False,
    progress_callback: Optional[ProgressCallback] = None,
    progress_file: Optional[str] = None,
    subtitle_langs: Optional[List[str]] = None,
    subtitles_only: bool = False,
    convert_subtitles_to_srt: bool = False,
    rate_limit_kbps: int = 0,
    cookies_from_browser: Optional[str] = None,
    resolution: Optional[str] = None,
    filename_template: Optional[str] = None,
    proxy: Optional[str] = None,
    cookiefile: Optional[str] = None,
) -> str:
    """Compatibility API that returns only the downloaded filepath."""
    return download_with_ytdlp_result(
        url,
        output_path,
        audio_only=audio_only,
        convert_mp3=convert_mp3,
        progress_callback=progress_callback,
        progress_file=progress_file,
        subtitle_langs=subtitle_langs,
        subtitles_only=subtitles_only,
        convert_subtitles_to_srt=convert_subtitles_to_srt,
        rate_limit_kbps=rate_limit_kbps,
        cookies_from_browser=cookies_from_browser,
        resolution=resolution,
        filename_template=filename_template,
        proxy=proxy,
        cookiefile=cookiefile,
    ).filepath
