"""Queue adapter for the authoritative download core.

DownloadQueue owns scheduling/state. This adapter translates QueueItem fields into
`download_core` arguments, reports progress back to the queue, and writes
successful downloads to the history DB.
"""

from __future__ import annotations

import os
from typing import Callable

from download_core import download_with_ytdlp_result
from download_db import record_download
from download_queue import QueueItem


def _subtitle_langs(item: QueueItem):
    if not item.subtitles:
        return None
    langs = [lang.strip() for lang in item.subtitle_lang.split(',') if lang.strip()]
    return langs or ['en']


def download_queue_item(item: QueueItem, progress_cb: Callable[..., None]) -> str:
    """Execute one QueueItem through the canonical download core.

    progress_cb receives (pct, downloaded=, total=, speed=, eta=); pct is None when
    the size is unknown (live streams). It is called on every progress update
    because it may raise download_errors.DownloadCancelled, which download_core
    lets through to abort.
    """

    def _progress(_filename: str, downloaded: int, total: int, speed: float, eta: float) -> None:
        pct = max(0, min(100, int(downloaded / total * 100))) if total > 0 else None
        progress_cb(pct, downloaded=downloaded, total=total, speed=speed, eta=int(eta or 0))

    result = download_with_ytdlp_result(
        item.url,
        item.output_folder,
        audio_only=item.audio_only,
        convert_mp3=item.convert_mp3,
        progress_callback=_progress,
        subtitle_langs=_subtitle_langs(item),
        rate_limit_kbps=item.rate_limit,
        cookies_from_browser=item.cookies_from_browser or None,
        resolution=item.resolution or None,
        filename_template=item.filename_template or None,
        proxy=item.proxy or None,
        cookiefile=item.cookiefile or None,
    )

    filepath = result.filepath
    if result.title:
        # Batch/URL-only items are queued with the URL as their title
        item.title = result.title
    record_download(
        item.url,
        item.output_folder,
        filepath,
        title=result.title,
        size=os.path.getsize(filepath) if filepath and os.path.isfile(filepath) else 0,
        mode='audio' if (item.audio_only or item.convert_mp3) else 'video',
    )
    return filepath
