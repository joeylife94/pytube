"""Thread-safe download queue with persistent state and explicit retry semantics."""
import os
import uuid
import time
import json
import threading
from dataclasses import dataclass, field, asdict, fields
from typing import List, Optional, Dict, Any, Callable, Set
from enum import Enum
import logging

from download_errors import DownloadCancelled, DownloadErrorCode, classify_download_error

logger = logging.getLogger(__name__)

# Upper bound for set_max_concurrent(); one worker thread is started per slot.
MAX_CONCURRENT_LIMIT = 8


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
    # Live transfer stats for the item being downloaded (bytes, bytes/s, seconds)
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0
    eta: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_ITEM_FIELDS = {f.name for f in fields(QueueItem)}


class DownloadQueue:
    """Persistent, thread-safe queue. Scheduling is separate from download execution."""

    def __init__(self, persist_path: Optional[str] = None, max_concurrent: int = 2):
        self._items: Dict[str, QueueItem] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._persist_path = persist_path or ''
        self._max_concurrent = self._clamp_concurrency(max_concurrent)
        self._worker_threads: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self._download_fn: Optional[Callable] = None
        self._cancel_requested: Set[str] = set()
        self._load()

    @staticmethod
    def _clamp_concurrency(n: int) -> int:
        return max(1, min(int(n), MAX_CONCURRENT_LIMIT))

    def _db_file(self) -> str:
        return self._persist_path or os.path.join(os.getcwd(), 'downloads', '.queue.json')

    def _load(self):
        try:
            with open(self._db_file(), 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return
        for rec in data if isinstance(data, list) else []:
            try:
                # Ignore keys written by other versions instead of dropping the queue
                item = QueueItem(**{k: v for k, v in rec.items() if k in _ITEM_FIELDS})
            except (TypeError, AttributeError):
                logger.warning('Skipping unreadable queue record: %r', rec)
                continue
            if item.status == QueueItemStatus.DOWNLOADING:
                item.status = QueueItemStatus.PENDING
                item.progress = 0
                item.started_at = 0.0
            self._reset_transfer_stats(item)
            self._items[item.id] = item
            self._order.append(item.id)

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

    @staticmethod
    def _reset_transfer_stats(item: QueueItem):
        item.downloaded_bytes = 0
        item.total_bytes = 0
        item.speed = 0.0
        item.eta = 0

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

    def add_batch(self, urls: List[str], output_folder: str,
                  titles: Optional[List[str]] = None, **kwargs) -> List[QueueItem]:
        """Queue several URLs with shared options; titles (same order) are optional."""
        items = []
        with self._lock:
            for i, url in enumerate(urls):
                u = url.strip()
                if not u:
                    continue
                title = (titles[i] if titles and i < len(titles) else '') or u
                item = QueueItem(
                    url=u, title=title, output_folder=output_folder,
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

    def request_cancel(self, item_id: str) -> bool:
        """Cancel a waiting item now, or stop an active download at its next progress update."""
        if self.cancel(item_id):
            return True
        with self._lock:
            item = self._items.get(item_id)
            if item and item.status == QueueItemStatus.DOWNLOADING:
                self._cancel_requested.add(item_id)
                return True
        return False

    def retry(self, item_id: str, force: bool = False) -> bool:
        """Requeue a FAILED item when its failure is retryable.

        force=True is for user-initiated retries (e.g. after adding cookies): it also
        requeues non-retryable failures and cancelled items.
        """
        with self._lock:
            item = self._items.get(item_id)
            if not item:
                return False
            if force:
                if item.status not in (QueueItemStatus.FAILED, QueueItemStatus.CANCELLED):
                    return False
            elif item.status != QueueItemStatus.FAILED or not item.retryable:
                return False
            item.status = QueueItemStatus.PENDING
            item.progress = 0
            item.error = ''
            item.error_code = ''
            item.retryable = False
            item.filepath = ''
            item.started_at = 0.0
            item.finished_at = 0.0
            self._reset_transfer_stats(item)
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

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    def set_max_concurrent(self, n: int):
        """Change how many downloads run at once (takes effect for the next pick)."""
        self._max_concurrent = self._clamp_concurrency(n)
        if self._worker_threads:
            self._ensure_workers()

    def set_download_function(self, fn: Callable):
        """fn(item, progress_cb) -> filepath.

        progress_cb(pct, downloaded=0, total=0, speed=0.0, eta=0) may raise
        DownloadCancelled when the user cancelled the item; fn should let it propagate.
        """
        self._download_fn = fn

    def start_worker(self):
        self._stop_event.clear()
        self._ensure_workers()

    def _ensure_workers(self):
        self._worker_threads = [t for t in self._worker_threads if t.is_alive()]
        while len(self._worker_threads) < self._max_concurrent:
            t = threading.Thread(target=self._worker_loop, daemon=True,
                                 name=f'download-worker-{len(self._worker_threads) + 1}')
            t.start()
            self._worker_threads.append(t)

    def stop_worker(self):
        self._stop_event.set()
        for t in self._worker_threads:
            t.join(timeout=5)
        self._worker_threads = []

    def _mark_failed(self, item: QueueItem, error: BaseException | str,
                     code: Optional[DownloadErrorCode] = None, retryable: Optional[bool] = None):
        failure = classify_download_error(error)
        with self._lock:
            item.status = QueueItemStatus.FAILED
            item.error = failure.message[:300]
            item.error_code = (code or failure.code).value
            item.retryable = failure.retryable if retryable is None else retryable
            item.finished_at = time.time()
            item.speed = 0.0
            item.eta = 0
            self._save()

    def _make_progress_cb(self, item: QueueItem) -> Callable:
        def _progress(pct: int, downloaded: int = 0, total: int = 0,
                      speed: float = 0.0, eta: int = 0):
            if item.id in self._cancel_requested:
                raise DownloadCancelled(f'Download cancelled: {item.id}')
            with self._lock:
                item.progress = max(0, min(int(pct), 100))
                item.downloaded_bytes = int(downloaded or 0)
                item.total_bytes = int(total or 0)
                item.speed = float(speed or 0.0)
                item.eta = int(eta or 0)
        return _progress

    def _worker_loop(self):
        while not self._stop_event.is_set():
            item = self._pick_next()
            if item is None:
                self._stop_event.wait(1)
                continue
            if not self._download_fn:
                logger.error('No download function registered; marking item %s failed', item.id)
                self._mark_failed(item, 'No download function registered',
                                  code=DownloadErrorCode.INTERNAL, retryable=False)
                continue
            try:
                filepath = self._download_fn(item, self._make_progress_cb(item))
                with self._lock:
                    item.status = QueueItemStatus.COMPLETED
                    item.progress = 100
                    item.filepath = filepath or ''
                    item.error = ''
                    item.error_code = ''
                    item.retryable = False
                    item.finished_at = time.time()
                    item.speed = 0.0
                    item.eta = 0
                    self._save()
            except DownloadCancelled:
                with self._lock:
                    item.status = QueueItemStatus.CANCELLED
                    item.finished_at = time.time()
                    self._reset_transfer_stats(item)
                    self._save()
            except Exception as e:
                logger.error('Queue download failed for %s: %s', item.url, e)
                self._mark_failed(item, e)
            finally:
                self._cancel_requested.discard(item.id)

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
                    self._reset_transfer_stats(item)
                    self._save()
                    return item
        return None
