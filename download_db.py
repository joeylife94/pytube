"""Download history database — JSON-backed duplicate detection & history tracking."""
import os
import json
import hashlib
import time
import threading
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _db_path(output_folder: str) -> str:
    """Return the path to the download history database file."""
    d = Path(output_folder)
    d.mkdir(parents=True, exist_ok=True)
    return str(d / '.download_history.json')


def _url_key(url: str) -> str:
    """Normalise a URL into a short hash key."""
    return hashlib.sha256(url.strip().encode()).hexdigest()[:16]


def _load(db_file: str) -> Dict[str, Any]:
    try:
        with open(db_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(db_file: str, data: Dict[str, Any]) -> None:
    tmp = db_file + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, db_file)


# ─── Public API ──────────────────────────────────────────────────────────────

def is_downloaded(url: str, output_folder: str) -> Optional[Dict[str, Any]]:
    """Check if a URL has already been downloaded.

    Returns the record dict if found, otherwise None.
    """
    with _lock:
        db = _load(_db_path(output_folder))
        rec = db.get(_url_key(url))
        if rec is None:
            return None
        # Also verify the file still exists on disk
        fpath = rec.get('filepath', '')
        if fpath and os.path.isfile(fpath):
            return rec
        return None


def record_download(url: str, output_folder: str, filepath: str,
                    title: str = '', size: int = 0,
                    extra: Optional[Dict] = None) -> None:
    """Record a successful download."""
    with _lock:
        db_file = _db_path(output_folder)
        db = _load(db_file)
        db[_url_key(url)] = {
            'url': url,
            'title': title,
            'filepath': filepath,
            'size': size,
            'timestamp': time.time(),
            **(extra or {}),
        }
        _save(db_file, db)


def get_history(output_folder: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Return the most recent downloads, newest first."""
    with _lock:
        db = _load(_db_path(output_folder))
    items = sorted(db.values(), key=lambda x: x.get('timestamp', 0), reverse=True)
    return items[:limit]


def clear_history(output_folder: str) -> int:
    """Clear all download history. Returns how many records were removed."""
    with _lock:
        db_file = _db_path(output_folder)
        db = _load(db_file)
        n = len(db)
        _save(db_file, {})
        return n


def remove_record(url: str, output_folder: str) -> bool:
    """Remove a single record by URL."""
    with _lock:
        db_file = _db_path(output_folder)
        db = _load(db_file)
        key = _url_key(url)
        if key in db:
            del db[key]
            _save(db_file, db)
            return True
        return False
