"""FastAPI-based REST API server for YouTube Downloader."""
import os
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from pytube_helper import (
    YTDLP_AVAILABLE, is_ffmpeg_available, PYDUB_AVAILABLE,
    get_video_streams, extract_playlist_urls_with_titles, extract_channel_videos,
)
from download_db import is_downloaded, get_history, clear_history
from download_errors import classify_download_error
from download_queue import DownloadQueue, QueueItem, QueueItemStatus
from queue_download_adapter import download_queue_item

app = FastAPI(
    title='YouTube Downloader API',
    description='REST API for downloading YouTube videos, playlists, and channels.',
    version='1.1.0',
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get('CORS_ORIGINS', '*').split(',') if o.strip()],
    allow_methods=['*'], allow_headers=['*'],
)

DEFAULT_OUTPUT = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DEFAULT_OUTPUT, exist_ok=True)


def _api_error(status_code: int, code: str, message: str, retryable: bool = False):
    raise HTTPException(status_code=status_code, detail={
        'code': code, 'message': message, 'retryable': retryable,
    })


def _validate_output_folder(folder: str) -> str:
    if not folder:
        return DEFAULT_OUTPUT
    normalized = os.path.normpath(folder)
    parts = normalized.replace('\\', '/').split('/')
    if '..' in parts:
        _api_error(400, 'invalid_output_folder',
                   'output_folder must not contain path traversal (..)', False)
    return os.path.realpath(os.path.abspath(normalized))


_queue = DownloadQueue(persist_path=os.path.join(DEFAULT_OUTPUT, '.queue.json'))
_queue.set_download_function(download_queue_item)
_queue.start_worker()


class DownloadRequest(BaseModel):
    url: str
    output_folder: str = ''
    audio_only: bool = False
    convert_mp3: bool = False
    subtitles: bool = False
    subtitle_lang: str = 'en'
    rate_limit: int = Field(0, description='Speed limit in KB/s, 0 = unlimited')
    skip_duplicates: bool = True
    proxy: str = ''
    cookiefile: str = ''
    resolution: str = ''
    filename_template: str = '%(title)s'


class BatchRequest(BaseModel):
    urls: List[str]
    output_folder: str = ''
    audio_only: bool = False
    convert_mp3: bool = False
    subtitles: bool = False
    subtitle_lang: str = 'en'
    rate_limit: int = 0
    proxy: str = ''
    cookiefile: str = ''
    resolution: str = ''
    filename_template: str = '%(title)s'


class PlaylistRequest(BaseModel):
    url: str
    output_folder: str = ''
    audio_only: bool = False
    convert_mp3: bool = False
    subtitles: bool = False
    subtitle_lang: str = 'en'
    rate_limit: int = 0
    max_items: int = 0
    concurrency: int = 3
    proxy: str = ''
    cookiefile: str = ''
    resolution: str = ''
    filename_template: str = '%(title)s'


class ScheduleRequest(BaseModel):
    url: str
    output_folder: str = ''
    audio_only: bool = False
    convert_mp3: bool = False
    subtitles: bool = False
    subtitle_lang: str = 'en'
    rate_limit: int = 0
    scheduled_time: str = Field(..., description='ISO format datetime or Unix timestamp')
    proxy: str = ''
    cookiefile: str = ''
    resolution: str = ''
    filename_template: str = '%(title)s'


class QueueItemResponse(BaseModel):
    id: str
    url: str
    title: str
    status: str
    progress: int
    error: str = ''
    error_code: str = ''
    retryable: bool = False
    attempts: int = 0
    filepath: str = ''
    added_at: float
    started_at: float
    finished_at: float


class StatusResponse(BaseModel):
    ytdlp_available: bool
    ffmpeg_available: bool
    pydub_available: bool
    queue_pending: int
    queue_active: int


def _queue_response(item: QueueItem) -> QueueItemResponse:
    return QueueItemResponse(**{
        k: v for k, v in item.to_dict().items() if k in QueueItemResponse.model_fields
    })


def _add_queue_item(req, out: str, scheduled_time: float = 0.0):
    return _queue.add(
        url=req.url, output_folder=out,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit, scheduled_time=scheduled_time,
        proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )


@app.get('/api/status', response_model=StatusResponse)
def get_status():
    return StatusResponse(
        ytdlp_available=YTDLP_AVAILABLE,
        ffmpeg_available=is_ffmpeg_available(),
        pydub_available=PYDUB_AVAILABLE,
        queue_pending=_queue.pending_count(), queue_active=_queue.active_count(),
    )


@app.post('/api/download', response_model=QueueItemResponse)
def start_download(req: DownloadRequest):
    out = _validate_output_folder(req.output_folder)
    os.makedirs(out, exist_ok=True)
    if req.skip_duplicates:
        mode = 'audio' if (req.audio_only or req.convert_mp3) else 'video'
        dup = is_downloaded(req.url, out, mode=mode)
        if dup:
            return QueueItemResponse(
                id='duplicate', url=req.url, title=dup.get('title', ''),
                status='already_downloaded', progress=100,
                filepath=dup.get('filepath', ''), added_at=dup.get('timestamp', 0),
                started_at=0, finished_at=0,
            )
    return _queue_response(_add_queue_item(req, out))


@app.post('/api/batch', response_model=List[QueueItemResponse])
def batch_download(req: BatchRequest):
    out = _validate_output_folder(req.output_folder)
    os.makedirs(out, exist_ok=True)
    items = _queue.add_batch(
        urls=req.urls, output_folder=out, audio_only=req.audio_only,
        convert_mp3=req.convert_mp3, subtitles=req.subtitles,
        subtitle_lang=req.subtitle_lang, rate_limit=req.rate_limit,
        proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )
    return [_queue_response(it) for it in items]


