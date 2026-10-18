"""Unit tests for pytube_helper module."""
import os
import pytest
from unittest import mock

from pytube_helper import (
    is_ffmpeg_available, _safe_filename, _normalize_video_url, download_with_ytdlp,
    build_ytdlp_opts, download_queue_item,
)


@pytest.fixture
def no_default_cookies(monkeypatch):
    """Keep a real cookies.txt in the repo root from leaking into option assertions."""
    import pytube_helper
    monkeypatch.setattr(pytube_helper, '_find_default_cookiefile', lambda: None)


def test_build_ytdlp_opts_leaves_client_selection_to_ytdlp(tmp_path, no_default_cookies):
    """Forced android/ios clients and disabled TLS checks must not come back."""
    opts = build_ytdlp_opts(str(tmp_path))
    assert 'extractor_args' not in opts
    assert 'http_headers' not in opts
    assert 'nocheckcertificate' not in opts
    assert 'cookiefile' not in opts
    assert opts['outtmpl'] == os.path.join(str(tmp_path), '%(title)s.%(ext)s')


def test_build_ytdlp_opts_maps_all_options(tmp_path, no_default_cookies):
    hook = lambda d: None
    opts = build_ytdlp_opts(
        str(tmp_path), resolution='720p', subtitle_langs=['en', 'ko'],
        rate_limit_kbps=500, cookies_from_browser='chrome',
        proxy='socks5://127.0.0.1:1080', filename_template='%(id)s',
        progress_hooks=[hook],
    )
    assert opts['format'].startswith('bestvideo[height<=720]')
    assert opts['merge_output_format'] == 'mp4'
    assert opts['subtitleslangs'] == ['en', 'ko']
    assert opts['writesubtitles'] is True
    assert opts['ratelimit'] == 500 * 1024
    assert opts['cookiesfrombrowser'] == ('chrome',)
    assert opts['proxy'] == 'socks5://127.0.0.1:1080'
    assert opts['outtmpl'].endswith('%(id)s.%(ext)s')
    assert opts['progress_hooks'] == [hook]


def test_build_ytdlp_opts_cookiefile_resolution(tmp_path, monkeypatch):
    import pytube_helper
    default = tmp_path / 'cookies.txt'
    default.write_text('# Netscape HTTP Cookie File\n')
    explicit = tmp_path / 'mine.txt'
    explicit.write_text('# Netscape HTTP Cookie File\n')
    monkeypatch.setattr(pytube_helper, '_find_default_cookiefile', lambda: str(default))

    assert build_ytdlp_opts(str(tmp_path))['cookiefile'] == str(default)
    assert build_ytdlp_opts(str(tmp_path), cookiefile=str(explicit))['cookiefile'] == str(explicit)
    # An explicit path that doesn't exist disables cookies instead of falling back
    assert 'cookiefile' not in build_ytdlp_opts(str(tmp_path), cookiefile=str(tmp_path / 'missing.txt'))


def test_build_ytdlp_opts_js_runtime_uses_local_ejs_when_installed(tmp_path, monkeypatch, no_default_cookies):
    import pytube_helper
    monkeypatch.setattr(pytube_helper.shutil, 'which', lambda x: '/usr/bin/node' if x == 'node' else None)

    monkeypatch.setattr(pytube_helper, 'YTDLP_EJS_AVAILABLE', True)
    opts = build_ytdlp_opts(str(tmp_path))
    assert opts['js_runtimes'] == {'node': {}}
    assert 'remote_components' not in opts

    monkeypatch.setattr(pytube_helper, 'YTDLP_EJS_AVAILABLE', False)
    assert build_ytdlp_opts(str(tmp_path))['remote_components'] == ['ejs:github']


def test_build_ytdlp_opts_mp3_without_ffmpeg_raises(tmp_path, monkeypatch, no_default_cookies):
    import pytube_helper
    monkeypatch.setattr(pytube_helper.shutil, 'which', lambda x: None)
    monkeypatch.setattr(pytube_helper, '_get_ffmpeg_location_from_env', lambda: None)
    with pytest.raises(RuntimeError, match='ffmpeg'):
        build_ytdlp_opts(str(tmp_path), audio_only=True, convert_mp3=True)


