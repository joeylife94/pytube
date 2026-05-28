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
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    # Import the function directly from the module (not the Streamlit app)
    import importlib, types
    # Minimal import: read the helper out of app.py without executing Streamlit
    import ast, textwrap
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py'),
               encoding='utf-8').read()
    tree = ast.parse(src)
    # Extract just the _safe_getsize function
    fn_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_safe_getsize':
            fn_src = ast.get_source_segment(src, node)
            break
    assert fn_src is not None, '_safe_getsize not found in app.py'
    ns: dict = {}
    exec(compile(fn_src, '<test>', 'exec'), {'os': os}, ns)
    _safe_getsize = ns['_safe_getsize']
    assert _safe_getsize('/nonexistent/path/file.mp4') == 0


def test_safe_getsize_existing_file(tmp_path):
    """_safe_getsize must return correct size for an existing file."""
    import ast
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app.py'),
               encoding='utf-8').read()
    tree = ast.parse(src)
    fn_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_safe_getsize':
            fn_src = ast.get_source_segment(src, node)
            break
    ns: dict = {}
    exec(compile(fn_src, '<test>', 'exec'), {'os': os}, ns)
    _safe_getsize = ns['_safe_getsize']
    f = tmp_path / 'test.mp4'
    f.write_bytes(b'x' * 42)
    assert _safe_getsize(str(f)) == 42
