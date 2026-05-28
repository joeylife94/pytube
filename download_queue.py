"""Thread-safe download queue with background processing."""
import os
import uuid
import time
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class QueueItemStatus(str, Enum):
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    SCHEDULED = 'scheduled'


@dataclass
class QueueItem:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    url: str = ''
    title: str = ''
    output_folder: str = ''
    audio_only: bool = False
    convert_mp3: bool = False
    subtitles: bool = False
    subtitle_lang: str = 'en'
    rate_limit: int = 0  # KB/s, 0 = unlimited
    status: str = QueueItemStatus.PENDING
    progress: int = 0  # 0-100
    error: str = ''
    filepath: str = ''
    added_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    # For scheduling
    scheduled_time: float = 0.0  # unix timestamp, 0 = immediate
    # Per-item download options (captured from sidebar at queue time)
    proxy: str = ''
    cookiefile: str = ''
    cookies_from_browser: str = ''
    resolution: str = ''
    filename_template: str = '%(title)s'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DownloadQueue:
    """Persistent, thread-safe download queue with background worker."""

    def __init__(self, persist_path: Optional[str] = None, max_concurrent: int = 2):
        self._items: Dict[str, QueueItem] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._persist_path = persist_path or ''
        self._max_concurrent = max_concurrent
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._download_fn: Optional[Callable] = None
        self._load()

    # ─── Persistence ────────────────────────────────────────────────────

    def _db_file(self) -> str:
        if self._persist_path:
            return self._persist_path
        return os.path.join(os.getcwd(), 'downloads', '.queue.json')

    def _load(self):
        try:
            with open(self._db_file(), 'r', encoding='utf-8') as f:
                data = json.load(f)
            for rec in data:
                item = QueueItem(**rec)
                # Reset stuck downloads back to pending
                if item.status == QueueItemStatus.DOWNLOADING:
                    item.status = QueueItemStatus.PENDING
                    item.progress = 0
                self._items[item.id] = item
                self._order.append(item.id)
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            pass

    def _save(self):
        path = self._db_file()
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        tmp = path + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump([self._items[k].to_dict() for k in self._order if k in self._items],
                          f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            logger.error('Failed to save queue: %s', e)

    # ─── Queue operations ───────────────────────────────────────────────

    def add(self, url: str, output_folder: str, title: str = '',
            audio_only: bool = False, convert_mp3: bool = False,
            subtitles: bool = False, subtitle_lang: str = 'en',
            rate_limit: int = 0,
            scheduled_time: float = 0.0,
            proxy: str = '', cookiefile: str = '',
            cookies_from_browser: str = '', resolution: str = '',
            filename_template: str = '%(title)s') -> QueueItem:
        """Add a new item to the queue."""
        item = QueueItem(
            url=url.strip(),
            title=title or url.strip(),
            output_folder=output_folder,
            audio_only=audio_only,
            convert_mp3=convert_mp3,
            subtitles=subtitles,
            subtitle_lang=subtitle_lang,
            rate_limit=rate_limit,
            status=QueueItemStatus.SCHEDULED if scheduled_time > 0 else QueueItemStatus.PENDING,
            scheduled_time=scheduled_time,
            proxy=proxy,
            cookiefile=cookiefile,
            cookies_from_browser=cookies_from_browser,
            resolution=resolution,
            filename_template=filename_template,
        )
        with self._lock:
            self._items[item.id] = item
            self._order.append(item.id)
            self._save()
        return item

    def add_batch(self, urls: List[str], output_folder: str, **kwargs) -> List[QueueItem]:
        """Add multiple URLs to the queue at once."""
        items = []
        with self._lock:
            for url in urls:
                u = url.strip()
                if not u:
                    continue
                item = QueueItem(
                    url=u,
                    title=u,
                    output_folder=output_folder,
                    audio_only=kwargs.get('audio_only', False),
                    convert_mp3=kwargs.get('convert_mp3', False),
                    subtitles=kwargs.get('subtitles', False),
                    subtitle_lang=kwargs.get('subtitle_lang', 'en'),
                    rate_limit=kwargs.get('rate_limit', 0),
                    proxy=kwargs.get('proxy', ''),
                    cookiefile=kwargs.get('cookiefile', ''),
                    cookies_from_browser=kwargs.get('cookies_from_browser', ''),
                    resolution=kwargs.get('resolution', ''),
                    filename_template=kwargs.get('filename_template', '%(title)s'),
                )
                self._items[item.id] = item
                self._order.append(item.id)
                items.append(item)
            self._save()
        return items

    def remove(self, item_id: str) -> bool:
        """Remove an item from the queue."""
        with self._lock:
            if item_id in self._items:
                item = self._items[item_id]
                if item.status == QueueItemStatus.DOWNLOADING:
                    return False  # Can't remove while downloading
                del self._items[item_id]
                self._order = [k for k in self._order if k != item_id]
                self._save()
                return True
        return False

    def cancel(self, item_id: str) -> bool:
        """Cancel a pending or scheduled item."""
        with self._lock:
            if item_id in self._items:
                item = self._items[item_id]
                if item.status in (QueueItemStatus.PENDING, QueueItemStatus.SCHEDULED):
                    item.status = QueueItemStatus.CANCELLED
                    self._save()
                    return True
        return False

    def clear_completed(self) -> int:
        """Remove all completed/failed/cancelled items."""
        with self._lock:
            to_remove = [
                k for k, v in self._items.items()
                if v.status in (QueueItemStatus.COMPLETED, QueueItemStatus.FAILED, QueueItemStatus.CANCELLED)
            ]
            for k in to_remove:
                del self._items[k]
            self._order = [k for k in self._order if k in self._items]
            self._save()
            return len(to_remove)

    def get_all(self) -> List[QueueItem]:
        """Return all items in order."""
        with self._lock:
            return [self._items[k] for k in self._order if k in self._items]

    def get(self, item_id: str) -> Optional[QueueItem]:
        with self._lock:
            return self._items.get(item_id)

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for v in self._items.values()
                       if v.status in (QueueItemStatus.PENDING, QueueItemStatus.SCHEDULED))

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for v in self._items.values()
                       if v.status == QueueItemStatus.DOWNLOADING)

    # ─── Background worker ──────────────────────────────────────────────

    def set_download_function(self, fn: Callable):
        """Set the function used to perform downloads.
        
        fn signature: fn(item: QueueItem, progress_cb: Callable[[int], None]) -> str
        Should return the downloaded filepath.
        """
        self._download_fn = fn

    def start_worker(self):
        """Start the background processing thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop_worker(self):
        """Stop the background processing thread."""
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _worker_loop(self):
        """Background loop that processes pending items."""
        while not self._stop_event.is_set():
            item = self._pick_next()
            if item is None:
                self._stop_event.wait(2)
                continue

            if not self._download_fn:
                logger.error('No download function registered; marking item %s as failed. '
                             'Call set_download_function() before start_worker().', item.id)
                with self._lock:
                    item.status = QueueItemStatus.FAILED
                    item.error = 'No download function registered'
                    item.finished_at = time.time()
                    self._save()
                continue

            try:
                def _progress(pct: int):
                    with self._lock:
                        item.progress = min(pct, 100)

                filepath = self._download_fn(item, _progress)

                with self._lock:
                    item.status = QueueItemStatus.COMPLETED
                    item.progress = 100
                    item.filepath = filepath or ''
                    item.finished_at = time.time()
                    self._save()

            except Exception as e:
                logger.error('Queue download failed for %s: %s', item.url, e)
                with self._lock:
                    item.status = QueueItemStatus.FAILED
                    item.error = str(e)[:200]
                    item.finished_at = time.time()
                    self._save()

    def _pick_next(self) -> Optional[QueueItem]:
        """Pick the next item to download, atomically marking it as DOWNLOADING."""
        now = time.time()
        with self._lock:
            # Inline active count to avoid re-acquiring the non-reentrant lock
            active = sum(1 for v in self._items.values() if v.status == QueueItemStatus.DOWNLOADING)
            if active >= self._max_concurrent:
                return None
            for item_id in self._order:
                item = self._items.get(item_id)
                if item is None:
                    continue
                if item.status == QueueItemStatus.PENDING or (
                    item.status == QueueItemStatus.SCHEDULED and item.scheduled_time <= now
                ):
                    # Mark DOWNLOADING atomically inside the lock to prevent two workers
                    # from picking the same item in concurrent calls.
                    item.status = QueueItemStatus.DOWNLOADING
                    item.started_at = time.time()
                    self._save()
                    return item
        return None
