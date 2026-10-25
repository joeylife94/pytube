"""Headless Streamlit tests for app.py (no network: metadata and downloads are faked)."""
import os
import time

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from download_queue import DownloadQueue

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py')
VIDEO = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'


@pytest.fixture
def app(tmp_path, monkeypatch):
    import pytube_helper
    import queue_download_adapter

    monkeypatch.setenv('PYTUBE_DOWNLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(pytube_helper, 'get_video_info', lambda url, **kw: {
        'id': 'dQw4w9WgXcQ', 'title': 'Test Clip', 'thumbnail': '', 'duration_str': '3:33',
        'channel': 'Tester', 'upload_date': '20091025', 'view_count': 1234567, 'heights': [1080, 720],
    })
    monkeypatch.setattr(pytube_helper, 'extract_playlist_urls_with_titles', lambda url: {
        'playlist_title': 'My List',
        'items': [{'url': f'https://www.youtube.com/watch?v={c * 11}', 'title': f'Item {c}'} for c in 'abc'],
    })

    def slow_download(item, progress_cb):
        time.sleep(30)  # keep items pending/active; the test only inspects what was queued
        return ''

    monkeypatch.setattr(queue_download_adapter, 'download_queue_item', slow_download)
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def _queued(tmp_path):
    return DownloadQueue(persist_path=str(tmp_path / '.queue.json')).get_all()


def test_app_shell_renders(app):
    assert app.title[0].value == '🎬 YouTube 다운로더'
    assert len(app.tabs) == 6
    assert app.text_input(key='url_single') is not None


def test_unsafe_filename_template_is_flagged(app):
    def flagged():
        return any('템플릿에는' in e.value for e in app.error)

    assert not flagged()
    app.text_input(key='cfg_filename_template').input('../%(title)s').run()
    assert not app.exception
    assert flagged()
    app.text_input(key='cfg_filename_template').input('%(uploader)s/%(title)s').run()
    assert not flagged()


def test_single_video_preview_and_enqueue(app, tmp_path):
    app.text_input(key='url_single').input(VIDEO + '&list=PLxyz').run()
    assert not app.exception
    assert any('Test Clip' in m.value for m in app.markdown)

    app.button(key='dl_single').click().run()
    assert not app.exception
    items = _queued(tmp_path)
    assert [(i.url, i.title, i.audio_only) for i in items] == [(VIDEO, 'Test Clip', False)]
    # URL box is cleared for the next paste
    assert app.text_input(key='url_single').value == ''


def test_mp3_choice_is_applied_to_queue(app, tmp_path):
    app.session_state['cfg_fmt'] = 'mp3'
    app.run()
    app.text_input(key='url_single').input(VIDEO).run()
    app.button(key='dl_single').click().run()
    item = _queued(tmp_path)[0]
    assert (item.audio_only, item.convert_mp3, item.resolution) == (True, True, '')


def test_playlist_selection_enqueues_with_order_in_template(app, tmp_path):
    app.session_state['cfg_filename_template'] = '%(playlist_index)02d_%(title)s'
    app.run()
    app.text_input(key='url_pl').input('https://www.youtube.com/playlist?list=PL1').run()
    assert not app.exception
    app.button(key='playlist_download').click().run()
    items = _queued(tmp_path)
    assert [i.title for i in items] == ['Item a', 'Item b', 'Item c']
    assert [i.filename_template for i in items] == ['01_%(title)s', '02_%(title)s', '03_%(title)s']
    assert all(i.output_folder.endswith('My List') for i in items)


def test_batch_tab_dedupes_and_skips_non_video_links(app, tmp_path):
    app.text_area(key='batch_text').input(
        f'{VIDEO}\nhttps://youtu.be/dQw4w9WgXcQ\nhttps://www.youtube.com/playlist?list=PL1').run()
    app.button(key='batch_download').click().run()
    assert [i.url for i in _queued(tmp_path)] == [VIDEO]


def test_settings_persist_between_sessions(app, tmp_path):
    app.session_state['cfg_quality'] = '720'
    app.run()
    second = AppTest.from_file(APP, default_timeout=30)
    second.run()
    assert second.session_state['cfg_quality'] == '720'


def test_concurrency_is_shared_and_not_reset_by_passive_tabs(app):
    """The queue is process-wide: one tab's slider change must stick across other tabs' reruns."""
    other = AppTest.from_file(APP, default_timeout=30)
    other.run()

    app.slider(key='cfg_concurrency').set_value(5).run()
    other.run()  # passive rerun of a tab that still had the old value
    assert other.slider(key='cfg_concurrency').value == 5

    other.slider(key='cfg_concurrency').set_value(3).run()
    app.run()
    assert app.slider(key='cfg_concurrency').value == 3
