"""Streamlit-free helpers for app.py: settings, formatting, URL parsing, messages."""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from dataclasses import asdict, dataclass, fields
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from download_errors import DownloadErrorCode, classify_download_error

# ─── Download options ───────────────────────────────────────────────────────

FORMAT_LABELS: Dict[str, str] = {
    'video': '🎬 영상',
    'mp3': '🎵 MP3',
    'audio': '🎧 원본 오디오',
}

QUALITY_LABELS: Dict[str, str] = {
    'best': '최고 화질',
    '2160': '2160p (4K)',
    '1440': '1440p (QHD)',
    '1080': '1080p (FHD)',
    '720': '720p (HD)',
    '480': '480p',
    '360': '360p',
}

FILENAME_PRESETS: Dict[str, str] = {
    '제목': '%(title)s',
    '업로드 날짜_제목': '%(upload_date)s_%(title)s',
    '채널_제목': '%(uploader)s_%(title)s',
    '재생목록 순서_제목': '%(playlist_index)02d_%(title)s',
    '제목 [영상 ID]': '%(title)s [%(id)s]',
}

# Browsers yt-dlp can read cookies from
COOKIE_BROWSERS: List[str] = ['', 'firefox', 'chrome', 'edge', 'brave', 'opera', 'vivaldi', 'whale',
                              'chromium', 'safari']


def mode_flags(fmt: str) -> Tuple[bool, bool]:
    """Map a format choice to (audio_only, convert_mp3)."""
    if fmt == 'mp3':
        return True, True
    if fmt == 'audio':
        return True, False
    return False, False


def history_mode(fmt: str) -> str:
    """Duplicate-detection mode used by download_db for a format choice."""
    return 'audio' if fmt in ('mp3', 'audio') else 'video'


_PLAYLIST_INDEX_FIELD = re.compile(r'%\(playlist_index[^)]*\)[-#0 +]*\d*[a-z]')


def resolve_template(template: str, index: Optional[int] = None) -> str:
    """Bake a playlist position into a filename template.

    Queued items are downloaded one URL at a time, so yt-dlp never sees a
    playlist_index; substitute the item's position (or drop the field).
    """
    template = template or '%(title)s'
    if not _PLAYLIST_INDEX_FIELD.search(template):
        return template
    if index:
        return _PLAYLIST_INDEX_FIELD.sub(f'{index:02d}', template)
    return _PLAYLIST_INDEX_FIELD.sub('', template).lstrip('_- ') or '%(title)s'


def resolution_for(fmt: str, quality: str) -> str:
    """Queue `resolution` value: '' means best; ignored for audio formats."""
    if fmt != 'video' or not quality or quality == 'best':
        return ''
    return f'{quality}p'


# ─── Settings persistence ───────────────────────────────────────────────────

@dataclass
class AppSettings:
    output_folder: str = ''
    fmt: str = 'video'
    quality: str = 'best'
    subtitles: bool = False
    subtitle_langs: str = 'ko,en'
    skip_duplicates: bool = True
    concurrency: int = 2
    rate_limit_kbps: int = 0
    filename_template: str = '%(title)s'
    cookies_from_browser: str = ''
    cookiefile: str = ''
    proxy: str = ''
    notify: bool = True


SETTINGS_FIELDS = [f.name for f in fields(AppSettings)]


def default_download_dir() -> str:
    return os.environ.get('PYTUBE_DOWNLOAD_DIR') or os.path.join(os.getcwd(), 'downloads')


def settings_path() -> str:
    return os.path.join(default_download_dir(), '.app_settings.json')