def test_download_queue_item_uses_shared_opts_and_records_audio_mode(tmp_path, monkeypatch, no_default_cookies):
    """Queue downloads get the shared options, report progress and are found by duplicate checks."""
    import pytube_helper
    from download_db import is_downloaded
    from download_queue import QueueItem

    captured = {}
    (tmp_path / 'sample.mp3').write_bytes(b'mp3')

    class DummyYDL:
        def __init__(self, opts):
            captured['opts'] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=True):
            for hook in captured['opts'].get('progress_hooks', []):
                hook({'status': 'downloading', 'downloaded_bytes': 50, 'total_bytes': 100})
            return {'title': 'Sample', 'requested_downloads': [{'filepath': str(tmp_path / 'sample.webm')}]}

    monkeypatch.setattr(pytube_helper, 'YTDLP_AVAILABLE', True)
    monkeypatch.setattr(pytube_helper.yt_dlp, 'YoutubeDL', DummyYDL)
    monkeypatch.setattr(pytube_helper.shutil, 'which', lambda x: '/usr/bin/' + x)

    item = QueueItem(url='https://www.youtube.com/watch?v=abc', output_folder=str(tmp_path),
                     audio_only=True, convert_mp3=True, subtitles=True, subtitle_lang='en, ko',
                     proxy='http://proxy:8080')
    progress = []
    out = download_queue_item(item, progress.append)

    opts = captured['opts']
    assert out == str(tmp_path / 'sample.mp3')
    assert progress == [50]
    assert opts['js_runtimes'] == {'node': {}}
    assert opts['subtitleslangs'] == ['en', 'ko']
    assert opts['proxy'] == 'http://proxy:8080'
    assert any(pp.get('key') == 'FFmpegExtractAudio' for pp in opts['postprocessors'])
    rec = is_downloaded(item.url, str(tmp_path), mode='audio')
    assert rec and rec['title'] == 'Sample'


def test_download_with_ytdlp_sets_mp3_postprocessor_when_requested(tmp_path, monkeypatch):
    """Ensure convert_mp3=True results in FFmpegExtractAudio postprocessor being configured."""
    import pytube_helper

    captured = {}

    class DummyYDL:
        def __init__(self, opts):
            captured['opts'] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=True):
            # simulate yt-dlp returning a pre-postprocess file
            out = str(tmp_path / 'sample.webm')
            return {'requested_downloads': [{'filepath': out}]}

        def prepare_filename(self, info):
            return str(tmp_path / 'sample.webm')

    # Force "yt-dlp is available" path and replace YoutubeDL with dummy
    monkeypatch.setattr(pytube_helper, 'YTDLP_AVAILABLE', True)
    monkeypatch.setattr(pytube_helper.yt_dlp, 'YoutubeDL', DummyYDL)
    # Mock ffmpeg so the MP3 pre-check passes in environments without ffmpeg
    monkeypatch.setattr(pytube_helper.shutil, 'which', lambda x: '/usr/bin/ffmpeg')

    out = download_with_ytdlp('https://example.invalid/video', str(tmp_path), audio_only=True, convert_mp3=True)

    opts = captured.get('opts', {})
    assert opts.get('format') == 'bestaudio/best'
    pps = opts.get('postprocessors') or []
    assert any(pp.get('key') == 'FFmpegExtractAudio' for pp in pps)
    assert out.endswith('.mp3')


def test_safe_filename_removes_bad_chars():
    """Test that unsafe characters are removed from filenames."""
    result = _safe_filename("Test: a/b\\c*")
    assert '/' not in result and '\\' not in result
    assert ':' not in result and '*' not in result


def test_safe_filename_keeps_safe_chars():
    """Test that safe characters are preserved."""
    result = _safe_filename("Test (2023) - Part 1_Final.mp4")
    assert '(' in result and ')' in result
    assert '-' in result and '_' in result
    assert '.' in result


def test_safe_filename_strips_whitespace():
    """Test that leading/trailing whitespace is removed."""
    result = _safe_filename("  Test Video  ")
    assert result == "Test Video"


def test_ffmpeg_check_returns_bool_by_mocking_shutil_which():
    """Ensure the function returns a bool and does not depend on the real PATH in CI."""
    with mock.patch('pytube_helper.shutil.which', return_value=None):
        assert is_ffmpeg_available() is False
    with mock.patch('pytube_helper.shutil.which', return_value='C:\\ffmpeg\\bin\\ffmpeg.exe'):
        assert is_ffmpeg_available() is True


def test_normalize_video_url_standard():
    """Test normalization of standard YouTube URLs."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = _normalize_video_url(url)
    assert result == url


def test_normalize_video_url_with_extra_params():
    """Test removal of extra query parameters."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=xyz&feature=share"
    result = _normalize_video_url(url)
    assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert "si=" not in result


def test_normalize_video_url_youtu_be():
    """Test normalization of youtu.be short URLs."""
    url = "https://youtu.be/dQw4w9WgXcQ"
    result = _normalize_video_url(url)
    assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_normalize_video_url_shorts():
    """Test normalization of YouTube Shorts URLs."""
    url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
    result = _normalize_video_url(url)
    assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_normalize_video_url_invalid():
    """Test that invalid URLs are returned unchanged."""
    url = "not a valid url"
    result = _normalize_video_url(url)
    assert result == url
