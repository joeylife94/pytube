"""FastAPI-based REST API server for YouTube Downloader."""
import os
import uuid
import time
from typing import Optional, List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import logging

from pytube_helper import (
    YTDLP_AVAILABLE, is_ffmpeg_available, PYDUB_AVAILABLE,
    download_playlist, get_video_streams,
    extract_playlist_urls_with_titles, extract_channel_videos,
)
from download_db import is_downloaded, record_download, get_history, clear_history
from download_queue import DownloadQueue, QueueItem, QueueItemStatus

logger = logging.getLogger(__name__)

# ─── App setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title='YouTube Downloader API',
    description='REST API for downloading YouTube videos, playlists, and channels.',
    version='1.0.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get('CORS_ORIGINS', '*').split(',') if o.strip()],
    allow_methods=['*'],
    allow_headers=['*'],
)

DEFAULT_OUTPUT = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DEFAULT_OUTPUT, exist_ok=True)


def _validate_output_folder(folder: str) -> str:
    """Validate and resolve output folder, rejecting path traversal attempts."""
    if not folder:
        return DEFAULT_OUTPUT
    # Normalize syntactically first so a/b/../../.. becomes ../.. etc.
    normalized = os.path.normpath(folder)
    parts = normalized.replace('\\', '/').split('/')
    if '..' in parts:
        raise HTTPException(status_code=400, detail='output_folder must not contain path traversal (..)')
    # Resolve symlinks to get the true absolute path
    return os.path.realpath(os.path.abspath(normalized))

# Shared queue instance
_queue = DownloadQueue(persist_path=os.path.join(DEFAULT_OUTPUT, '.queue.json'))


