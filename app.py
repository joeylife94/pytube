"""Streamlit-based YouTube downloader GUI application."""
import os
import streamlit as st
from pytube_helper import (
    get_video_streams, download_video, download_audio, download_playlist,
    PYDUB_AVAILABLE, is_ffmpeg_available, has_yt_dlp, download_fallback,
    download_with_ytdlp
)
from progress_store import progress_file_for_id, read_progress_file, list_progress_files
import uuid
from pytube import Playlist
import time
from typing import Optional, Callable


def human_speed(bps: float) -> str:
    """Convert bytes per second to human-readable format.
    
    Args:
        bps: Bytes per second
        
    Returns:
        Human-readable speed string
    """
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if bps < 1024.0:
            return f"{bps:3.1f}{unit}"
        bps /= 1024.0
    return f"{bps:.1f}TB/s"

def create_progress_callback(start_time: dict, progress_bar, status_text):
    """Create a standardized progress callback for downloads.
    
    Args:
        start_time: Dict with 't' key to track start time
        progress_bar: Streamlit progress bar widget
        status_text: Streamlit text widget for status updates
        
    Returns:
        Progress callback function
    """
    def progress_cb(received: int, total: int):
        now = time.time()
        if start_time['t'] is None:
            start_time['t'] = now
        elapsed = max(now - start_time['t'], 1e-6)
        speed = received / elapsed
        eta = int((total - received) / speed) if speed > 0 else 0
        try:
            percent = int(received / total * 100)
            progress_bar.progress(min(percent, 100))
            status_text.text(
                f"{received:,} / {total:,} bytes ({percent}%) — "
                f"{human_speed(speed)} — ETA {eta}s"
            )
        except Exception:
            pass
    
    return progress_cb


def ensure_output_folder(folder: str) -> str:
    """Ensure the output folder exists.
    
    Args:
        folder: Desired output folder path
        
    Returns:
        Valid output folder path
    """
    if not folder:
        folder = os.path.join(os.getcwd(), 'downloads')
    
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        st.warning(f'Could not create output folder: {folder}. Falling back to current directory')
        folder = os.getcwd()
    
    return folder

st.title('YouTube Downloader (pytube)')

st.markdown('A simple GUI for downloading YouTube videos, audio, and playlists using pytube.')

url = st.text_input('YouTube video or playlist URL')
is_playlist = st.checkbox('Is this a playlist?')
mode = st.radio('Download mode', ['Video', 'Audio'])
backend = st.selectbox('Download backend', ['yt-dlp', 'pytube (default)', 'pytube then yt-dlp fallback'], index=0)

# Whether to show live progress in the UI (this will block the UI while downloading)
show_live_progress = st.checkbox('Show live progress in UI (blocks UI while downloading)', value=True)

col1, col2 = st.columns(2)
with col1:
    resolution = st.selectbox('Preferred resolution (for video)', ['Highest', '1080p', '720p', '480p', '360p', '240p'], index=0)
with col2:
    convert_mp3 = st.checkbox('Convert audio to MP3 (requires pydub + ffmpeg)', value=False)

output_folder = st.text_input('Output folder (leave blank = current directory)', value='')
# default to a repo-local downloads/ folder when blank
if not output_folder:
    output_folder = os.path.join(os.getcwd(), 'downloads')

# ensure the output folder exists
try:
    os.makedirs(output_folder, exist_ok=True)
except Exception:
    st.warning(f'Could not create output folder: {output_folder}. Falling back to current directory')
    output_folder = os.getcwd()

if convert_mp3 and not PYDUB_AVAILABLE:
    st.warning('pydub is not available. Install pydub and ffmpeg to enable MP3 conversion.')

if not is_ffmpeg_available():
    with st.expander('ffmpeg not found (why needed & how to install)'):
        st.markdown('''
        MP3 conversion requires ffmpeg. On Windows you can install using one of these methods:

        - Download official static build from https://ffmpeg.org/download.html and add `ffmpeg.exe` to your PATH.
        - If you have Chocolatey installed (admin), run: `choco install ffmpeg` in an elevated PowerShell.

        After installation, restart your shell/terminal and restart this app.
        ''')

download_btn = st.button('Start download')

log_area = st.empty()

