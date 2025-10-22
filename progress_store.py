"""Progress tracking utilities for download operations."""
import os
import json
from pathlib import Path
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


def ensure_progress_dir(output_folder: str) -> str:
    """Create and return the progress directory path.
    
    Args:
        output_folder: Base output directory
        
    Returns:
        Path to the progress directory
    """
    p = Path(output_folder) / '.progress'
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def progress_file_for_id(output_folder: str, uid: str) -> str:
    """Get the progress file path for a given download ID.
    
    Args:
        output_folder: Base output directory
        uid: Unique identifier for the download
        
    Returns:
        Full path to the progress file
    """
    d = ensure_progress_dir(output_folder)
    return os.path.join(d, f'{uid}.json')


def write_progress_file(path: str, data: Dict[str, Any]) -> None:
    """Write progress data to a file atomically.
    
    Args:
        path: Path to the progress file
        data: Progress data dictionary to write
    """
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception as e:
        logger.error(f'Failed to write progress file {path}: {e}')
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def read_progress_file(path: str) -> Dict[str, Any]:
    """Read progress data from a file.
    
    Args:
        path: Path to the progress file
        
    Returns:
        Progress data dictionary, or empty dict if read fails
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f'Failed to read progress file {path}: {e}')
        return {}


def list_progress_files(output_folder: str) -> List[str]:
    """List all progress files in the output folder.
    
    Args:
        output_folder: Base output directory
        
    Returns:
        List of progress file paths
    """
    d = Path(output_folder) / '.progress'
    if not d.exists():
        return []
    return [str(p) for p in d.glob('*.json')]
