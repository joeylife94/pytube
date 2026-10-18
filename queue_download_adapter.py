"""Queue adapter for the authoritative download core.

DownloadQueue owns scheduling/state. This adapter translates QueueItem fields into
`download_core` arguments, reports percentage progress back to the queue, and writes
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


def download_queue_item(item: QueueItem, progress_cb: Callable[[int], None]) -> str:
    """Execute one QueueItem through the canonical download core."""

    def _progress(_filename: str, downloaded: int, total: int, _speed: float, _eta: float) -> None:
        if total > 0:
            progress_cb(max(0, min(100, int(downloaded / total * 100))))

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
    record_download(
        item.url,
        item.output_folder,
        filepath,
        title=result.title,
        size=os.path.getsize(filepath) if filepath and os.path.isfile(filepath) else 0,
        mode='audio' if (item.audio_only or item.convert_mp3) else 'video',
    )
    return filepath