def log(msg):
    log_area.text(msg)

# Keep the fetched-download UI visible across reruns by caching fetched streams
# If the user presses Start download, or we already have cached streams for the current URL,
# render the download controls.
show_download_ui = download_btn or (st.session_state.get('fetched_streams') and st.session_state.get('fetched_url') == url)

if download_btn:
    # mark that we should keep the UI visible for this URL
    st.session_state['fetched_url'] = url

if show_download_ui:
    if not url:
        st.error('Please provide a YouTube URL.')
    else:
        try:
            concurrency = st.number_input('Max concurrent downloads (playlist)', min_value=1, max_value=8, value=1)
            stream_logs = st.empty()
            overall_progress = None
            if is_playlist:
                st.info('Starting playlist download...')
                res_pref = None if resolution == 'Highest' else resolution

                urls = []
                # when concurrency ==1 we can show per-item live updates
                items = []
                # create placeholders
                status_box = st.container()

                downloaded = []

                if concurrency == 1:
                    # define callback to update status per item
                    total = None

                    def per_item_cb(title, status):
                        status_box.write(f"{title}: {status}")

                    results = download_playlist(url, output_folder, resolution_preference=res_pref,
                                                audio_only=(mode=='Audio'), convert_mp3=convert_mp3,
                                                concurrency=1, per_item_callback=per_item_cb)
                    st.success(f'Downloaded {len(results)} items to {output_folder}')
                    for r in results:
                        st.write(r)
                else:
                    st.warning('Parallel downloads enabled — live per-item streaming logs are limited. You will see a summary when done.')
                    # prepare placeholders in session_state for each playlist item (with progress bars)
                    from pytube import Playlist as PTPlaylist
                    playlist_obj = PTPlaylist(url)
                    urls = playlist_obj.video_urls
                    n = len(urls)
                    if 'playlist_items' not in st.session_state or len(st.session_state.get('playlist_items', [])) != n:
                        st.session_state['playlist_items'] = [
                            {'status': 'queued', 'progress': 0, 'text': f'Item {i+1}: queued'} for i in range(n)
                        ]

                    # render placeholders and progress bars
                    item_placeholders = []
                    for i in range(n):
                        container = status_box.container()
                        t = container.empty()
                        p = container.progress(0)
                        s = container.empty()
                        t.text(st.session_state['playlist_items'][i]['text'])
                        item_placeholders.append((t, p, s))

                    def per_item_cb(title, status, video_url_cb, index_cb, received, total, speed, eta):
                        try:
                            # update state
                            st.session_state['playlist_items'][index_cb]['status'] = status
                            st.session_state['playlist_items'][index_cb]['text'] = f"{title}: {status}"
                            if total and total > 0:
                                pct = int(received / total * 100)
                            else:
                                pct = 0
                            st.session_state['playlist_items'][index_cb]['progress'] = pct
                            # update UI widgets
                            t, p, s = item_placeholders[index_cb]
                            t.text(st.session_state['playlist_items'][index_cb]['text'])
                            p.progress(pct)
                            s.text(f"{received:,} / {total:,} bytes — {human_speed(speed)} — ETA {eta}s")
                        except Exception:
                            pass

                    try:
                        results = download_playlist(url, output_folder, resolution_preference=res_pref,
                                                    audio_only=(mode=='Audio'), convert_mp3=convert_mp3,
                                                    concurrency=concurrency, per_item_callback=per_item_cb)
                    except Exception as e:
                        st.error(f'Playlist error: {e}')
                        results = []
                    st.success(f'Downloaded {len(results)} items to {output_folder}')
                    for r in results:
                        st.write(r)
            else:
                st.info('Fetching video info...')
                # Try to reuse cached streams for the same URL to avoid disappearing UI after actions
                if st.session_state.get('fetched_url') == url and st.session_state.get('fetched_streams'):
                    streams = st.session_state['fetched_streams']
                else:
                    streams = get_video_streams(url)
                    st.session_state['fetched_streams'] = streams
                    st.session_state['fetched_url'] = url
                st.write(f"Title: {streams.get('title')}")

                # If get_video_streams returned a yt-dlp info dict, offer only yt-dlp download path
                if streams.get('backend') == 'yt-dlp':
                    st.info('Metadata fetched via yt-dlp (pytube failed). Use yt-dlp backend to download.')
                    if mode == 'Video':
                        if st.button('Download video now (yt-dlp)'):
                            # show live progress inline if user requested; otherwise run in background
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            def ytdlp_progress(fn, downloaded, total, speed, eta):
                                try:
                                    pct = int(downloaded / total * 100) if total and total > 0 else 0
                                    progress_bar.progress(min(pct, 100))
                                    status_text.text(f"{downloaded:,} / {total:,} bytes — {human_speed(speed)} — ETA {eta}s")
                                except Exception:
                                    pass

                            if show_live_progress:
                                # run inline and block UI while downloading so user sees live progress
                                try:
                                    fname = download_with_ytdlp(url, output_folder, audio_only=False, progress_callback=ytdlp_progress)
                                    st.session_state['last_download'] = fname
                                    st.success(f'Downloaded to: {fname}')
                                except Exception as e:
                                    st.error(f'YT-DLP download failed: {e}')
                            else:
                                import threading
                                # create a per-download progress file so other sessions can poll it
                                uid = str(uuid.uuid4())
                                pf = progress_file_for_id(output_folder, uid)

                                def _bg_download():
                                    try:
                                        fname = download_with_ytdlp(url, output_folder, audio_only=False, progress_callback=ytdlp_progress, progress_file=pf)
                                        # write final status
                                        try:
                                            write_progress = None
                                            from progress_store import write_progress_file
                                            write_progress_file(pf, {'status': 'completed', 'filename': fname})
                                        except Exception:
                                            pass
                                        st.session_state['last_download'] = fname
                                    except Exception as e:
                                        try:
                                            from progress_store import write_progress_file
                                            write_progress_file(pf, {'status': 'error', 'error': str(e)})
                                        except Exception:
                                            pass
                                        st.session_state['last_download_error'] = str(e)

                                threading.Thread(target=_bg_download, daemon=True).start()
                                st.info(f'Download started in background — progress file: {pf} (pollable)')
                    else:
                        # audio
                        if st.button('Download audio now (yt-dlp)'):
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            def ytdlp_progress(fn, downloaded, total, speed, eta):
                                try:
                                    pct = int(downloaded / total * 100) if total and total > 0 else 0
                                    progress_bar.progress(min(pct, 100))
                                    status_text.text(f"{downloaded:,} / {total:,} bytes — {human_speed(speed)} — ETA {eta}s")
                                except Exception:
                                    pass

                            if show_live_progress:
                                try:
                                    fname = download_with_ytdlp(url, output_folder, audio_only=True, convert_mp3=convert_mp3, progress_callback=ytdlp_progress)
                                    st.session_state['last_download'] = fname
                                    st.success(f'Downloaded to: {fname}')
                                except Exception as e:
                                    st.error(f'YT-DLP download failed: {e}')
                            else:
                                import threading

                                def _bg_download_audio():
                                    try:
                                        fname = download_with_ytdlp(url, output_folder, audio_only=True, convert_mp3=convert_mp3, progress_callback=ytdlp_progress)
                                        st.session_state['last_download'] = fname
                                    except Exception as e:
                                        st.session_state['last_download_error'] = str(e)

                                threading.Thread(target=_bg_download_audio, daemon=True).start()
                                st.info('Audio download started in background — check downloads folder and server logs.')
                else:
                    # original pytube-based path
                    if mode == 'Video':
                        # build list of available resolutions
                        options = []
                        seen = set()
                        for s in streams['progressive'] + streams['adaptive_video']:
                            res = s.resolution or 'unknown'
                            if res not in seen:
                                options.append(res)
                                seen.add(res)
                        options = ['Highest'] + options
                        chosen = st.selectbox('Choose resolution', options, index=0)

                        if st.button('Download video now'):
                            # pick stream
                            stream = None
                            if chosen == 'Highest':
                                if streams['progressive']:
                                    stream = streams['progressive'][0]
                                elif streams['adaptive_video']:
                                    stream = streams['adaptive_video'][0]
                            else:
                                for s in streams['progressive'] + streams['adaptive_video']:
                                    if s.resolution == chosen:
                                        stream = s
                                        break
                            if stream is None:
                                st.error('No matching stream found.')
                            else:
                                progress_bar = st.progress(0)
                                status_text = st.empty()

                                start_time = {'t': None}
                                def progress_cb(received, total):
                                    now = time.time()
                                    if start_time['t'] is None:
                                        start_time['t'] = now
                                    elapsed = max(now - start_time['t'], 1e-6)
                                    speed = received / elapsed
                                    eta = int((total - received) / speed) if speed > 0 else 0
                                    try:
                                        percent = int(received / total * 100)
                                        progress_bar.progress(min(percent, 100))
                                        status_text.text(f"{received:,} / {total:,} bytes ({percent}%) — {human_speed(speed)} — ETA {eta}s")
                                    except Exception:
                                        pass

                                with st.spinner('Downloading...'):
                                    if backend == 'yt-dlp':
                                            out = download_with_ytdlp(url, output_folder, audio_only=False, progress_callback=lambda f,r,t,s,e: progress_cb(r,t))
                                    elif backend == 'pytube then yt-dlp fallback':
                                            out = download_fallback(url, output_folder, audio_only=False, progress_callback=lambda f,r,t,s,e: progress_cb(r,t))
                                    else:
                                        out = download_video(stream, output_folder, progress_callback=progress_cb)
                                progress_bar.progress(100)
                                status_text.text('Completed')
                                st.success(f'Downloaded to: {out}')

                    # show active progress files for background downloads in the output folder
                    try:
                        pfs = list_progress_files(output_folder)
                        if pfs:
                            st.subheader('Background downloads')
                            for pf in pfs:
                                info = read_progress_file(pf)
                                title = info.get('filename') or info.get('title') or pf
                                status = info.get('status') or 'unknown'
                                downloaded = info.get('downloaded') or info.get('downloaded_bytes') or 0
                                total = info.get('total') or info.get('total_bytes') or 0
                                if total and total > 0:
                                    pct = int(downloaded / total * 100)
                                else:
                                    pct = 0
                                st.write(f"{title}: {status} — {downloaded:,}/{total:,} bytes ({pct}%)")
                                if status == 'completed':
                                    st.success(f"Completed: {info.get('filename')}")
                                if status == 'error':
                                    st.error(f"Error: {info.get('error')}")
                    except Exception:
                        pass

                    else:
                        # Audio mode
                        audios = streams['audio']
                        options = [s.abr for s in audios]
                        chosen = st.selectbox('Choose audio bitrate', options)

                        if st.button('Download audio now'):
                            stream = None
                            for s in audios:
                                if s.abr == chosen:
                                    stream = s
                                    break
                            if stream is None:
                                st.error('No matching audio stream found.')
                            else:
                                progress_bar = st.progress(0)
                                status_text = st.empty()

                                start_time = {'t': None}
                                def progress_cb(received, total):
                                    now = time.time()
                                    if start_time['t'] is None:
                                        start_time['t'] = now
                                    elapsed = max(now - start_time['t'], 1e-6)
                                    speed = received / elapsed
                                    eta = int((total - received) / speed) if speed > 0 else 0
                                    try:
                                        percent = int(received / total * 100)
                                        progress_bar.progress(min(percent, 100))
                                        status_text.text(f"{received:,} / {total:,} bytes ({percent}%) — {human_speed(speed)} — ETA {eta}s")
                                    except Exception:
                                        pass

                                with st.spinner('Downloading audio...'):
                                    if backend == 'yt-dlp':
                                        out = download_with_ytdlp(url, output_folder, audio_only=True, progress_callback=lambda f,r,t,s,e: progress_cb(r,t))
                                    elif backend == 'pytube then yt-dlp fallback':
                                        out = download_fallback(url, output_folder, audio_only=True, convert_mp3=convert_mp3, progress_callback=lambda f,r,t,s,e: progress_cb(r,t))
                                    else:
                                        out = download_audio(stream, output_folder, convert_mp3=convert_mp3, progress_callback=progress_cb)
                                progress_bar.progress(100)
                                status_text.text('Completed')
                                st.success(f'Downloaded to: {out}')

                
        except Exception as e:
            # show full traceback in the Streamlit UI to aid debugging (400 errors, etc.)
            st.exception(e)
