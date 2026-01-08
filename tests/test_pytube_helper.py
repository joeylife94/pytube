"""Unit tests for pytube_helper module."""
import os
import pytest
from unittest import mock

from pytube_helper import (
    is_ffmpeg_available, _safe_filename, _normalize_video_url, download_with_ytdlp
)


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
