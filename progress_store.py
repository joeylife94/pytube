import os
import json
from pathlib import Path


def ensure_progress_dir(output_folder: str) -> str:
    p = Path(output_folder) / '.progress'
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def progress_file_for_id(output_folder: str, uid: str) -> str:
    d = ensure_progress_dir(output_folder)
    return os.path.join(d, f'{uid}.json')


def write_progress_file(path: str, data: dict):
    # atomic write
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def read_progress_file(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def list_progress_files(output_folder: str):
    d = Path(output_folder) / '.progress'
    if not d.exists():
        return []
    return [str(p) for p in d.glob('*.json')]
