"""Tests for api_server helpers and app helper utilities."""
import os
import pytest
from fastapi import HTTPException


def test_validate_output_folder_empty_returns_default():
    from api_server import _validate_output_folder, DEFAULT_OUTPUT
    assert _validate_output_folder('') == DEFAULT_OUTPUT


def test_validate_output_folder_dotdot_rejected():
    from api_server import _validate_output_folder
    with pytest.raises(HTTPException) as exc_info:
        _validate_output_folder('../../../etc/passwd')
    assert exc_info.value.status_code == 400


def test_validate_output_folder_dotdot_component_rejected():
    from api_server import _validate_output_folder
    with pytest.raises(HTTPException):
        _validate_output_folder('downloads/../../secret')


def test_validate_output_folder_normalizes_path():
    from api_server import _validate_output_folder
    result = _validate_output_folder('downloads/sub')
    assert '..' not in result
    assert os.path.isabs(result)


def test_safe_getsize_missing_file():
    """_safe_getsize must return 0 for non-existent paths without raising."""
    from app_helpers import _safe_getsize
    assert _safe_getsize('/nonexistent/path/file.mp4') == 0


def test_safe_getsize_existing_file(tmp_path):
    """_safe_getsize must return correct size for an existing file."""
    from app_helpers import _safe_getsize
    f = tmp_path / 'test.mp4'
    f.write_bytes(b'x' * 42)
    assert _safe_getsize(str(f)) == 42
