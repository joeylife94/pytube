"""Thread-safe download queue with persistent state and explicit retry semantics."""
import os
import uuid
import time
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
import logging

from download_errors import DownloadErrorCode, classify_download_error

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
    rate_limit: int = 0
    status: str = QueueItemStatus.PENDING
    progress: int = 0
    error: str = ''
    error_code: str = ''
    retryable: bool = False
    attempts: int = 0
    filepath: str = ''
    added_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    scheduled_time: float = 0.0
    proxy: str = ''
    cookiefile: str = ''
    cookies_from_browser: str = ''
    resolution: str = ''
    filename_template: str = '%(title)s'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DownloadQueue:
    """Persistent, thread-safe queue. Scheduling is separate from download execution."""

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

    def _db_file(self) -> str:
        return self._persist_path or os.path.join(os.getcwd(), 'downloads', '.queue.json')

    def _load(self):
        try:
            with open(self._db_file(), 'r', encoding='utf-8') as f:
                data = json.load(f)
            for rec in data:
                item = QueueItem(**rec)
                if item.status == QueueItemStatus.DOWNLOADING:
                    item.status = QueueItemStatus.PENDING
                    item.progress = 0
                    item.started_at = 0.0
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
                json.dump([self._items[k].to_dict() for k in self._order if k in self._items], f,
                          ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as e:
            logger.error('Failed to save queue: %s', e)

    def add(self, url: str, output_folder: str, title: str = '',
            audio_only: bool = False, convert_mp3: bool = False,
            subtitles: bool = False, subtitle_lang: str = 'en', rate_limit: int = 0,
            scheduled_time: float = 0.0, proxy: str = '', cookiefile: str = '',
            cookies_from_browser: str = '', resolution: str = '',
            filename_template: str = '%(title)s') -> QueueItem:
        item = QueueItem(
            url=url.strip(), title=title or url.strip(), output_folder=output_folder,
            audio_only=audio_only, convert_mp3=convert_mp3, subtitles=subtitles,
            subtitle_lang=subtitle_lang, rate_limit=rate_limit,
            status=QueueItemStatus.SCHEDULED if scheduled_time > 0 else QueueItemStatus.PENDING,
            scheduled_time=scheduled_time, proxy=proxy, cookiefile=cookiefile,
            cookies_from_browser=cookies_from_browser, resolution=resolution,
            filename_template=filename_template,
        )
        with self._lock:
            self._items[item.id] = item
            self._order.append(item.id)
            self._save()
        return item

    def add_batch(self, urls: List[str], output_folder: str, **kwargs) -> List[QueueItem]:
        items = []
        with self._lock:
            for url in urls:
                u = url.strip()
                if not u:
                    continue
                item = QueueItem(
                    url=u, title=u, output_folder=output_folder,
                    audio_only=kwargs.get('audio_only', False),
                    convert_mp3=kwargs.get('convert_mp3', False),
                    subtitles=kwargs.get('subtitles', False),
                    subtitle_lang=kwargs.get('subtitle_lang', 'en'),
                    rate_limit=kwargs.get('rate_limit', 0),
                    proxy=kwargs.get('proxy', ''), cookiefile=kwargs.get('cookiefile', ''),
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
        with self._lock:
            item = self._items.get(item_id)
            if not item or item.status == QueueItemStatus.DOWNLOADING:
                return False
            del self._items[item_id]
            self._order = [k for k in self._order if k != item_id]
            self._save()
            return True

    def cancel(self, item_id: str) -> bool:
        with self._lock:
            item = self._items.get(item_id)
            if item and item.status in (QueueItemStatus.PENDING, QueueItemStatus.SCHEDULED):
                item.status = QueueItemStatus.CANCELLED
                item.error = ''
                item.error_code = ''
                item.retryable = False
                item.finished_at = time.time()
                self._save()
                return True
        return False

    def retry(self, item_id: str) -> bool:
        """Requeue a FAILED item only when its failure contract marks it retryable."""
        with self._lock:
            item = self._items.get(item_id)
            if not item or item.status != QueueItemStatus.FAILED or not item.retryable:
                return False
            item.status = QueueItemStatus.PENDING
            item.progress = 0
            item.error = ''
            item.error_code = ''
            item.retryable = False
            item.filepath = ''
            item.started_at = 0.0
            item.finished_at = 0.0
            self._save()
            return True

    def clear_completed(self) -> int:
        with self._lock:
            to_remove = [k for k, v in self._items.items()
                         if v.status in (QueueItemStatus.COMPLETED, QueueItemStatus.FAILED,
                                         QueueItemStatus.CANCELLED)]
            for k in to_remove:
                del self._items[k]
            self._order = [k for k in self._order if k in self._items]
            self._save()
            return len(to_remove)

    def get_all(self) -> List[QueueItem]:
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
            return sum(1 for v in self._items.values() if v.status == QueueItemStatus.DOWNLOADING)

    def set_download_function(self, fn: Callable):
        self._download_fn = fn

    def start_worker(self):
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop_worker(self):
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _mark_failed(self, item: QueueItem, error: BaseException | str,
                     code: Optional[DownloadErrorCode] = None, retryable: Optional[bool] = None):
        failure = classify_download_error(error)
        with self._lock:
            item.status = QueueItemStatus.FAILED
            item.error = failure.message[:300]
            item.error_code = (code or failure.code).value
            item.retryable = failure.retryable if retryable is None else retryable
            item.finished_at = time.time()
            self._save()

    def _worker_loop(self):
        while not self._stop_event.is_set():
            item = self._pick_next()
            if item is None:
                self._stop_event.wait(2)
                continue
            if not self._download_fn:
                logger.error('No download function registered; marking item %s failed', item.id)
                self._mark_failed(item, 'No download function registered',
                                  code=DownloadErrorCode.INTERNAL, retryable=False)
                continue
            try:
                def _progress(pct: int):
                    with self._lock:
                        item.progress = max(0, min(int(pct), 100))
                filepath = self._download_fn(item, _progress)
                with self._lock:
                    item.status = QueueItemStatus.COMPLETED
                    item.progress = 100
                    item.filepath = filepath or ''
                    item.error = ''
                    item.error_code = ''
                    item.retryable = False
                    item.finished_at = time.time()
                    self._save()
            except Exception as e:
                logger.error('Queue download failed for %s: %s', item.url, e)
                self._mark_failed(item, e)

    def _pick_next(self) -> Optional[QueueItem]:
        now = time.time()
        with self._lock:
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
                    item.status = QueueItemStatus.DOWNLOADING
                    item.progress = 0
                    item.error = ''
                    item.error_code = ''
                    item.retryable = False
                    item.started_at = time.time()
                    item.finished_at = 0.0
                    item.attempts += 1
                    self._save()
                    return item
        return None
