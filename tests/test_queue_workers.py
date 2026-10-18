"""Worker pool, cancellation and forced retry behaviour of DownloadQueue."""
import json
import threading
import time

from download_errors import DownloadCancelled
from download_queue import DownloadQueue, QueueItemStatus


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_worker_pool_runs_downloads_concurrently(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'), max_concurrent=3)
    running, peak, release = set(), [0], threading.Event()
    lock = threading.Lock()

    def fake_download(item, progress_cb):
        with lock:
            running.add(item.id)
            peak[0] = max(peak[0], len(running))
        release.wait(5)
        with lock:
            running.discard(item.id)
        return str(tmp_path / f'{item.id}.mp4')

    q.set_download_function(fake_download)
    for i in range(3):
        q.add(f'https://youtu.be/{i}', str(tmp_path))
    q.start_worker()
    try:
        assert _wait_for(lambda: peak[0] == 3), f'expected 3 parallel downloads, saw {peak[0]}'
        release.set()
        assert _wait_for(lambda: all(i.status == QueueItemStatus.COMPLETED for i in q.get_all()))
    finally:
        release.set()
        q.stop_worker()


def test_set_max_concurrent_is_clamped(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    q.set_max_concurrent(0)
    assert q.max_concurrent == 1
    q.set_max_concurrent(99)
    assert q.max_concurrent == 8


def test_request_cancel_stops_active_download(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'), max_concurrent=1)
    started = threading.Event()

    def fake_download(item, progress_cb):
        started.set()
        for pct in range(100):
            progress_cb(pct, downloaded=pct, total=100, speed=10.0, eta=1)
            time.sleep(0.02)
        return 'never'

    q.set_download_function(fake_download)
    item = q.add('https://youtu.be/cancel-me', str(tmp_path))
    q.start_worker()
    try:
        assert started.wait(5)
        assert q.request_cancel(item.id) is True
        assert _wait_for(lambda: q.get(item.id).status == QueueItemStatus.CANCELLED)
        assert q.get(item.id).speed == 0.0
    finally:
        q.stop_worker()


def test_request_cancel_on_pending_item_cancels_immediately(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    item = q.add('https://youtu.be/pending', str(tmp_path))
    assert q.request_cancel(item.id) is True
    assert q.get(item.id).status == QueueItemStatus.CANCELLED


def test_progress_cb_records_transfer_stats_and_honours_cancel(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    item = q.add('https://youtu.be/stats', str(tmp_path))
    picked = q._pick_next()
    cb = q._make_progress_cb(picked)
    cb(40, downloaded=400, total=1000, speed=2048.0, eta=3)
    assert (item.progress, item.downloaded_bytes, item.total_bytes, item.speed, item.eta) == \
        (40, 400, 1000, 2048.0, 3)
    q._cancel_requested.add(item.id)
    try:
        cb(41)
    except DownloadCancelled:
        pass
    else:
        raise AssertionError('progress callback should raise once cancel is requested')


def test_forced_retry_requeues_non_retryable_and_cancelled_items(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    failed = q.add('https://youtu.be/auth', str(tmp_path))
    q._mark_failed(q._pick_next(), 'Sign in to confirm you are not a bot')
    assert q.retry(failed.id) is False
    assert q.retry(failed.id, force=True) is True
    assert q.get(failed.id).status == QueueItemStatus.PENDING

    cancelled = q.add('https://youtu.be/cancelled', str(tmp_path))
    q.cancel(cancelled.id)
    assert q.retry(cancelled.id, force=True) is True
    assert q.get(cancelled.id).status == QueueItemStatus.PENDING


def test_add_batch_uses_titles_when_given(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    items = q.add_batch(['https://youtu.be/a', 'https://youtu.be/b'], str(tmp_path),
                        titles=['First', ''])
    assert [i.title for i in items] == ['First', 'https://youtu.be/b']


def test_load_ignores_unknown_fields_instead_of_dropping_queue(tmp_path):
    path = tmp_path / 'q.json'
    path.write_text(json.dumps([
        {'id': 'keep0001', 'url': 'https://youtu.be/keep', 'status': 'pending', 'future_field': 1},
        'not-a-record',
    ]), encoding='utf-8')
    q = DownloadQueue(persist_path=str(path))
    assert [i.id for i in q.get_all()] == ['keep0001']


def test_progress_cb_with_unknown_total_keeps_percentage(tmp_path):
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    item = q.add('https://youtu.be/live', str(tmp_path))
    cb = q._make_progress_cb(q._pick_next())
    cb(30, downloaded=300, total=1000)
    cb(None, downloaded=5000, total=0, speed=100.0)
    assert (item.progress, item.downloaded_bytes, item.total_bytes, item.speed) == (30, 5000, 0, 100.0)
