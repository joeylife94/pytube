"""API hardening: token auth, cookiefile confinement and the /api/info contract."""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api_server


@pytest.fixture
def client():
    return TestClient(api_server.app)


def test_api_is_open_without_token(client, monkeypatch):
    monkeypatch.delenv('API_TOKEN', raising=False)
    assert client.get('/api/status').status_code == 200


def test_api_token_is_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv('API_TOKEN', 's3cret')
    assert client.get('/api/status').status_code == 401
    assert client.get('/api/status', headers={'X-API-Key': 'wrong'}).status_code == 401
    assert client.get('/api/status', headers={'X-API-Key': 's3cret'}).status_code == 200
    assert client.get('/api/status', headers={'Authorization': 'Bearer s3cret'}).status_code == 200


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