def _do_download(item: QueueItem, progress_cb):
    """Execute a queue item download."""
    import yt_dlp
    if not YTDLP_AVAILABLE:
        raise RuntimeError('yt-dlp not available')

    def _hook(d):
        if d.get('status') != 'downloading':
            return
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
        if total > 0:
            progress_cb(int(downloaded / total * 100))

    _tmpl = item.filename_template or '%(title)s'
    ydl_opts = {
        'outtmpl': os.path.join(item.output_folder, f'{_tmpl}.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [_hook],
    }
    if item.audio_only:
        ydl_opts['format'] = 'bestaudio/best'
        if item.convert_mp3:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
    elif item.resolution and item.resolution != 'best':
        res_num = item.resolution.replace('p', '')
        ydl_opts['format'] = (
            f'bestvideo[height<={res_num}][ext=mp4]+bestaudio[ext=m4a]'
            f'/bestvideo[height<={res_num}]+bestaudio/best[height<={res_num}]/best'
        )
        ydl_opts['merge_output_format'] = 'mp4'
    if item.subtitles:
        ydl_opts['writesubtitles'] = True
        ydl_opts['writeautomaticsub'] = True
        langs = [l.strip() for l in item.subtitle_lang.split(',') if l.strip()]
        ydl_opts['subtitleslangs'] = langs or ['en']
        ydl_opts['subtitlesformat'] = 'srt/best'
    if item.rate_limit and item.rate_limit > 0:
        ydl_opts['ratelimit'] = item.rate_limit * 1024
    if item.proxy:
        ydl_opts['proxy'] = item.proxy
    if item.cookiefile and os.path.isfile(item.cookiefile):
        ydl_opts['cookiefile'] = item.cookiefile
    if item.cookies_from_browser:
        ydl_opts['cookiesfrombrowser'] = (item.cookies_from_browser,)

    os.makedirs(item.output_folder, exist_ok=True)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(item.url, download=True)
        if 'requested_downloads' in info and info['requested_downloads']:
            filepath = info['requested_downloads'][0].get('filepath', '')
        else:
            filepath = ydl.prepare_filename(info)

    record_download(item.url, item.output_folder, filepath,
                    title=info.get('title', ''),
                    size=os.path.getsize(filepath) if os.path.isfile(filepath) else 0,
                    mode='audio' if (item.audio_only or item.convert_mp3) else 'video')
    return filepath

_queue.set_download_function(_do_download)
_queue.start_worker()

# ─── Request/Response models ────────────────────────────────────────────────

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
    error: str
    filepath: str
    added_at: float
    started_at: float
    finished_at: float

class StatusResponse(BaseModel):
    ytdlp_available: bool
    ffmpeg_available: bool
    pydub_available: bool
    queue_pending: int
    queue_active: int

# ─── Endpoints ──────────────────────────────────────────────────────────────

@app.get('/api/status', response_model=StatusResponse)
def get_status():
    """Get system status and environment info."""
    return StatusResponse(
        ytdlp_available=YTDLP_AVAILABLE,
        ffmpeg_available=is_ffmpeg_available(),
        pydub_available=PYDUB_AVAILABLE,
        queue_pending=_queue.pending_count(),
        queue_active=_queue.active_count(),
    )


@app.post('/api/download', response_model=QueueItemResponse)
def start_download(req: DownloadRequest):
    """Add a single URL to the download queue."""
    out = _validate_output_folder(req.output_folder)
    os.makedirs(out, exist_ok=True)

    if req.skip_duplicates:
        dup = is_downloaded(req.url, out, mode='audio' if (req.audio_only or req.convert_mp3) else 'video')
        if dup:
            return QueueItemResponse(
                id='duplicate',
                url=req.url,
                title=dup.get('title', ''),
                status='already_downloaded',
                progress=100,
                error='',
                filepath=dup.get('filepath', ''),
                added_at=dup.get('timestamp', 0),
                started_at=0, finished_at=0,
            )

    item = _queue.add(
        url=req.url, output_folder=out,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit,
        proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )
    return QueueItemResponse(**{k: v for k, v in item.to_dict().items() if k in QueueItemResponse.model_fields})


@app.post('/api/batch', response_model=List[QueueItemResponse])
def batch_download(req: BatchRequest):
    """Add multiple URLs to the download queue at once."""
    out = _validate_output_folder(req.output_folder)
    os.makedirs(out, exist_ok=True)

    items = _queue.add_batch(
        urls=req.urls, output_folder=out,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit,
        proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )
    return [
        QueueItemResponse(**{k: v for k, v in it.to_dict().items() if k in QueueItemResponse.model_fields})
        for it in items
    ]


@app.post('/api/playlist')
def playlist_download(req: PlaylistRequest):
    """Fetch playlist info and add items to the queue."""
    out = _validate_output_folder(req.output_folder)

    try:
        result = extract_playlist_urls_with_titles(req.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    pl_title = result.get('playlist_title', 'Playlist')
    pl_items = result.get('items', [])

    if req.max_items > 0:
        pl_items = pl_items[:req.max_items]

    safe_title = "".join(c for c in pl_title if c.isalnum() or c in ' ._-()[]').strip() or 'Playlist'
    pl_folder = os.path.join(out, safe_title)
    os.makedirs(pl_folder, exist_ok=True)

    urls = [it['url'] for it in pl_items if it.get('url')]
    items = _queue.add_batch(
        urls=urls, output_folder=pl_folder,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit,
        proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )

    return {
        'playlist_title': pl_title,
        'folder': pl_folder,
        'total_items': len(pl_items),
        'queued': len(items),
    }


@app.post('/api/channel')
def channel_download(req: PlaylistRequest):
    """Download all videos from a channel."""
    out = _validate_output_folder(req.output_folder)
    try:
        result = extract_channel_videos(req.url, max_items=req.max_items or None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    ch_title = result.get('channel_title', 'Channel')
    ch_items = result.get('items', [])

    safe_title = "".join(c for c in ch_title if c.isalnum() or c in ' ._-()[]').strip() or 'Channel'
    ch_folder = os.path.join(out, safe_title)
    os.makedirs(ch_folder, exist_ok=True)

    urls = [it['url'] for it in ch_items if it.get('url')]
    items = _queue.add_batch(
        urls=urls, output_folder=ch_folder,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit,
        proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )
    return {
        'channel_title': ch_title,
        'folder': ch_folder,
        'total_items': len(ch_items),
        'queued': len(items),
    }


@app.post('/api/schedule', response_model=QueueItemResponse)
def schedule_download(req: ScheduleRequest):
    """Schedule a download for a specific time."""
    out = _validate_output_folder(req.output_folder)
    os.makedirs(out, exist_ok=True)

    # Parse scheduled time
    try:
        ts = float(req.scheduled_time)
    except ValueError:
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(req.scheduled_time)
            ts = dt.timestamp()
        except Exception:
            raise HTTPException(status_code=400, detail='Invalid scheduled_time format')

    item = _queue.add(
        url=req.url, output_folder=out,
        audio_only=req.audio_only, convert_mp3=req.convert_mp3,
        subtitles=req.subtitles, subtitle_lang=req.subtitle_lang,
        rate_limit=req.rate_limit,
        scheduled_time=ts,
        proxy=req.proxy, cookiefile=req.cookiefile,
        resolution=req.resolution, filename_template=req.filename_template,
    )
    return QueueItemResponse(**{k: v for k, v in item.to_dict().items() if k in QueueItemResponse.model_fields})


@app.get('/api/queue', response_model=List[QueueItemResponse])
def list_queue():
    """List all items in the download queue."""
    items = _queue.get_all()
    return [
        QueueItemResponse(**{k: v for k, v in it.to_dict().items() if k in QueueItemResponse.model_fields})
        for it in items
    ]


@app.get('/api/queue/{item_id}', response_model=QueueItemResponse)
def get_queue_item(item_id: str):
    """Get details of a specific queue item."""
    item = _queue.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail='Item not found')
    return QueueItemResponse(**{k: v for k, v in item.to_dict().items() if k in QueueItemResponse.model_fields})


@app.delete('/api/queue/{item_id}')
def remove_queue_item(item_id: str):
    """Remove an item from the queue."""
    if _queue.remove(item_id):
        return {'status': 'removed'}
    raise HTTPException(status_code=400, detail='Cannot remove (item not found or currently downloading)')


@app.post('/api/queue/{item_id}/cancel')
def cancel_queue_item(item_id: str):
    """Cancel a pending queue item."""
    if _queue.cancel(item_id):
        return {'status': 'cancelled'}
    raise HTTPException(status_code=400, detail='Cannot cancel')


@app.delete('/api/queue')
def clear_queue():
    """Remove all completed/failed/cancelled items."""
    n = _queue.clear_completed()
    return {'removed': n}


@app.get('/api/history')
def download_history(output_folder: str = '', limit: int = 50):
    """Get download history."""
    out = _validate_output_folder(output_folder)
    return get_history(out, limit=limit)


@app.delete('/api/history')
def clear_download_history(output_folder: str = ''):
    """Clear download history."""
    out = _validate_output_folder(output_folder)
    n = clear_history(out)
    return {'cleared': n}


@app.get('/api/info')
def video_info(url: str):
    """Get video metadata without downloading."""
    try:
        streams = get_video_streams(url)
        return {
            'title': streams.get('title', 'Unknown'),
            'backend': streams.get('backend', 'unknown'),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get('/api/playlist/info')
def playlist_info(url: str):
    """Get playlist info without downloading."""
    try:
        result = extract_playlist_urls_with_titles(url)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Entry point ────────────────────────────────────────────────────────────

def run_api(host: str = '0.0.0.0', port: int = 8000):
    """Run the API server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='YouTube Downloader REST API')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    run_api(host=args.host, port=args.port)
