"""Streamlit-based YouTube Downloader — full-featured GUI application."""
import os
import time
import datetime
import logging
import platform
import subprocess
import streamlit as st

from pytube_helper import (
    get_video_streams, download_video, download_audio, download_playlist,
    PYDUB_AVAILABLE, is_ffmpeg_available, has_yt_dlp, download_fallback,
    download_with_ytdlp, extract_playlist_urls, extract_playlist_urls_with_titles,
    cleanup_part_files, YTDLP_AVAILABLE, extract_channel_videos,
    get_video_info,
)
from download_db import is_downloaded, record_download, get_history, clear_history
from download_queue import DownloadQueue, QueueItemStatus

logger = logging.getLogger(__name__)

# ─── Helper functions ───────────────────────────────────────────────────────

def human_size(b: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(b) < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} TB"


def _safe_getsize(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _open_folder(path: str) -> None:
    """Open a directory in the system file manager (cross-platform)."""
    abs_path = os.path.abspath(path)
    system = platform.system()
    if system == 'Windows':
        os.startfile(abs_path)
    elif system == 'Darwin':
        subprocess.Popen(['open', abs_path])
    else:
        subprocess.Popen(['xdg-open', abs_path])


def _reveal_file(path: str) -> None:
    """Reveal a file in the system file manager (cross-platform)."""
    abs_path = os.path.abspath(path)
    system = platform.system()
    if system == 'Windows':
        proc = subprocess.Popen(['explorer', f'/select,{abs_path}'])
    elif system == 'Darwin':
        proc = subprocess.Popen(['open', '-R', abs_path])
    else:
        proc = subprocess.Popen(['xdg-open', os.path.dirname(abs_path)])
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def human_speed(bps: float) -> str:
    if bps is None or bps == 0:
        return "0 B/s"
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if abs(bps) < 1024.0:
            return f"{bps:.1f} {unit}"
        bps /= 1024.0
    return f"{bps:.1f} TB/s"


def ensure_output_folder(folder: str) -> str:
    if not folder:
        folder = os.path.join(os.getcwd(), 'downloads')
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as e:
        logger.warning('Failed to create output folder %s: %s — falling back to cwd', folder, e)
        folder = os.getcwd()
    return folder


def safe_title(text: str) -> str:
    return "".join(c for c in text if c.isalnum() or c in ' ._-()[]').strip() or 'Download'


# ─── Page config ────────────────────────────────────────────────────────────

st.set_page_config(page_title="YouTube Downloader", page_icon="🎬", layout="wide")
st.title('🎬 YouTube Downloader')

# ─── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header('⚙️ Environment')
    c1, c2 = st.columns(2)
    with c1:
        if YTDLP_AVAILABLE:
            st.success('✅ yt-dlp')
        else:
            st.error('❌ yt-dlp')
    with c2:
        if is_ffmpeg_available():
            st.success('✅ ffmpeg')
        else:
            st.warning('⚠️ ffmpeg')
    st.caption('✅ pydub' if PYDUB_AVAILABLE else '⚠️ pydub missing')

    st.divider()
    st.header('📁 Output')
    output_folder = st.text_input('Output folder', value='')
    if not output_folder:
        output_folder = os.path.join(os.getcwd(), 'downloads')
    output_folder = ensure_output_folder(output_folder)
    st.caption(f'📂 {output_folder}')

    st.divider()
    st.header('⚡ Global options')
    g_audio_only = st.checkbox('🎵 Audio only', value=False, key='g_audio')
    g_convert_mp3 = st.checkbox('🎶 Convert MP3', value=False, key='g_mp3')
    g_subtitles = st.checkbox('📝 Download subtitles', value=False, key='g_subs')
    g_sub_lang = st.text_input('Subtitle languages', value='en,ko', key='g_sublang',
                               help='Comma-separated: en,ko,ja')
    _res_options = ['best', '2160p (4K)', '1440p', '1080p', '720p', '480p', '360p']
    g_resolution_label = st.selectbox('🎞 해상도', _res_options, index=0, key='g_res')
    g_resolution = None if g_resolution_label == 'best' else g_resolution_label.split()[0]
    g_rate_limit = st.number_input('⏱ Speed limit (KB/s, 0=∞)', min_value=0, max_value=100000,
                                   value=0, key='g_rate')
    g_skip_dup = st.checkbox('🚫 Skip duplicates', value=True, key='g_dup')
    g_concurrency = st.number_input('Concurrency', min_value=1, max_value=8, value=3, key='g_conc')
    g_use_cookies = st.checkbox('🍪 Chrome 쿠키 사용 (403 우회)', value=False, key='g_cookies',
                                help='Chrome에 YouTube 로그인되어 있어야 합니다.')
    g_cookies_browser = 'chrome' if g_use_cookies else None

    # 쿠키 파일 업로드 (cookies.txt)
    g_cookie_file_upload = st.file_uploader('🍪 쿠키 파일 업로드 (cookies.txt)',
                                            type=['txt'], key='g_cookiefile',
                                            help='yt-dlp --cookies 또는 브라우저 확장으로 내보낸 Netscape 형식')
    if g_cookie_file_upload is not None:
        _cookie_save_path = os.path.join(output_folder, '.uploaded_cookies.txt')
        _MAX_COOKIE_SIZE = 5 * 1024 * 1024  # 5MB
        if g_cookie_file_upload.size > _MAX_COOKIE_SIZE:
            st.error(f'❌ 쿠키 파일이 너무 큽니다 (최대 5MB, 현재 {g_cookie_file_upload.size // 1024}KB)')
        else:
            _prev = st.session_state.get('g_cookiefile_path')
            if _prev and os.path.isfile(_prev):
                st.info(f'ℹ️ 기존 쿠키 파일을 교체합니다: `{os.path.basename(_prev)}`')
            try:
                with open(_cookie_save_path, 'wb') as _cf:
                    _cf.write(g_cookie_file_upload.read())
                st.session_state['g_cookiefile_path'] = _cookie_save_path
                st.caption(f'✅ 쿠키 파일 저장됨')
            except OSError as _e:
                st.error(f'❌ 쿠키 파일 저장 실패: {_e}')
                logger.exception('Failed to save uploaded cookie file')
    g_cookiefile = st.session_state.get('g_cookiefile_path')
    if g_cookiefile and not os.path.isfile(g_cookiefile):
        st.session_state.pop('g_cookiefile_path', None)
        g_cookiefile = None
    if g_cookiefile and g_cookie_file_upload is None:
        st.caption(f'📄 쿠키 파일 유지 중: `{os.path.basename(g_cookiefile)}`')

    # 프록시 설정
    g_proxy_raw = st.text_input('🌐 프록시 (비워두면 미사용)', value='', key='g_proxy',
                                placeholder='http://user:pass@host:port  또는  socks5://127.0.0.1:1080',
                                help='지역 제한 영상 우회. HTTP/HTTPS/SOCKS4/SOCKS5 지원')
    g_proxy = g_proxy_raw.strip() or None

    st.divider()
    _tmpl_presets = {
        '제목만 (기본)': '%(title)s',
        '날짜_제목': '%(upload_date)s_%(title)s',
        '채널_제목': '%(uploader)s_%(title)s',
        '재생목록순서_제목': '%(playlist_index)02d_%(title)s',
        '직접 입력': '__custom__',
    }
    _tmpl_label = st.selectbox('📝 파일명 템플릿', list(_tmpl_presets.keys()), key='g_tmpl_preset')
    if _tmpl_presets[_tmpl_label] == '__custom__':
        g_filename_template = st.text_input('커스텀 템플릿', value='%(title)s', key='g_tmpl_custom',
                                            help='yt-dlp 필드 사용 가능: %(title)s, %(uploader)s, %(upload_date)s, %(id)s ...')
    else:
        g_filename_template = _tmpl_presets[_tmpl_label]
        st.caption(f'`{g_filename_template}`')

    st.divider()
    col_clean, col_open = st.columns(2)
    with col_clean:
        if st.button('🧹 .part 정리'):
            n = cleanup_part_files(output_folder)
            st.success(f'Removed {n}') if n else st.info('None found')
    with col_open:
        if st.button('📂 폴더 열기'):
            _open_folder(output_folder)

    st.divider()
    st.header('📜 History')
    hist = get_history(output_folder, limit=10)
    if hist:
        for hi, h in enumerate(hist):
            filepath = h.get('filepath', '')
            col_h, col_btn = st.columns([5, 1])
            with col_h:
                icon = '✅' if filepath and os.path.isfile(filepath) else '📥'
                st.caption(f"{icon} {h.get('title', '?')[:35]}")
            with col_btn:
                if filepath and os.path.isfile(filepath):
                    if st.button('📂', key=f"hist_{hi}_{h.get('url','')[-8:]}",
                                 help='파일 열기'):
                        _reveal_file(filepath)
        if st.button('Clear all history'):
            clear_history(output_folder)
            st.rerun()
    else:
        st.caption('No history yet.')

# ─── Subtitle helper ────────────────────────────────────────────────────────

def _get_sub_langs():
    if g_subtitles:
        return [l.strip() for l in g_sub_lang.split(',') if l.strip()]
    return None

# ─── Initialize queue ───────────────────────────────────────────────────────

def _get_queue() -> DownloadQueue:
    """Get or create the shared queue instance."""
    if 'dl_queue' not in st.session_state:
        q = DownloadQueue(persist_path=os.path.join(output_folder, '.queue.json'))

        def _do_download(item, progress_cb):
            import yt_dlp as _yt_dlp
            _tmpl = item.filename_template or '%(title)s'
            ydl_opts = {
                'outtmpl': os.path.join(item.output_folder, f'{_tmpl}.%(ext)s'),
                'quiet': True, 'no_warnings': True,
                'progress_hooks': [lambda d: progress_cb(
                    int(d.get('downloaded_bytes', 0) / max(d.get('total_bytes') or d.get('total_bytes_estimate') or 1, 1) * 100)
                ) if d.get('status') == 'downloading' else None],
            }
            if item.audio_only:
                ydl_opts['format'] = 'bestaudio/best'
                if item.convert_mp3:
                    ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
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
            if item.rate_limit > 0:
                ydl_opts['ratelimit'] = item.rate_limit * 1024
            if item.proxy:
                ydl_opts['proxy'] = item.proxy
            if item.cookiefile and os.path.isfile(item.cookiefile):
                ydl_opts['cookiefile'] = item.cookiefile
            if item.cookies_from_browser:
                ydl_opts['cookiesfrombrowser'] = (item.cookies_from_browser,)

            os.makedirs(item.output_folder, exist_ok=True)
            with _yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(item.url, download=True)
                if 'requested_downloads' in info and info['requested_downloads']:
                    fp = info['requested_downloads'][0].get('filepath', '')
                else:
                    fp = ydl.prepare_filename(info)
            record_download(item.url, item.output_folder, fp,
                            title=info.get('title', ''),
                            size=_safe_getsize(fp))
            return fp

        q.set_download_function(_do_download)
        q.start_worker()
        st.session_state['dl_queue'] = q
    return st.session_state['dl_queue']


queue = _get_queue()

# ─── Tabs ───────────────────────────────────────────────────────────────────

tab_single, tab_playlist, tab_channel, tab_batch, tab_queue, tab_schedule, tab_api = st.tabs([
    '🎬 Single', '📋 Playlist', '📺 Channel', '📝 Batch', '📦 Queue', '⏰ Schedule', '🔌 API'
])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: Single Video
# ═══════════════════════════════════════════════════════════════════════════

with tab_single:
    st.subheader('🎬 Single Video Download')
    # 클립보드에서 YouTube URL 자동 감지
    st.components.v1.html("""
    <script>
    async function checkClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            if (text && (text.includes('youtube.com/watch') || text.includes('youtu.be/'))) {
                const inputs = window.parent.document.querySelectorAll('input[data-testid]');
                inputs.forEach(inp => {
                    if (inp.value === '' && inp.placeholder && inp.placeholder.includes('youtube.com')) {
                        inp.value = text;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                });
            }
        } catch(e) {}
    }
    checkClipboard();
    </script>
    """, height=0)
    url_single = st.text_input('YouTube URL', placeholder='https://www.youtube.com/watch?v=...', key='url_single')

    if url_single:
        # 썸네일 + 메타데이터 자동 미리보기
        prev_key = 's_preview'
        if st.session_state.get(prev_key + '_url') != url_single:
            with st.spinner('🔍 미리보기 로딩...'):
                preview = get_video_info(url_single)
            st.session_state[prev_key] = preview
            st.session_state[prev_key + '_url'] = url_single
        else:
            preview = st.session_state.get(prev_key, {})

        if preview:
            col_thumb, col_meta = st.columns([2, 3])
            with col_thumb:
                if preview.get('thumbnail'):
                    st.image(preview['thumbnail'], use_container_width=True)
            with col_meta:
                st.markdown(f"**{preview.get('title', '?')}**")
                st.caption(f"📺 {preview.get('channel', '?')}")
                st.caption(f"⏱ {preview.get('duration_str', '?')}")
                if preview.get('upload_date'):
                    d = preview['upload_date']
                    st.caption(f"📅 {d[:4]}-{d[4:6]}-{d[6:8]}")
                if preview.get('filesize_approx'):
                    st.caption(f"💾 ~{human_size(preview['filesize_approx'])}")
            st.divider()
        # Duplicate check
        if g_skip_dup:
            _mode = 'audio' if (g_audio_only or g_convert_mp3) else 'video'
            dup = is_downloaded(url_single, output_folder, mode=_mode)
            if dup:
                st.warning(f'⚠️ Already downloaded: **{dup.get("title", "?")}** → `{dup.get("filepath", "?")}`')
                st.caption('Uncheck "Skip duplicates" in sidebar to re-download.')

        if st.button('🔍 Fetch info', key='fetch_single', type='primary'):
            with st.spinner('Fetching...'):
                streams = get_video_streams(url_single)
                st.session_state['s_streams'] = streams
                st.session_state['s_fetched_url'] = url_single

        if st.session_state.get('s_fetched_url') == url_single and st.session_state.get('s_streams'):
            streams = st.session_state['s_streams']
            title = streams.get('title', 'Unknown')
            st.info(f'**{title}** (via {streams.get("backend", "?")})')

            if st.button('⬇️ Download', key='dl_single', type='primary'):
                # Check duplicate
                if g_skip_dup and is_downloaded(url_single, output_folder, mode='audio' if (g_audio_only or g_convert_mp3) else 'video'):
                    st.warning('Already downloaded. Skipping.')
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def _ytdlp_progress(fn, downloaded, total, speed, eta):
                        try:
                            pct = int(downloaded / total * 100) if total > 0 else 0
                            progress_bar.progress(min(pct, 100))
                            status_text.text(f"{human_size(downloaded)}/{human_size(total)} — {human_speed(speed or 0)}")
                        except Exception as e:
                            logger.debug('Progress UI update failed: %s', e)

                    with st.spinner('Downloading...'):
                        try:
                            fname = download_with_ytdlp(
                                url_single, output_folder,
                                audio_only=g_audio_only, convert_mp3=g_convert_mp3,
                                progress_callback=_ytdlp_progress,
                                subtitle_langs=_get_sub_langs(),
                                rate_limit_kbps=g_rate_limit,
                                cookies_from_browser=g_cookies_browser,
                                resolution=g_resolution,
                                filename_template=g_filename_template,
                                proxy=g_proxy,
                                cookiefile=g_cookiefile,
                            )
                            progress_bar.progress(100)
                            status_text.text('✅ Complete')
                            st.success(f'Downloaded: `{fname}`')
                            # 완료 알림
                            _done_title = preview.get('title', fname) if preview else fname
                            st.toast(f'✅ 다운로드 완료: {_done_title[:50]}', icon='🎬')
                            st.components.v1.html(f"""
                            <script>
                            (function(){{
                                const msg = {repr(_done_title[:80])};
                                if (Notification && Notification.permission === 'granted') {{
                                    new Notification('✅ 다운로드 완료', {{ body: msg }});
                                }} else if (Notification && Notification.permission !== 'denied') {{
                                    Notification.requestPermission().then(p => {{
                                        if (p === 'granted') new Notification('✅ 다운로드 완료', {{ body: msg }});
                                    }});
                                }}
                            }})();
                            </script>
                            """, height=0)
                            if st.button('📂 파일 열기', key='open_single'):
                                _reveal_file(fname)
                            record_download(url_single, output_folder, fname, title=title,
                                            size=_safe_getsize(fname),
                                            mode='audio' if (g_audio_only or g_convert_mp3) else 'video')
                        except Exception as e:
                            st.error(f'❌ {e}')

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: Playlist
# ═══════════════════════════════════════════════════════════════════════════

with tab_playlist:
    st.subheader('📋 Playlist Download')
    url_pl = st.text_input('Playlist URL', placeholder='https://www.youtube.com/playlist?list=...', key='url_pl')
    max_items_pl = st.number_input('Max items (0 = all)', 0, 500, 0, key='pl_max')

    if url_pl:
        cache_key = 'pl_cache'
        if st.session_state.get(cache_key + '_url') != url_pl:
            with st.spinner('🔍 Fetching playlist...'):
                try:
                    result = extract_playlist_urls_with_titles(url_pl)
                    st.session_state['pl_data'] = result
                    st.session_state[cache_key + '_url'] = url_pl
                except Exception as e:
                    st.error(f'❌ {e}')
                    st.session_state['pl_data'] = {'playlist_title': 'Playlist', 'items': []}
                    st.session_state[cache_key + '_url'] = url_pl

        data = st.session_state.get('pl_data', {})
        pl_title = data.get('playlist_title', 'Playlist')
        items = data.get('items', [])

        if items:
            st.success(f'✅ **{pl_title}** — {len(items)} items')
            with st.expander(f'📜 Items ({len(items)})', expanded=False):
                for i, it in enumerate(items, 1):
                    st.caption(f"{i}. {it.get('title', '?')}")

            if st.button('🔄 Refresh', key='pl_refresh'):
                st.session_state[cache_key + '_url'] = None
                st.rerun()

            pl_folder = os.path.join(output_folder, safe_title(pl_title))
            os.makedirs(pl_folder, exist_ok=True)

            effective = min(max_items_pl, len(items)) if max_items_pl > 0 else len(items)
            st.info(f'📂 `{safe_title(pl_title)}/` | {effective} items | Concurrency: {g_concurrency}')

            if st.button('🚀 Start playlist download', key='pl_dl', type='primary'):
                progress_bar = st.progress(0)
                status_text = st.empty()
                log = []
                done = {'ok': 0, 'err': 0}
                failed_urls_pl = []

                def _pl_cb(title, status, video_url, idx):
                    short = (title or video_url or '?')[:60]
                    if 'completed' in str(status):
                        done['ok'] += 1
                        log.append(f"✅ {short}")
                    elif 'error' in str(status):
                        done['err'] += 1
                        log.append(f"❌ {short}: {status}")
                        if video_url:
                            failed_urls_pl.append(video_url)
                    else:
                        log.append(f"⏳ {short}")
                    total = done['ok'] + done['err']
                    try:
                        progress_bar.progress(min(int(total / effective * 100), 100))
                        status_text.text(f"{total}/{effective} | ✅{done['ok']} ❌{done['err']}")
                    except Exception as e:
                        logger.debug('Playlist progress UI update failed: %s', e)

                with st.spinner(f'Downloading {effective} items...'):
                    try:
                        results = download_playlist(
                            url_pl, pl_folder,
                            audio_only=g_audio_only, convert_mp3=g_convert_mp3,
                            concurrency=g_concurrency,
                            max_items=max_items_pl if max_items_pl > 0 else None,
                            per_item_callback=_pl_cb, prefer_ytdlp=True,
                            subtitle_langs=_get_sub_langs(),
                            rate_limit_kbps=g_rate_limit,
                            cookies_from_browser=g_cookies_browser,
                            skip_duplicates=g_skip_dup,
                            resolution_preference=g_resolution,
                            filename_template=g_filename_template,
                            proxy=g_proxy,
                            cookiefile=g_cookiefile,
                        )
                    except Exception as e:
                        st.error(f'❌ {e}')
                        results = []

                progress_bar.progress(100)
                st.success(f'🎉 Done! {len(results)}/{effective} downloaded to `{pl_folder}`')
                st.toast(f'🎉 플레이리스트 완료: {len(results)}/{effective}개', icon='✅')
                if done['err'] > 0:
                    st.warning(f'⚠️ {done["err"]} failed')
                    if failed_urls_pl:
                        st.session_state['pl_failed_urls'] = failed_urls_pl
                if st.session_state.get('pl_failed_urls'):
                    failed_list = st.session_state['pl_failed_urls']
                    if st.button(f'🔁 실패한 {len(failed_list)}개 재시도', key='pl_retry'):
                        st.session_state['pl_failed_urls'] = None
                        retry_done = {'ok': 0, 'err': 0}
                        retry_log = []
                        for ru in failed_list:
                            try:
                                download_with_ytdlp(ru, pl_folder, audio_only=g_audio_only,
                                                    convert_mp3=g_convert_mp3, subtitle_langs=_get_sub_langs(),
                                                    rate_limit_kbps=g_rate_limit, cookies_from_browser=g_cookies_browser,
                                                    resolution=g_resolution, proxy=g_proxy, cookiefile=g_cookiefile)
                                retry_done['ok'] += 1
                                retry_log.append(f'✅ {ru[:60]}')
                            except Exception as re:
                                retry_done['err'] += 1
                                retry_log.append(f'❌ {ru[:60]}: {re}')
                        st.success(f'재시도 완료: ✅{retry_done["ok"]} ❌{retry_done["err"]}')
                        with st.expander('재시도 로그'):
                            for e in retry_log:
                                st.caption(e)
                with st.expander('📋 Log', expanded=True):
                    for entry in log:
                        st.caption(entry)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: Channel
# ═══════════════════════════════════════════════════════════════════════════

with tab_channel:
    st.subheader('📺 Channel Download')
    st.caption('Download all videos from a YouTube channel.')
    url_ch = st.text_input('Channel URL', placeholder='https://www.youtube.com/@ChannelName', key='url_ch')
    max_ch = st.number_input('Max videos (0 = all)', 0, 5000, 0, key='ch_max')

    if url_ch:
        ch_cache = 'ch_cache'
        if st.session_state.get(ch_cache + '_url') != url_ch:
            with st.spinner('🔍 Fetching channel videos...'):
                try:
                    ch_result = extract_channel_videos(url_ch, max_items=max_ch or None)
                    st.session_state['ch_data'] = ch_result
                    st.session_state[ch_cache + '_url'] = url_ch
                except Exception as e:
                    st.error(f'❌ {e}')
                    st.session_state['ch_data'] = {'channel_title': 'Channel', 'items': []}
                    st.session_state[ch_cache + '_url'] = url_ch

        ch_data = st.session_state.get('ch_data', {})
        ch_title = ch_data.get('channel_title', 'Channel')
        ch_items = ch_data.get('items', [])

        if ch_items:
            st.success(f'✅ **{ch_title}** — {len(ch_items)} videos')
            with st.expander(f'📜 Videos ({len(ch_items)})', expanded=False):
                for i, it in enumerate(ch_items[:100], 1):
                    st.caption(f"{i}. {it.get('title', '?')}")
                if len(ch_items) > 100:
                    st.caption(f'... and {len(ch_items) - 100} more')

            if st.button('🔄 Refresh', key='ch_refresh'):
                st.session_state[ch_cache + '_url'] = None
                st.rerun()

            ch_folder = os.path.join(output_folder, safe_title(ch_title))
            os.makedirs(ch_folder, exist_ok=True)
            st.info(f'📂 `{safe_title(ch_title)}/` | {len(ch_items)} videos')

            if st.button('🚀 Start channel download', key='ch_dl', type='primary'):
                progress_bar = st.progress(0)
                status_text = st.empty()
                log = []
                done = {'ok': 0, 'err': 0}
                total_ch = len(ch_items)
                failed_urls_ch = []

                def _ch_cb(title, status, video_url, idx):
                    short = (title or video_url or '?')[:60]
                    if 'completed' in str(status):
                        done['ok'] += 1
                        log.append(f"✅ {short}")
                    elif 'error' in str(status):
                        done['err'] += 1
                        log.append(f"❌ {short}")
                        if video_url:
                            failed_urls_ch.append(video_url)
                    processed = done['ok'] + done['err']
                    try:
                        progress_bar.progress(min(int(processed / total_ch * 100), 100))
                        status_text.text(f"{processed}/{total_ch} | ✅{done['ok']} ❌{done['err']}")
                    except Exception as e:
                        logger.debug('Channel progress UI update failed: %s', e)

                # Use pre-fetched URLs to avoid re-extracting the entire channel
                urls_list = [it['url'] for it in ch_items if it.get('url')]

                with st.spinner(f'Downloading {total_ch} videos...'):
                    try:
                        results = download_playlist(
                            url_ch, ch_folder,
                            preset_urls=urls_list,
                            audio_only=g_audio_only, convert_mp3=g_convert_mp3,
                            concurrency=g_concurrency,
                            max_items=max_ch if max_ch > 0 else None,
                            per_item_callback=_ch_cb, prefer_ytdlp=True,
                            subtitle_langs=_get_sub_langs(),
                            rate_limit_kbps=g_rate_limit,
                            cookies_from_browser=g_cookies_browser,
                            skip_duplicates=g_skip_dup,
                            resolution_preference=g_resolution,
                            filename_template=g_filename_template,
                            proxy=g_proxy,
                            cookiefile=g_cookiefile,
                        )
                    except Exception as e:
                        st.error(f'❌ {e}')
                        results = []

                progress_bar.progress(100)
                st.success(f'🎉 Done! {len(results)}/{total_ch} downloaded')
                st.toast(f'🎉 채널 다운로드 완료: {len(results)}/{total_ch}개', icon='✅')
                if done['err'] > 0:
                    st.warning(f'⚠️ {done["err"]} failed')
                    if failed_urls_ch:
                        st.session_state['ch_failed_urls'] = failed_urls_ch
                if st.session_state.get('ch_failed_urls'):
                    failed_ch_list = st.session_state['ch_failed_urls']
                    if st.button(f'🔁 실패한 {len(failed_ch_list)}개 재시도', key='ch_retry'):
                        st.session_state['ch_failed_urls'] = None
                        for ru in failed_ch_list:
                            try:
                                download_with_ytdlp(ru, ch_folder, audio_only=g_audio_only,
                                                    convert_mp3=g_convert_mp3, subtitle_langs=_get_sub_langs(),
                                                    rate_limit_kbps=g_rate_limit, cookies_from_browser=g_cookies_browser,
                                                    resolution=g_resolution, proxy=g_proxy, cookiefile=g_cookiefile)
                            except Exception as e:
                                logger.warning('Retry download failed for %s: %s', ru, e)
                        st.success('재시도 완료!')
                with st.expander('📋 Log', expanded=True):
                    for entry in log:
                        st.caption(entry)
        else:
            st.warning('No videos found.')

# ═══════════════════════════════════════════════════════════════════════════
# TAB 4: Batch
# ═══════════════════════════════════════════════════════════════════════════

with tab_batch:
    st.subheader('📝 Batch Download')
    st.caption('Paste multiple YouTube URLs (one per line) or upload a .txt file.')

    upload = st.file_uploader('Upload URL list (.txt)', type=['txt'], key='batch_upload')
    batch_text = st.text_area(
        'Or paste URLs here (one per line)',
        height=200,
        placeholder='https://www.youtube.com/watch?v=xxx\nhttps://www.youtube.com/watch?v=yyy\n...',
        key='batch_text',
    )

    # Combine sources
    urls_raw = ''
    if upload:
        urls_raw = upload.read().decode('utf-8', errors='ignore')
    if batch_text:
        urls_raw = batch_text

    urls_list = [u.strip() for u in urls_raw.splitlines() if u.strip() and ('youtube.com' in u or 'youtu.be' in u)]

    if urls_list:
        st.info(f'Found **{len(urls_list)}** valid URLs')

        # Deduplicate check
        if g_skip_dup:
            new_urls = []
            dup_count = 0
            for u in urls_list:
                if is_downloaded(u, output_folder, mode='audio' if (g_audio_only or g_convert_mp3) else 'video'):
                    dup_count += 1
                else:
                    new_urls.append(u)
            if dup_count > 0:
                st.warning(f'⚠️ {dup_count} URLs already downloaded (will be skipped)')
            urls_list = new_urls
            st.info(f'**{len(urls_list)}** new URLs to download')

        batch_mode = st.radio('Batch mode', ['Add to queue', 'Download immediately'], horizontal=True, key='batch_mode')

        if st.button('🚀 Start batch', key='batch_start', type='primary') and urls_list:
            if batch_mode == 'Add to queue':
                items = queue.add_batch(
                    urls=urls_list, output_folder=output_folder,
                    audio_only=g_audio_only, convert_mp3=g_convert_mp3,
                    subtitles=g_subtitles, subtitle_lang=g_sub_lang,
                    rate_limit=g_rate_limit,
                    proxy=g_proxy or '', cookiefile=g_cookiefile or '',
                    cookies_from_browser=g_cookies_browser or '',
                    resolution=g_resolution or '',
                    filename_template=g_filename_template,
                )
                st.success(f'✅ Added {len(items)} items to queue!')
                st.info('Go to the **Queue** tab to monitor progress.')
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                log = []
                total = len(urls_list)
                done_count = {'ok': 0, 'err': 0}

                for i, url_b in enumerate(urls_list):
                    try:
                        status_text.text(f'({i+1}/{total}) {url_b[:60]}...')
                        fname = download_with_ytdlp(
                            url_b, output_folder,
                            audio_only=g_audio_only, convert_mp3=g_convert_mp3,
                            subtitle_langs=_get_sub_langs(),
                            rate_limit_kbps=g_rate_limit,
                            cookies_from_browser=g_cookies_browser,
                            resolution=g_resolution,
                            filename_template=g_filename_template,
                            proxy=g_proxy,
                            cookiefile=g_cookiefile,
                        )
                        done_count['ok'] += 1
                        log.append(f'✅ {url_b[:50]}')
                        record_download(url_b, output_folder, fname, mode='audio' if (g_audio_only or g_convert_mp3) else 'video')
                    except Exception as e:
                        done_count['err'] += 1
                        log.append(f'❌ {url_b[:50]}: {e}')
                    progress_bar.progress(min(int((i + 1) / total * 100), 100))

                progress_bar.progress(100)
                st.success(f'🎉 Batch complete! ✅{done_count["ok"]} ❌{done_count["err"]}')
                with st.expander('📋 Log', expanded=True):
                    for entry in log:
                        st.caption(entry)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 5: Queue
# ═══════════════════════════════════════════════════════════════════════════

with tab_queue:
    st.subheader('📦 Download Queue')

    q_items = queue.get_all()

    if q_items:
        # Summary
        pending = sum(1 for i in q_items if i.status == QueueItemStatus.PENDING)
        active = sum(1 for i in q_items if i.status == QueueItemStatus.DOWNLOADING)
        completed = sum(1 for i in q_items if i.status == QueueItemStatus.COMPLETED)
        failed = sum(1 for i in q_items if i.status == QueueItemStatus.FAILED)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric('⏳ Pending', pending)
        c2.metric('⬇️ Active', active)
        c3.metric('✅ Done', completed)
        c4.metric('❌ Failed', failed)

        st.divider()

        for item in q_items:
            icon = {'pending': '⏳', 'downloading': '⬇️', 'completed': '✅',
                    'failed': '❌', 'cancelled': '🚫', 'scheduled': '⏰'}.get(item.status, '❓')

            with st.container():
                col_a, col_b, col_c = st.columns([5, 2, 1])
                with col_a:
                    st.markdown(f'{icon} **{(item.title or item.url)[:60]}**')
                    if item.status == QueueItemStatus.DOWNLOADING:
                        st.progress(item.progress)
                    elif item.status == QueueItemStatus.FAILED:
                        st.caption(f'Error: {item.error[:80]}')
                    elif item.status == QueueItemStatus.COMPLETED:
                        st.caption(f'📁 {item.filepath}')
                    elif item.status == QueueItemStatus.SCHEDULED:
                        sched = datetime.datetime.fromtimestamp(item.scheduled_time)
                        st.caption(f'Scheduled: {sched.strftime("%Y-%m-%d %H:%M")}')
                with col_b:
                    st.caption(item.status)
                with col_c:
                    if item.status in (QueueItemStatus.PENDING, QueueItemStatus.SCHEDULED):
                        if st.button('❌', key=f'cancel_{item.id}'):
                            queue.cancel(item.id)
                            st.rerun()
                st.divider()

        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            if st.button('🗑 Clear completed', key='q_clear'):
                n = queue.clear_completed()
                st.success(f'Removed {n} items')
                st.rerun()
        with bc2:
            if st.button('🔄 Refresh', key='q_refresh'):
                st.rerun()
        with bc3:
            st.caption(f'Auto-refresh: Ctrl+R')
    else:
        st.info('Queue is empty. Add items from other tabs.')

# ═══════════════════════════════════════════════════════════════════════════
# TAB 6: Schedule
# ═══════════════════════════════════════════════════════════════════════════

with tab_schedule:
    st.subheader('⏰ Scheduled Downloads')
    st.caption('지정한 시각에 자동으로 다운로드를 시작합니다. 앱이 실행 중이어야 동작합니다.')

    # 현재 사이드바 설정 안내
    _sched_hints = []
    if g_proxy:
        _sched_hints.append(f'🌐 프록시: `{g_proxy}`')
    if g_cookiefile and os.path.isfile(g_cookiefile):
        _sched_hints.append(f'🍪 쿠키 파일: `{os.path.basename(g_cookiefile)}`')
    if g_resolution:
        _sched_hints.append(f'🎞 해상도: `{g_resolution}`')
    if g_audio_only:
        _sched_hints.append('🎵 Audio only')
    if _sched_hints:
        st.info('현재 사이드바 설정 적용됨: ' + ' · '.join(_sched_hints))

    url_sched = st.text_input('YouTube URL', key='sched_url',
                              placeholder='https://www.youtube.com/watch?v=...')

    sc1, sc2 = st.columns(2)
    with sc1:
        sched_date = st.date_input('Date', key='sched_date')
    with sc2:
        sched_time_val = st.time_input('Time', key='sched_time', value=datetime.time(23, 0))

    if url_sched:
        sched_dt = datetime.datetime.combine(sched_date, sched_time_val)
        sched_ts = sched_dt.timestamp()
        now_ts = time.time()

        if sched_ts <= now_ts:
            st.warning('⚠️ 설정한 시각이 이미 지났습니다. 즉시 시작됩니다.')
        else:
            remaining = int(sched_ts - now_ts)
            h, m = remaining // 3600, (remaining % 3600) // 60
            st.info(f'📅 예약 시각: **{sched_dt.strftime("%Y-%m-%d %H:%M")}** (약 {h}시간 {m}분 후)')

        if st.button('⏰ Schedule download', key='sched_go', type='primary'):
            item = queue.add(
                url=url_sched, output_folder=output_folder,
                audio_only=g_audio_only, convert_mp3=g_convert_mp3,
                subtitles=g_subtitles, subtitle_lang=g_sub_lang,
                rate_limit=g_rate_limit,
                scheduled_time=sched_ts,
                proxy=g_proxy or '', cookiefile=g_cookiefile or '',
                cookies_from_browser=g_cookies_browser or '',
                resolution=g_resolution or '',
                filename_template=g_filename_template,
            )
            st.success(f'✅ 예약 완료! ID: `{item.id}` — {sched_dt.strftime("%Y-%m-%d %H:%M")} 시작 예정')
            st.info('**Queue** 탭에서 예약 항목을 확인할 수 있습니다.')

    # Show existing scheduled items
    st.divider()
    scheduled = [i for i in queue.get_all() if i.status == QueueItemStatus.SCHEDULED]
    if scheduled:
        st.markdown(f'**{len(scheduled)}개 예약됨:**')
        for item in scheduled:
            sched_t = datetime.datetime.fromtimestamp(item.scheduled_time)
            remaining_s = int(item.scheduled_time - time.time())
            remain_str = f'{remaining_s//3600}h {(remaining_s%3600)//60}m 후' if remaining_s > 0 else '곧 시작'
            col_s, col_cancel = st.columns([5, 1])
            with col_s:
                st.caption(f'⏰ {sched_t.strftime("%Y-%m-%d %H:%M")} ({remain_str}) — {item.url[:55]}')
            with col_cancel:
                if st.button('✖', key=f'sched_cancel_{item.id}', help='예약 취소'):
                    queue.cancel(item.id)
                    st.rerun()
    else:
        st.caption('예약된 다운로드가 없습니다.')

# ═══════════════════════════════════════════════════════════════════════════
# TAB 7: API
# ═══════════════════════════════════════════════════════════════════════════

with tab_api:
    st.subheader('🔌 REST API')
    st.caption('Run the API server separately for programmatic access.')

    st.markdown('''
### Quick start
```bash
# Start the API server (separate terminal)
python api_server.py --port 8000
```

### Available endpoints

| Method | Endpoint | Description |
|--------|---------|-------------|
| `GET` | `/api/status` | System & environment status |
| `POST` | `/api/download` | Download a single video |
| `POST` | `/api/batch` | Batch download multiple URLs |
| `POST` | `/api/playlist` | Download a playlist |
| `POST` | `/api/channel` | Download all channel videos |
| `POST` | `/api/schedule` | Schedule a download |
| `GET` | `/api/queue` | List queue items |
| `GET` | `/api/queue/{id}` | Get queue item details |
| `DELETE` | `/api/queue/{id}` | Remove from queue |
| `POST` | `/api/queue/{id}/cancel` | Cancel pending item |
| `DELETE` | `/api/queue` | Clear completed items |
| `GET` | `/api/history` | Download history |
| `DELETE` | `/api/history` | Clear history |
| `GET` | `/api/info?url=...` | Get video info |
| `GET` | `/api/playlist/info?url=...` | Get playlist info |

### Example: cURL
```bash
# Download a video
curl -X POST http://localhost:8000/api/download \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "audio_only": true}'

# Batch download
curl -X POST http://localhost:8000/api/batch \\
  -H "Content-Type: application/json" \\
  -d '{"urls": ["https://youtube.com/watch?v=xxx", "https://youtube.com/watch?v=yyy"]}'

# Schedule a download
curl -X POST http://localhost:8000/api/schedule \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://youtube.com/watch?v=xxx", "scheduled_time": "2026-02-08T03:00:00"}'
```

### Interactive docs
Once the API server is running, visit:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
''')

# ─── Footer ─────────────────────────────────────────────────────────────────

st.divider()
with st.expander('📂 Files in output folder'):
    try:
        all_entries = []
        for root, dirs, files in os.walk(output_folder):
            # Skip hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.startswith('.') or f.endswith('.part'):
                    continue
                fpath = os.path.join(root, f)
                rel = os.path.relpath(fpath, output_folder)
                size = _safe_getsize(fpath)
                all_entries.append((rel, size))

        if all_entries:
            for rel, size in sorted(all_entries)[:80]:
                st.caption(f"📄 {rel} ({human_size(size)})")
            if len(all_entries) > 80:
                st.caption(f'... and {len(all_entries) - 80} more files')
        else:
            st.caption('No files yet.')
    except Exception as e:
        st.caption(f'Error: {e}')
