"""Unit tests for the Streamlit-free UI helpers."""
import json

import pytest

import app_helpers as h


def test_mode_flags_and_history_mode():
    assert h.mode_flags('video') == (False, False)
    assert h.mode_flags('mp3') == (True, True)
    assert h.mode_flags('audio') == (True, False)
    assert h.history_mode('mp3') == h.history_mode('audio') == 'audio'
    assert h.history_mode('video') == 'video'


def test_resolution_for_ignores_audio_and_best():
    assert h.resolution_for('video', '1080') == '1080p'
    assert h.resolution_for('video', 'best') == ''
    assert h.resolution_for('mp3', '1080') == ''


@pytest.mark.parametrize('template, index, expected', [
    ('%(title)s', 3, '%(title)s'),
    ('%(playlist_index)02d_%(title)s', 7, '07_%(title)s'),
    ('%(playlist_index)02d_%(title)s', None, '%(title)s'),
    ('', None, '%(title)s'),
])
def test_resolve_template(template, index, expected):
    assert h.resolve_template(template, index) == expected


@pytest.mark.parametrize('url, vid', [
    ('https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123&si=x', 'dQw4w9WgXcQ'),
    ('https://youtu.be/dQw4w9WgXcQ?si=abc', 'dQw4w9WgXcQ'),
    ('https://www.youtube.com/shorts/dQw4w9WgXcQ', 'dQw4w9WgXcQ'),
    ('https://m.youtube.com/live/dQw4w9WgXcQ', 'dQw4w9WgXcQ'),
    ('https://www.youtube.com/playlist?list=PL123', ''),
    ('https://www.youtube.com/@channel', ''),
    ('https://example.com/watch?v=dQw4w9WgXcQ', ''),
])
def test_video_id(url, vid):
    assert h.video_id(url) == vid


def test_url_kind_helpers():
    assert h.is_youtube_url('https://music.youtube.com/watch?v=dQw4w9WgXcQ')
    assert not h.is_youtube_url('https://notyoutube.com/watch?v=x')
    assert not h.is_youtube_url('youtube.com/watch?v=x')
    assert h.is_playlist_only_url('https://www.youtube.com/playlist?list=PL123')
    assert not h.is_playlist_only_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123')
    assert h.is_channel_url('https://www.youtube.com/@name/videos')


def test_parse_urls_normalises_dedupes_and_separates_non_videos():
    text = """
    https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10
    https://youtu.be/dQw4w9WgXcQ, https://youtu.be/9bZkp7q19f0
    not a url  https://example.com/x
    https://www.youtube.com/playlist?list=PL123
    """
    videos, others = h.parse_urls(text)
    assert videos == ['https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                      'https://www.youtube.com/watch?v=9bZkp7q19f0']
    assert others == ['https://www.youtube.com/playlist?list=PL123']


def test_settings_roundtrip_and_validation(tmp_path):
    path = tmp_path / 'settings.json'
    s = h.AppSettings(fmt='mp3', quality='720', concurrency=4, proxy='socks5://x:1')
    h.save_settings(s, str(path))
    assert h.load_settings(str(path)) == s

    path.write_text(json.dumps({'fmt': 'bogus', 'quality': 99, 'concurrency': 42,
                                'cookies_from_browser': 'netscape', 'unknown': 1}), encoding='utf-8')
    loaded = h.load_settings(str(path))
    assert loaded.fmt == 'video'
    assert loaded.quality == 'best'
    assert loaded.concurrency == 8
    assert loaded.cookies_from_browser == ''


def test_load_settings_missing_or_corrupt_file(tmp_path):
    assert h.load_settings(str(tmp_path / 'missing.json')) == h.AppSettings()
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json', encoding='utf-8')
    assert h.load_settings(str(bad)) == h.AppSettings()


def test_formatting_helpers():
    assert h.human_size(1536) == '1.5 KB'
    assert h.human_speed(0) == '0 B/s'
    assert h.human_eta(65) == '1:05'
    assert h.human_eta(3725) == '1:02:05'
    assert h.human_eta(0) == '-'
    assert h.human_count(12_345) == '1.2만'
    assert h.human_count(123_456_789) == '1.2억'
    assert h.human_count(999) == '999'
    assert h.format_upload_date('20240131') == '2024-01-31'
    assert h.format_upload_date('') == ''


def test_md_escape_neutralises_markdown_and_latex():
    assert h.md_escape('*Hot* $5 [live]') == r'\*Hot\* \$5 \[live\]'


def test_friendly_error_uses_codes_and_falls_back_to_message():
    assert '쿠키' in h.friendly_error('ERROR: Sign in to confirm you’re not a bot')
    assert '프록시' in h.friendly_error('', 'geo_restricted')
    assert h.friendly_error('ERROR: something odd happened') == 'something odd happened'
    assert len(h.friendly_error('x' * 500)) == 160
