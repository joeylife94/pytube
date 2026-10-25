"""API hardening: token auth, caller checks, path confinement and the /api/info contract."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api_server
from download_queue import DownloadQueue


@pytest.fixture
def client():
    return TestClient(api_server.app, base_url='http://127.0.0.1:8000')


@pytest.fixture
def idle_queue(tmp_path, monkeypatch):
    """A queue without workers, so accepted requests are recorded but never downloaded."""
    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    monkeypatch.setattr(api_server, '_queue', q)
    return q


def test_api_is_open_without_token(client, monkeypatch):
    monkeypatch.delenv('API_TOKEN', raising=False)
    assert client.get('/api/status').status_code == 200


def test_api_token_is_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv('API_TOKEN', 's3cret')
    assert client.get('/api/status').status_code == 401
    assert client.get('/api/status', headers={'X-API-Key': 'wrong'}).status_code == 401
    assert client.get('/api/status', headers={'X-API-Key': 's3cret'}).status_code == 200
    assert client.get('/api/status', headers={'Authorization': 'Bearer s3cret'}).status_code == 200


def test_requests_from_other_websites_are_refused(client, idle_queue, monkeypatch):
    """A page on another site must not drive the local API through the user's browser."""
    monkeypatch.delenv('API_TOKEN', raising=False)
    monkeypatch.delenv('CORS_ORIGINS', raising=False)
    evil = {'Origin': 'https://evil.example'}

    preflight = client.options('/api/download', headers={**evil, 'Access-Control-Request-Method': 'POST'})
    assert 'access-control-allow-origin' not in preflight.headers
    # Simple requests skip the preflight, so the server itself must refuse them
    assert client.post('/api/download', headers=evil, content=b'{"url": "https://youtu.be/x"}').status_code == 403
    assert client.get('/api/queue', headers=evil).status_code == 403
    assert idle_queue.get_all() == []

    # Non-browser clients (no Origin) and the API's own /docs page still work
    assert client.get('/api/status').status_code == 200
    assert client.get('/api/status', headers={'Origin': 'http://127.0.0.1:8000'}).status_code == 200


def test_cors_origins_lets_listed_pages_call_the_api(client, monkeypatch):
    monkeypatch.delenv('API_TOKEN', raising=False)
    monkeypatch.setenv('CORS_ORIGINS', 'http://localhost:3000, https://my.dashboard/')
    assert client.get('/api/status', headers={'Origin': 'http://localhost:3000'}).status_code == 200
    assert client.get('/api/status', headers={'Origin': 'https://my.dashboard'}).status_code == 200
    assert client.get('/api/status', headers={'Origin': 'https://evil.example'}).status_code == 403


def test_without_token_only_localhost_is_served(monkeypatch):
    monkeypatch.delenv('API_TOKEN', raising=False)
    for base in ('http://localhost:8000', 'http://127.0.0.1', 'http://[::1]:8000'):
        assert TestClient(api_server.app, base_url=base).get('/api/status').status_code == 200

    # Another device on the network, and DNS rebinding (a site re-pointing its own
    # domain at 127.0.0.1, so its requests look same-origin)
    lan = TestClient(api_server.app, base_url='http://192.168.0.10:8000')
    assert lan.get('/api/status').status_code == 403
    rebound = TestClient(api_server.app, base_url='http://evil.example:8000')
    assert rebound.get('/api/status', headers={'Origin': 'http://evil.example:8000'}).status_code == 403

    monkeypatch.setenv('API_TOKEN', 's3cret')
    assert lan.get('/api/status', headers={'X-API-Key': 's3cret'}).status_code == 200


@pytest.mark.parametrize('template', [
    '../../outside/%(title)s', 'a/../../%(title)s', '/tmp/%(title)s', '\\\\server\\share\\%(title)s',
    'C:\\Users\\%(title)s',
])
def test_filename_template_must_stay_in_download_folder(client, idle_queue, monkeypatch, tmp_path, template):
    monkeypatch.delenv('API_TOKEN', raising=False)
    response = client.post('/api/download', json={
        'url': 'https://youtu.be/x', 'output_folder': str(tmp_path), 'skip_duplicates': False,
        'filename_template': template,
    })
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'invalid_filename_template'
    assert idle_queue.get_all() == []


def test_filename_template_may_use_subfolders(client, idle_queue, monkeypatch, tmp_path):
    monkeypatch.delenv('API_TOKEN', raising=False)
    response = client.post('/api/download', json={
        'url': 'https://youtu.be/x', 'output_folder': str(tmp_path), 'skip_duplicates': False,
        'filename_template': '%(uploader)s/%(title)s',
    })
    assert response.status_code == 200
    assert [i.filename_template for i in idle_queue.get_all()] == ['%(uploader)s/%(title)s']


def test_cookiefile_outside_allowed_roots_is_rejected(tmp_path):
    outside = tmp_path / 'cookies.txt'
    outside.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')
    with pytest.raises(HTTPException) as exc_info:
        api_server._validate_cookiefile(str(outside))
    assert exc_info.value.detail['code'] == 'invalid_cookiefile'


def test_cookiefile_inside_downloads_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(api_server, 'DEFAULT_OUTPUT', str(tmp_path))
    inside = tmp_path / 'cookies.txt'
    inside.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')
    assert api_server._validate_cookiefile(str(inside)).lower() == str(inside).lower()
    assert api_server._validate_cookiefile('') == ''


def test_missing_cookiefile_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(api_server, 'DEFAULT_OUTPUT', str(tmp_path))
    with pytest.raises(HTTPException):
        api_server._validate_cookiefile(str(tmp_path / 'missing.txt'))


def test_info_endpoint_returns_ytdlp_metadata(client, monkeypatch):
    monkeypatch.delenv('API_TOKEN', raising=False)
    monkeypatch.setattr(api_server, 'get_video_info',
                        lambda url, raise_errors=False: {'title': 'Clip', 'heights': [720, 360]})
    body = client.get('/api/info', params={'url': 'https://youtu.be/x'}).json()
    assert body['title'] == 'Clip'
    assert body['backend'] == 'yt-dlp'
    assert body['heights'] == [720, 360]


def test_cancel_endpoint_stops_an_active_download(tmp_path, monkeypatch):
    from download_queue import DownloadQueue, QueueItemStatus

    q = DownloadQueue(persist_path=str(tmp_path / 'q.json'))
    item = q.add('https://youtu.be/active', str(tmp_path))
    q._pick_next()  # now DOWNLOADING
    monkeypatch.setattr(api_server, '_queue', q)

    response = api_server.cancel_queue_item(item.id)
    assert response.status == QueueItemStatus.DOWNLOADING  # stops at the next progress update
    assert item.id in q._cancel_requested
