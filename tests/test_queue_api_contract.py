"""Contract tests for structured queue failures and API retry semantics."""
import json

import pytest
from fastapi import HTTPException

from download_errors import DownloadErrorCode, classify_download_error
from download_queue import DownloadQueue, QueueItemStatus


def _queue(tmp_path):
    return DownloadQueue(persist_path=str(tmp_path / 'queue.json'))


def test_error_classifier_marks_only_transient_failures_retryable():
    network = classify_download_error('HTTP Error 503: Service Unavailable')
    assert network.code == DownloadErrorCode.NETWORK
    assert network.retryable is True

    rate = classify_download_error('HTTP Error 429: Too Many Requests')
    assert rate.code == DownloadErrorCode.RATE_LIMITED
    assert rate.retryable is True

    ffmpeg = classify_download_error('MP3 conversion requires ffmpeg')
    assert ffmpeg.code == DownloadErrorCode.FFMPEG_MISSING
    assert ffmpeg.retryable is False

    auth = classify_download_error('Sign in to confirm you are not a bot')
    assert auth.code == DownloadErrorCode.AUTH_REQUIRED
    assert auth.retryable is False


def test_old_persisted_queue_records_load_with_new_contract_defaults(tmp_path):
    path = tmp_path / 'queue.json'
    path.write_text(json.dumps([{
        'id': 'legacy01', 'url': 'https://youtu.be/legacy', 'title': 'legacy',
        'output_folder': str(tmp_path), 'status': 'failed', 'error': 'old failure',
    }]), encoding='utf-8')

    q = DownloadQueue(persist_path=str(path))
    item = q.get('legacy01')
    assert item is not None
    assert item.error_code == ''
    assert item.retryable is False
    assert item.attempts == 0


def test_retry_preserves_identity_and_increments_attempts_on_next_pick(tmp_path):
    q = _queue(tmp_path)
    item = q.add('https://youtu.be/retry', str(tmp_path))

    picked = q._pick_next()
    assert picked.id == item.id
    assert picked.attempts == 1

    q._mark_failed(picked, 'connection reset by peer')
    failed = q.get(item.id)
    assert failed.status == QueueItemStatus.FAILED
    assert failed.error_code == DownloadErrorCode.NETWORK.value
    assert failed.retryable is True

    assert q.retry(item.id) is True
    pending = q.get(item.id)
    assert pending.id == item.id
    assert pending.status == QueueItemStatus.PENDING
    assert pending.attempts == 1
    assert pending.error == ''
    assert pending.error_code == ''

    picked_again = q._pick_next()
    assert picked_again.id == item.id
    assert picked_again.attempts == 2


def test_non_retryable_failure_cannot_be_requeued(tmp_path):
    q = _queue(tmp_path)
    item = q.add('https://youtu.be/no-retry', str(tmp_path))
    picked = q._pick_next()
    q._mark_failed(picked, 'MP3 conversion requires ffmpeg')

    failed = q.get(item.id)
    assert failed.error_code == DownloadErrorCode.FFMPEG_MISSING.value
    assert failed.retryable is False
    assert q.retry(item.id) is False
    assert q.get(item.id).status == QueueItemStatus.FAILED


def test_api_queue_response_exposes_failure_metadata(tmp_path):
    import api_server

    q = _queue(tmp_path)
    item = q.add('https://youtu.be/api-contract', str(tmp_path))
    picked = q._pick_next()
    q._mark_failed(picked, 'HTTP Error 503: Service Unavailable')

    response = api_server._queue_response(q.get(item.id))
    assert response.status == QueueItemStatus.FAILED
    assert response.error_code == DownloadErrorCode.NETWORK.value
    assert response.retryable is True
    assert response.attempts == 1


def test_api_retry_endpoint_requeues_retryable_failure(tmp_path, monkeypatch):
    import api_server

    q = _queue(tmp_path)
    item = q.add('https://youtu.be/api-retry', str(tmp_path))
    picked = q._pick_next()
    q._mark_failed(picked, 'timed out while reading response')
    monkeypatch.setattr(api_server, '_queue', q)

    response = api_server.retry_queue_item(item.id)
    assert response.id == item.id
    assert response.status == QueueItemStatus.PENDING
    assert response.error == ''
    assert response.retryable is False
    assert response.attempts == 1


def test_api_retry_endpoint_rejects_non_retryable_failure(tmp_path, monkeypatch):
    import api_server

    q = _queue(tmp_path)
    item = q.add('https://youtu.be/api-no-retry', str(tmp_path))
    picked = q._pick_next()
    q._mark_failed(picked, 'Video unavailable')
    monkeypatch.setattr(api_server, '_queue', q)

    with pytest.raises(HTTPException) as exc_info:
        api_server.retry_queue_item(item.id)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail['code'] == 'failure_not_retryable'
    assert exc_info.value.detail['retryable'] is False
