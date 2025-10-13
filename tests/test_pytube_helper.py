import os
import pytest

from pytube_helper import is_ffmpeg_available, _safe_filename


def test_safe_filename_removes_bad_chars():
    s = 'A / B: C? * D|E<>'
    # result should not contain slash or backslash
    out = _safe_filename("Test: a/b\\c*")
    assert '/' not in out and '\\' not in out


def test_ffmpeg_check_returns_bool():
    val = is_ffmpeg_available()
    assert isinstance(val, bool)
