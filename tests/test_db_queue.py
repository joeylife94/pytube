"""Tests for download_db CRUD and download_queue add/cancel/race-condition."""
import os
import time
import threading
import pytest

# ─── download_db tests ──────────────────────────────────────────────────────

def test_record_and_check_download(tmp_path):
    """record_download should mark a URL as downloaded; is_downloaded should detect it."""
    from download_db import is_downloaded, record_download

    url = 'https://www.youtube.com/watch?v=test_crud_001'
    folder = str(tmp_path)
    # Create a real file so is_downloaded's existence check passes
    fake_file = tmp_path / 'path.mp4'
    fake_file.write_bytes(b'fake')

    assert not is_downloaded(url, folder)
    record_download(url, folder, str(fake_file), title='Test', size=1234)
    assert is_downloaded(url, folder)


def test_get_history_returns_records(tmp_path):
    """get_history should return previously recorded downloads."""
    from download_db import record_download, get_history

    url = 'https://www.youtube.com/watch?v=test_hist_002'
    folder = str(tmp_path)

    record_download(url, folder, str(tmp_path / 'video.mp4'), title='History Test', size=0)
    history = get_history(folder)
    urls = [h.get('url') for h in history]
    assert url in urls


def test_clear_history(tmp_path):
    """clear_history should remove all records."""
    from download_db import record_download, get_history, clear_history

    folder = str(tmp_path)
    for i in range(3):
        record_download(
            f'https://www.youtube.com/watch?v=clear_test_{i}',
            folder, str(tmp_path / f'{i}.mp4'), title=f'Vid {i}', size=0,
        )
    assert len(get_history(folder)) == 3
    n = clear_history(folder)
    assert n == 3
    assert len(get_history(folder)) == 0


# ─── download_queue tests ───────────────────────────────────────────────────

def _make_queue(tmp_path, max_concurrent=2):
    """Create a DownloadQueue backed by a temp directory (no worker thread started)."""
    from download_queue import DownloadQueue
    q = DownloadQueue(
        persist_path=str(tmp_path / 'queue.json'),
        max_concurrent=max_concurrent,
    )
    return q


def test_add_and_get_all(tmp_path):
    """add() should persist the item; get_all() should return it."""
    from download_queue import QueueItemStatus

    q = _make_queue(tmp_path)
    item = q.add(url='https://youtu.be/aaa', output_folder=str(tmp_path))
    assert item.id is not None
    all_items = q.get_all()
    assert any(i.id == item.id for i in all_items)
    assert item.status == QueueItemStatus.PENDING


def test_cancel_item(tmp_path):
    """cancel() should transition a PENDING item to CANCELLED."""
    from download_queue import QueueItemStatus

    q = _make_queue(tmp_path)
    item = q.add(url='https://youtu.be/bbb', output_folder=str(tmp_path))
    result = q.cancel(item.id)
    assert result is True
    updated = q.get(item.id)
    assert updated.status == QueueItemStatus.CANCELLED


def test_clear_removes_completed(tmp_path):
    """clear_completed() should remove cancelled/completed items."""
    from download_queue import QueueItemStatus

    q = _make_queue(tmp_path)
    item = q.add(url='https://youtu.be/ccc', output_folder=str(tmp_path))
    q.cancel(item.id)
    q.clear_completed()
    assert q.get(item.id) is None


def test_pick_next_marks_downloading_atomically(tmp_path):
    """_pick_next() must mark the item DOWNLOADING while still holding the lock.

    Regression test for the race condition where two threads could both call
    _pick_next() and return the same PENDING item before either marked it
    DOWNLOADING in _worker_loop.
    """
    from download_queue import QueueItemStatus

    q = _make_queue(tmp_path, max_concurrent=2)
    # Add one item
    q.add(url='https://youtu.be/race', output_folder=str(tmp_path))

    results = []

    def pick():
        item = q._pick_next()
        results.append(item)

    t1 = threading.Thread(target=pick)
    t2 = threading.Thread(target=pick)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Exactly one thread should have picked the item; the other gets None
    picked = [r for r in results if r is not None]
    assert len(picked) == 1, 'Two threads must not both pick the same item'
    assert picked[0].status == QueueItemStatus.DOWNLOADING


def test_speed_none_does_not_raise_type_error():
    """Regression: yt-dlp returns speed=None during initial buffering; must not crash."""
    from pytube_helper import _create_ytdlp_progress_hook

    hook = _create_ytdlp_progress_hook(None, None)

    # Simulate yt-dlp progress dict with speed=None and eta=None
    hook({
        'status': 'downloading',
        'downloaded_bytes': 1024,
        'total_bytes': 10240,
        'speed': None,
        'eta': None,
        'filename': 'test.mp4',
    })  # Must not raise