def _extract_or_api_error(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        failure = classify_download_error(exc)
        _api_error(400, failure.code.value, failure.message, failure.retryable)


@app.post('/api/playlist')
def playlist_download(req: PlaylistRequest):
    out = _validate_output_folder(req.output_folder)
    result = _extract_or_api_error(extract_playlist_urls_with_titles, req.url)
    pl_title = result.get('playlist_title', 'Playlist')
    pl_items = result.get('items', [])
    if req.max_items > 0:
        pl_items = pl_items[:req.max_items]
    safe_title = "".join(c for c in pl_title if c.isalnum() or c in ' ._-()[]').strip() or 'Playlist'
    folder = os.path.join(out, safe_title)
    os.makedirs(folder, exist_ok=True)
    items = _queue.add_batch(
        urls=[it['url'] for it in pl_items if it.get('url')], output_folder=folder,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit, proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )
    return {'playlist_title': pl_title, 'folder': folder,
            'total_items': len(pl_items), 'queued': len(items)}


@app.post('/api/channel')
def channel_download(req: PlaylistRequest):
    out = _validate_output_folder(req.output_folder)
    result = _extract_or_api_error(extract_channel_videos, req.url,
                                   max_items=req.max_items or None)
    title = result.get('channel_title', 'Channel')
    ch_items = result.get('items', [])
    safe_title = "".join(c for c in title if c.isalnum() or c in ' ._-()[]').strip() or 'Channel'
    folder = os.path.join(out, safe_title)
    os.makedirs(folder, exist_ok=True)
    items = _queue.add_batch(
        urls=[it['url'] for it in ch_items if it.get('url')], output_folder=folder,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit, proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )
    return {'channel_title': title, 'folder': folder,
            'total_items': len(ch_items), 'queued': len(items)}


@app.post('/api/schedule', response_model=QueueItemResponse)
def schedule_download(req: ScheduleRequest):
    out = _validate_output_folder(req.output_folder)
    os.makedirs(out, exist_ok=True)
    try:
        ts = float(req.scheduled_time)
    except ValueError:
        from datetime import datetime
        try:
            ts = datetime.fromisoformat(req.scheduled_time).timestamp()
        except Exception:
            _api_error(400, 'invalid_scheduled_time', 'Invalid scheduled_time format', False)
    return _queue_response(_add_queue_item(req, out, scheduled_time=ts))


@app.get('/api/queue', response_model=List[QueueItemResponse])
def list_queue():
    return [_queue_response(it) for it in _queue.get_all()]


@app.get('/api/queue/{item_id}', response_model=QueueItemResponse)
def get_queue_item(item_id: str):
    item = _queue.get(item_id)
    if not item:
        _api_error(404, 'queue_item_not_found', 'Item not found', False)
    return _queue_response(item)


@app.delete('/api/queue/{item_id}')
def remove_queue_item(item_id: str):
    item = _queue.get(item_id)
    if not item:
        _api_error(404, 'queue_item_not_found', 'Item not found', False)
    if item.status == QueueItemStatus.DOWNLOADING:
        _api_error(409, 'queue_item_busy', 'Cannot remove a downloading item', True)
    _queue.remove(item_id)
    return {'status': 'removed'}


@app.post('/api/queue/{item_id}/cancel', response_model=QueueItemResponse)
def cancel_queue_item(item_id: str):
    item = _queue.get(item_id)
    if not item:
        _api_error(404, 'queue_item_not_found', 'Item not found', False)
    if not _queue.cancel(item_id):
        _api_error(409, 'invalid_queue_state', f'Cannot cancel item in state {item.status}', False)
    return _queue_response(_queue.get(item_id))


@app.post('/api/queue/{item_id}/retry', response_model=QueueItemResponse)
def retry_queue_item(item_id: str):
    item = _queue.get(item_id)
    if not item:
        _api_error(404, 'queue_item_not_found', 'Item not found', False)
    if item.status != QueueItemStatus.FAILED:
        _api_error(409, 'invalid_queue_state', f'Only failed items can be retried; current state={item.status}', False)
    if not item.retryable:
        _api_error(409, 'failure_not_retryable',
                   f'Failure {item.error_code or "unknown"} is not retryable', False)
    _queue.retry(item_id)
    return _queue_response(_queue.get(item_id))


@app.delete('/api/queue')
def clear_queue():
    return {'removed': _queue.clear_completed()}


@app.get('/api/history')
def download_history(output_folder: str = '', limit: int = 50):
    return get_history(_validate_output_folder(output_folder), limit=limit)


@app.delete('/api/history')
def clear_download_history(output_folder: str = ''):
    return {'cleared': clear_history(_validate_output_folder(output_folder))}


@app.get('/api/info')
def video_info(url: str):
    streams = _extract_or_api_error(get_video_streams, url)
    return {'title': streams.get('title', 'Unknown'),
            'backend': streams.get('backend', 'unknown')}


@app.get('/api/playlist/info')
def playlist_info(url: str):
    return _extract_or_api_error(extract_playlist_urls_with_titles, url)


def run_api(host: str = '0.0.0.0', port: int = 8000):
    uvicorn.run(app, host=host, port=port)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='YouTube Downloader REST API')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    run_api(host=args.host, port=args.port)