def load_settings(path: Optional[str] = None) -> AppSettings:
    """Load saved settings, falling back to defaults for missing or invalid values."""
    defaults = AppSettings()
    try:
        with open(path or settings_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    values = {}
    for name in SETTINGS_FIELDS:
        default = getattr(defaults, name)
        value = data.get(name, default)
        values[name] = value if isinstance(value, type(default)) else default
    if values['fmt'] not in FORMAT_LABELS:
        values['fmt'] = defaults.fmt
    if values['quality'] not in QUALITY_LABELS:
        values['quality'] = defaults.quality
    if values['cookies_from_browser'] not in COOKIE_BROWSERS:
        values['cookies_from_browser'] = ''
    values['concurrency'] = max(1, min(int(values['concurrency']), 8))
    return AppSettings(**values)


def save_settings(settings: AppSettings, path: Optional[str] = None) -> None:
    path = path or settings_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ─── URLs ───────────────────────────────────────────────────────────────────

_YOUTUBE_HOST = re.compile(r'(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$', re.I)


def is_youtube_url(text: str) -> bool:
    try:
        parsed = urlparse(text.strip())
    except ValueError:
        return False
    return parsed.scheme in ('http', 'https') and bool(_YOUTUBE_HOST.search(parsed.netloc.split(':')[0]))


def playlist_id(url: str) -> str:
    try:
        return parse_qs(urlparse(url).query).get('list', [''])[0]
    except ValueError:
        return ''


def is_playlist_only_url(url: str) -> bool:
    """A /playlist?list=... link (no specific video)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return bool(playlist_id(url)) and 'v' not in parse_qs(parsed.query) and '/playlist' in parsed.path


_VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')


def video_id(url: str) -> str:
    """The 11-character video id of a watch/youtu.be/shorts/live/embed URL, or ''."""
    try:
        parsed = urlparse((url or '').strip())
    except ValueError:
        return ''
    host = parsed.netloc.lower().split(':')[0]
    candidate = ''
    if host.endswith('youtu.be'):
        candidate = parsed.path.lstrip('/').split('/')[0]
    elif _YOUTUBE_HOST.search(host):
        candidate = parse_qs(parsed.query).get('v', [''])[0]
        parts = [p for p in parsed.path.split('/') if p]
        if not candidate and len(parts) >= 2 and parts[0] in ('shorts', 'live', 'embed', 'v'):
            candidate = parts[1]
    return candidate if _VIDEO_ID.match(candidate) else ''


def watch_url(vid: str) -> str:
    """Canonical single-video URL (drops list=/si= params so yt-dlp never grabs a playlist)."""
    return f'https://www.youtube.com/watch?v={vid}'


def is_channel_url(url: str) -> bool:
    try:
        path = urlparse(url).path
    except ValueError:
        return False
    return path.startswith(('/@', '/channel/', '/c/', '/user/'))


def parse_urls(text: str) -> Tuple[List[str], List[str]]:
    """Split free text into (video URLs, other YouTube URLs).

    Tokens may be separated by newlines, spaces or commas. Video URLs are
    normalised to watch?v=<id> and deduplicated by id; anything else that is a
    YouTube link (playlists, channels) is returned separately so the UI can
    point the user at the right tab.
    """
    seen, videos, others = set(), [], []
    for token in re.split(r'[\s,]+', text or ''):
        token = token.strip().strip('<>"\'')
        if not token or not is_youtube_url(token):
            continue
        vid = video_id(token)
        if vid:
            if vid not in seen:
                seen.add(vid)
                videos.append(watch_url(vid))
        elif token not in others:
            others.append(token)
    return videos, others


# ─── Formatting ─────────────────────────────────────────────────────────────

def human_size(b: float) -> str:
    b = float(b or 0)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(b) < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} TB"


def human_speed(bps: float) -> str:
    return human_size(bps) + '/s' if bps else '0 B/s'


def human_eta(seconds: float) -> str:
    seconds = int(seconds or 0)
    if seconds <= 0:
        return '-'
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def human_count(n: Optional[int]) -> str:
    """Korean-style large numbers: 12,345 → 1.2만, 123,456,789 → 1.2억."""
    if n is None:
        return '?'
    if n >= 100_000_000:
        return f'{n / 100_000_000:.1f}억'
    if n >= 10_000:
        return f'{n / 10_000:.1f}만'
    return f'{n:,}'


def format_upload_date(d: str) -> str:
    return f'{d[:4]}-{d[4:6]}-{d[6:8]}' if d and len(d) == 8 and d.isdigit() else ''


_MD_SPECIAL = re.compile(r'([\\`*_{}\[\]()#+\-.!|<>~$])')


def md_escape(text: str) -> str:
    """Escape Markdown (and Streamlit's $ LaTeX) so video titles render literally."""
    return _MD_SPECIAL.sub(r'\\\1', text or '')


def safe_title(text: str) -> str:
    return "".join(c for c in (text or '') if c.isalnum() or c in ' ._-()[]').strip() or 'Download'


def _safe_getsize(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ─── Error messages ─────────────────────────────────────────────────────────

_ERROR_HINTS = {
    DownloadErrorCode.AUTH_REQUIRED: '로그인이 필요한 영상이에요. 사이드바 「로그인 · 네트워크」에서 쿠키를 설정한 뒤 다시 시도하세요.',
    DownloadErrorCode.GEO_RESTRICTED: '이 지역에서는 볼 수 없는 영상이에요. 프록시를 설정해 보세요.',
    DownloadErrorCode.NOT_FOUND: '영상을 찾을 수 없어요. 삭제됐거나 비공개일 수 있어요.',
    DownloadErrorCode.RATE_LIMITED: '요청이 너무 많아요. 잠시 후 다시 시도하세요.',
    DownloadErrorCode.NETWORK: '네트워크 오류예요. 연결을 확인하고 다시 시도하세요.',
    DownloadErrorCode.FFMPEG_MISSING: 'ffmpeg가 필요해요. ffmpeg를 설치하거나 FFMPEG_LOCATION을 설정하세요.',
    DownloadErrorCode.INVALID_REQUEST: '지원하지 않는 URL이에요.',
}


def friendly_error(message: str, code: str = '') -> str:
    """One-line Korean explanation for a failure, falling back to the raw message."""
    try:
        error_code = DownloadErrorCode(code) if code else classify_download_error(message).code
    except ValueError:
        error_code = classify_download_error(message).code
    hint = _ERROR_HINTS.get(error_code)
    if hint:
        return hint
    text = (message or '알 수 없는 오류').replace('ERROR: ', '').strip()
    return text if len(text) <= 160 else text[:157] + '...'


# ─── OS integration ─────────────────────────────────────────────────────────

def running_in_container() -> bool:
    return os.path.exists('/.dockerenv')


def open_folder(path: str) -> None:
    """Open a directory in the system file manager (cross-platform)."""
    abs_path = os.path.abspath(path)
    system = platform.system()
    if system == 'Windows':
        os.startfile(abs_path)  # type: ignore[attr-defined]
    elif system == 'Darwin':
        subprocess.Popen(['open', abs_path])
    else:
        subprocess.Popen(['xdg-open', abs_path])


def reveal_file(path: str) -> None:
    """Show a file selected in the system file manager (cross-platform)."""
    abs_path = os.path.abspath(path)
    system = platform.system()
    if system == 'Windows':
        subprocess.Popen(['explorer', f'/select,{abs_path}'])
    elif system == 'Darwin':
        subprocess.Popen(['open', '-R', abs_path])
    else:
        subprocess.Popen(['xdg-open', os.path.dirname(abs_path)])
