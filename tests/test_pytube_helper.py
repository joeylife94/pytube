import os
import pytest
from unittest import mock

from pytube_helper import is_ffmpeg_available, _safe_filename


def test_safe_filename_removes_bad_chars():
    s = 'A / B: C? * D|E<>'
    # result should not contain slash or backslash
    out = _safe_filename("Test: a/b\\c*")
    assert '/' not in out and '\\' not in out


def test_ffmpeg_check_returns_bool_by_mocking_shutil_which():
    # ensure the function returns a bool and does not depend on the real PATH in CI
    with mock.patch('pytube_helper.shutil.which', return_value=None):
        assert is_ffmpeg_available() is False
    with mock.patch('pytube_helper.shutil.which', return_value='C:\\ffmpeg\\bin\\ffmpeg.exe'):
        assert is_ffmpeg_available() is True
