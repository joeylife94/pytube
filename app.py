"""Streamlit UI for the YouTube downloader.

Every download goes through one background DownloadQueue shared by all browser
sessions, so the page never blocks while files download; the 다운로드 현황 panel
at the bottom refreshes itself.
"""
import datetime
import json
import os
import shutil
import time
from dataclasses import asdict
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from app_helpers import (
    COOKIE_BROWSERS, FILENAME_PRESETS, FORMAT_LABELS, QUALITY_LABELS, SETTINGS_FIELDS,
    AppSettings, _safe_getsize, default_download_dir, format_upload_date, friendly_error,
    history_mode, human_count, human_eta, human_size, human_speed, is_channel_url,
    is_playlist_only_url, is_youtube_url, load_settings, md_escape, mode_flags, open_folder,
    parse_urls, resolution_for, resolve_template, reveal_file, running_in_container,
    safe_title, save_settings, video_id, watch_url,
)
from download_core import YTDLP_EJS_AVAILABLE, _auto_cookiefile
from download_db import clear_history, downloaded_urls, get_history, is_downloaded
from download_queue import MAX_CONCURRENT_LIMIT, DownloadQueue, QueueItem, QueueItemStatus
from pytube_helper import (
    YTDLP_AVAILABLE, cleanup_part_files, extract_channel_videos,
    extract_playlist_urls_with_titles, get_video_info, is_ffmpeg_available,
)
from queue_download_adapter import download_queue_item

try:
    from yt_dlp.version import __version__ as YTDLP_VERSION
except ImportError:
    YTDLP_VERSION = ''

S = QueueItemStatus
TERMINAL = (S.COMPLETED, S.FAILED, S.CANCELLED)
# Browser download buttons read the whole file into memory; skip them for huge files
MAX_BROWSER_DOWNLOAD = 2 * 1024 ** 3
UPLOADED_COOKIES_NAME = '.uploaded_cookies.txt'

st.set_page_config(page_title='YouTube 다운로더', page_icon='🎬', layout='wide')


# ─── Shared resources ───────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_queue(persist_path: str) -> DownloadQueue:
    """One queue + worker pool per process, shared by every browser tab.

    Its concurrency is process-global too: it starts from the saved setting and
    only changes when someone moves the slider (see apply_concurrency).
    """
    q = DownloadQueue(persist_path=persist_path, max_concurrent=load_settings().concurrency)
    q.set_download_function(download_queue_item)
    q.start_worker()
    return q


@st.cache_data(ttl=900, max_entries=100, show_spinner=False)
def fetch_preview(url: str, cookiefile: str, proxy: str, browser: str) -> Dict:
    try:
        return get_video_info(url, cookiefile=cookiefile or None, proxy=proxy or None,
                              cookies_from_browser=browser or None, raise_errors=True)
    except Exception as e:
        return {'error': str(e)}


@st.cache_data(ttl=600, max_entries=20, show_spinner=False)
def fetch_playlist(url: str) -> Dict:
    try:
        data = extract_playlist_urls_with_titles(url)
        return {'title': data.get('playlist_title') or '재생목록', 'items': data.get('items', [])}
    except Exception as e:
        return {'error': str(e)}


@st.cache_data(ttl=600, max_entries=20, show_spinner=False)
def fetch_channel(url: str, max_items: int) -> Dict:
    try:
        data = extract_channel_videos(url, max_items=max_items or None)
        return {'title': data.get('channel_title') or '채널', 'items': data.get('items', [])}
    except Exception as e:
        return {'error': str(e)}


QUEUE = get_queue(os.path.join(default_download_dir(), '.queue.json'))


# ─── Settings state ─────────────────────────────────────────────────────────

def init_session_state():
    if st.session_state.get('_init'):
        return
    settings = load_settings()
    for name, value in asdict(settings).items():
        st.session_state[f'cfg_{name}'] = value
    st.session_state['_saved_settings'] = asdict(settings)
    # Only toast for items that finish after this session started
    st.session_state['notified'] = {i.id for i in QUEUE.get_all() if i.status in TERMINAL}
    st.session_state['_init'] = True


def current_settings() -> AppSettings:
    defaults = AppSettings()
    values = {name: st.session_state.get(f'cfg_{name}', getattr(defaults, name))
              for name in SETTINGS_FIELDS}
    values['fmt'] = values['fmt'] or defaults.fmt
    return AppSettings(**values)


def persist_settings(settings: AppSettings):
    data = asdict(settings)
    if data != st.session_state.get('_saved_settings'):
        try:
            save_settings(settings)
            st.session_state['_saved_settings'] = data
        except OSError:
            pass


def resolve_output_folder(raw: str) -> str:
    folder = os.path.abspath(os.path.expanduser(raw.strip() or default_download_dir()))
    try:
        os.makedirs(folder, exist_ok=True)
        return folder
    except OSError as e:
        st.sidebar.error(f'폴더를 만들 수 없어요: {e}')
        return default_download_dir()


def queue_kwargs(s: AppSettings) -> Dict:
    audio_only, convert_mp3 = mode_flags(s.fmt)
    cookiefile = s.cookiefile if s.cookiefile and os.path.isfile(s.cookiefile) else ''
    return dict(
        audio_only=audio_only, convert_mp3=convert_mp3,
        subtitles=s.subtitles, subtitle_lang=s.subtitle_langs or 'en',
        rate_limit=int(s.rate_limit_kbps or 0), proxy=s.proxy.strip(),
        cookiefile=cookiefile, cookies_from_browser=s.cookies_from_browser,
        resolution=resolution_for(s.fmt, s.quality),
    )


def queued_urls(mode: str) -> set:
    """URLs already waiting/downloading in the same audio/video mode."""
    return {i.url for i in QUEUE.get_all()
            if i.status in (S.PENDING, S.DOWNLOADING, S.SCHEDULED)
            and ('audio' if i.audio_only else 'video') == mode}


# ─── Callbacks ──────────────────────────────────────────────────────────────

def enqueue_single(url: str, title: str, folder: str, s: AppSettings, scheduled_time: float = 0.0,
                   clear_key: Optional[str] = None):
    QUEUE.add(url, folder, title=title, scheduled_time=scheduled_time,
              filename_template=resolve_template(s.filename_template), **queue_kwargs(s))
    if clear_key:
        st.session_state[clear_key] = ''
    if scheduled_time:
        when = datetime.datetime.fromtimestamp(scheduled_time).strftime('%m-%d %H:%M')
        st.toast(f'{when}에 받도록 예약했어요', icon='⏰')
    else:
        st.toast(f'대기열에 추가했어요: {title[:60]}', icon='⬇️')


def enqueue_many(urls: List[str], titles: List[str], positions: List[Optional[int]], folder: str,
                 s: AppSettings, clear_key: Optional[str] = None):
    QUEUE.add_batch(urls, folder, titles=titles,
                    filename_templates=[resolve_template(s.filename_template, p) for p in positions],
                    **queue_kwargs(s))
    if clear_key:
        st.session_state[clear_key] = ''
    st.toast(f'{len(urls)}개를 대기열에 추가했어요', icon='⬇️')


def apply_concurrency():
    QUEUE.set_max_concurrent(st.session_state.get('cfg_concurrency', QUEUE.max_concurrent))


def retry_all_failed():
    for item in QUEUE.get_all():
        if item.status == S.FAILED:
            QUEUE.retry(item.id, force=True)


def set_collection_selection(kind: str, mode: str):
    st.session_state[f'{kind}_select'] = mode
    st.session_state[f'{kind}_editor_rev'] = st.session_state.get(f'{kind}_editor_rev', 0) + 1


def on_template_preset_change():
    preset = st.session_state.get('tmpl_preset')
    if preset in FILENAME_PRESETS:
        st.session_state['cfg_filename_template'] = FILENAME_PRESETS[preset]


def remove_uploaded_cookies():
    path = st.session_state.get('cfg_cookiefile', '')
    if path and os.path.basename(path) == UPLOADED_COOKIES_NAME and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    st.session_state['cfg_cookiefile'] = ''
    st.session_state['cookie_upload_rev'] = st.session_state.get('cookie_upload_rev', 0) + 1


def clean_part_files(folder: str):
    n = cleanup_part_files(folder)
    st.toast(f'.part 파일 {n}개를 지웠어요' if n else '지울 .part 파일이 없어요', icon='🧹')


def browser_notify(title: str, body: str):
    """Desktop notification from the main page (st.html runs in the page, not an iframe)."""
    payload = json.dumps({'title': title, 'body': body})
    st.html(f"""<script>
(() => {{
  const d = {payload};
  if (!('Notification' in window)) return;
  const show = () => new Notification(d.title, {{ body: d.body }});
  if (Notification.permission === 'granted') show();
  else if (Notification.permission !== 'denied') Notification.requestPermission().then(p => p === 'granted' && show());
}})();
</script>""", unsafe_allow_javascript=True)


# ─── Sidebar ────────────────────────────────────────────────────────────────

def render_sidebar() -> str:
    with st.sidebar:
        st.header('⚙️ 설정')
        st.text_input('저장 폴더', key='cfg_output_folder', placeholder=default_download_dir(),
                      help='비워 두면 기본 폴더(downloads)에 저장돼요.')
        raw_folder = st.session_state.get('cfg_output_folder', '')
        output_folder = resolve_output_folder(raw_folder)
        if raw_folder.strip() and os.path.normcase(raw_folder.strip()) != os.path.normcase(output_folder):
            st.caption(f'실제 경로: `{output_folder}`')
        if not running_in_container():
            st.button('폴더 열기', icon=':material/folder_open:', width='stretch',
                      on_click=open_folder, args=(output_folder,))

        st.subheader('다운로드')
        # The queue is shared by every tab, so show its value instead of this tab's copy;
        # a passive rerun in another tab must not push a stale value back.
        st.session_state['cfg_concurrency'] = QUEUE.max_concurrent
        st.slider('동시 다운로드', 1, MAX_CONCURRENT_LIMIT, key='cfg_concurrency', on_change=apply_concurrency,
                  help='한 번에 받을 영상 수예요 (모든 브라우저 탭에 함께 적용돼요). '
                       '너무 높으면 YouTube가 속도를 제한할 수 있어요.')
        st.text_input('자막 언어', key='cfg_subtitle_langs',
                      help='자막을 켰을 때 받을 언어 코드예요. 쉼표로 구분해요 (예: ko,en,ja).')
        st.number_input('속도 제한 (KB/s)', min_value=0, max_value=1_000_000, step=100,
                        key='cfg_rate_limit_kbps', help='0이면 제한하지 않아요.')

        # Keep the preset picker in sync with the template unless the user chose 직접 입력
        template = st.session_state.get('cfg_filename_template') or '%(title)s'
        preset = st.session_state.get('tmpl_preset')
        if preset is None or (preset in FILENAME_PRESETS and FILENAME_PRESETS[preset] != template):
            st.session_state['tmpl_preset'] = next(
                (name for name, value in FILENAME_PRESETS.items() if value == template), '직접 입력')
        st.selectbox('파일 이름', [*FILENAME_PRESETS, '직접 입력'], key='tmpl_preset',
                     on_change=on_template_preset_change)
        st.text_input('템플릿', key='cfg_filename_template', label_visibility='collapsed',
                      help='yt-dlp 출력 템플릿이에요. 예: %(title)s, %(uploader)s, %(upload_date)s, %(id)s')

        with st.expander('🍪 로그인 · 네트워크', expanded=False):
            render_cookie_settings()
            st.text_input('프록시', key='cfg_proxy', placeholder='socks5://127.0.0.1:1080',
                          help='지역 제한 영상을 받을 때 써요. http(s)://, socks5:// 지원')

        with st.expander('🧰 도구', expanded=False):
            st.toggle('완료되면 데스크톱 알림', key='cfg_notify')
            st.button('.part 조각 파일 정리', icon=':material/cleaning_services:', width='stretch',
                      on_click=clean_part_files, args=(output_folder,),
                      help='중단된 다운로드가 남긴 .part 파일을 지워요.')

        with st.expander('📜 최근 기록', expanded=False):
            render_history(output_folder)
    return output_folder


def render_cookie_settings():
    st.selectbox(
        '브라우저 쿠키', COOKIE_BROWSERS, key='cfg_cookies_from_browser',
        format_func=lambda b: '사용 안 함' if not b else b.capitalize(),
        help='해당 브라우저에 YouTube 로그인이 돼 있어야 해요. Windows의 Chrome·Edge는 쿠키 암호화 때문에 '
             '실패할 수 있어서 Firefox나 cookies.txt 업로드를 권장해요.')

    rev = st.session_state.get('cookie_upload_rev', 0)
    uploaded = st.file_uploader('cookies.txt 업로드', type=['txt'], key=f'cookie_upload_{rev}',
                                help='브라우저 확장(예: Get cookies.txt LOCALLY)으로 내보낸 Netscape 형식 파일')
    if uploaded is not None and st.session_state.get('_cookie_file_id') != uploaded.file_id:
        data = uploaded.getvalue()
        if b'\t' not in data and b'Netscape' not in data:
            st.error('Netscape 형식 쿠키 파일이 아니에요.')
        else:
            path = os.path.join(default_download_dir(), UPLOADED_COOKIES_NAME)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
            st.session_state['cfg_cookiefile'] = path
            st.session_state['_cookie_file_id'] = uploaded.file_id

    cookiefile = st.session_state.get('cfg_cookiefile', '')
    if cookiefile and os.path.isfile(cookiefile):
        st.success('업로드한 쿠키 파일을 쓰는 중이에요.', icon='🍪')
        st.button('쿠키 파일 지우기', on_click=remove_uploaded_cookies, width='stretch')
    else:
        auto = _auto_cookiefile(None)
        if auto:
            st.caption(f'🍪 자동 감지된 쿠키 파일: `{os.path.basename(auto)}`')


def render_history(output_folder: str):
    history = get_history(output_folder, limit=10)
    if not history:
        st.caption('아직 기록이 없어요.')
        return
    local = not running_in_container()
    for i, rec in enumerate(history):
        path = rec.get('filepath', '')
        exists = bool(path) and os.path.isfile(path)
        cols = st.columns([6, 1], vertical_alignment='center')
        cols[0].caption(f"{'✅' if exists else '⚪'} {md_escape((rec.get('title') or rec.get('url', '?'))[:40])}")
        if exists and local:
            cols[1].button('📂', key=f'hist_{i}', help='폴더에서 보기', on_click=reveal_file, args=(path,))
    st.button('기록 지우기', on_click=clear_history, args=(output_folder,), width='stretch')


# ─── Header & download options ──────────────────────────────────────────────

def render_header(ffmpeg_ok: bool, node_ok: bool):
    # Title and status badges share one wrapping row so narrow windows don't squeeze the title
    with st.container(horizontal=True, vertical_alignment='center', horizontal_alignment='distribute'):
        st.title('🎬 YouTube 다운로더', width='content')
        render_status_badges(ffmpeg_ok, node_ok)


def render_status_badges(ffmpeg_ok: bool, node_ok: bool):
    with st.container(horizontal=True, width='content', gap='small'):
        if YTDLP_AVAILABLE:
            st.badge(f'yt-dlp {YTDLP_VERSION}', icon=':material/check_circle:', color='green')
        else:
            st.badge('yt-dlp 없음', icon=':material/error:', color='red',
                     help='pip install "yt-dlp[default]"')
        st.badge('ffmpeg', icon=':material/check_circle:' if ffmpeg_ok else ':material/warning:',
                 color='green' if ffmpeg_ok else 'orange',
                 help=None if ffmpeg_ok else 'MP3 변환과 고화질 영상 병합에 필요해요. 설치하거나 FFMPEG_LOCATION을 설정하세요.')
        js_ok = node_ok and YTDLP_EJS_AVAILABLE
        st.badge('JS 해석기', icon=':material/check_circle:' if js_ok else ':material/warning:',
                 color='green' if js_ok else 'orange',
                 help='Node.js와 yt-dlp-ejs로 YouTube의 보호 영상을 풀어요.' if js_ok
                 else 'Node.js를 설치하면 일부 보호된 영상도 받을 수 있어요.')


def render_options_bar(s: AppSettings, ffmpeg_ok: bool):
    # A wrapping row instead of fixed columns so labels never get truncated in narrow windows
    with st.container(border=True, horizontal=True, vertical_alignment='bottom', gap='medium'):
        st.segmented_control('형식', list(FORMAT_LABELS), format_func=FORMAT_LABELS.get,
                             key='cfg_fmt', required=True)
        st.selectbox('화질', list(QUALITY_LABELS), format_func=QUALITY_LABELS.get, key='cfg_quality',
                     disabled=s.fmt != 'video', width=190, help='고른 화질 이하에서 가장 좋은 걸 받아요.')
        st.toggle('자막', key='cfg_subtitles', help=f'언어: {s.subtitle_langs or "en"} (사이드바에서 변경)')
        st.toggle('받은 영상 건너뛰기', key='cfg_skip_duplicates',
                  help='같은 폴더에 같은 형식으로 이미 받은 영상은 다시 받지 않아요.')
    if not ffmpeg_ok:
        if s.fmt == 'mp3':
            st.warning('ffmpeg가 없어서 MP3로 변환할 수 없어요. 「원본 오디오」를 고르거나 ffmpeg를 설치하세요.',
                       icon='⚠️')
        elif s.fmt == 'video':
            st.info('ffmpeg가 없으면 영상과 소리를 합칠 수 없어서 낮은 화질로 받아질 수 있어요.', icon='ℹ️')


# ─── Tabs ───────────────────────────────────────────────────────────────────

def render_preview(info: Dict):
    with st.container(border=True):
        thumb, meta = st.columns([1, 2], vertical_alignment='center')
        if info.get('thumbnail'):
            thumb.image(info['thumbnail'], width='stretch')
        with meta:
            st.markdown(f"#### {md_escape(info.get('title') or '제목 없음')}")
            details = [
                f"📺 {md_escape(info.get('channel') or '?')}",
                f"⏱ {info.get('duration_str', '?')}",
            ]
            if format_upload_date(info.get('upload_date', '')):
                details.append(f"📅 {format_upload_date(info['upload_date'])}")
            if info.get('view_count') is not None:
                details.append(f"👁 {human_count(info['view_count'])}")
            st.caption(' · '.join(details))
            facts = []
            if info.get('heights'):
                facts.append(f"최대 {info['heights'][0]}p")
            if info.get('filesize_approx'):
                facts.append(f"예상 크기 약 {human_size(info['filesize_approx'])}")
            if facts:
                st.caption(' · '.join(facts))
            if info.get('is_live'):
                st.warning('라이브 방송은 끝날 때까지 받거나 실패할 수 있어요.', icon='🔴')


def render_single_tab(s: AppSettings, output_folder: str):
    url = st.text_input('YouTube URL', key='url_single',
                        placeholder='https://www.youtube.com/watch?v=...   또는   https://youtu.be/...').strip()
    if not url:
        st.caption('영상 주소를 붙여넣고 Enter를 누르면 미리보기가 나와요.')
        return
    if not is_youtube_url(url):
        st.error('YouTube 주소가 아니에요.')
        return
    vid = video_id(url)
    if not vid:
        if is_playlist_only_url(url):
            st.info('재생목록 주소예요. 「📋 재생목록」 탭에 붙여넣어 주세요.', icon='📋')
        elif is_channel_url(url):
            st.info('채널 주소예요. 「📺 채널」 탭에 붙여넣어 주세요.', icon='📺')
        else:
            st.error('영상 주소를 알아볼 수 없어요.')
        return

    target = watch_url(vid)
    with st.spinner('영상 정보를 불러오는 중...'):
        info = fetch_preview(target, s.cookiefile, s.proxy, s.cookies_from_browser)
    if info.get('error'):
        st.error(friendly_error(info['error']), icon='⚠️')
        with st.expander('자세한 오류'):
            st.code(info['error'], language=None)
        st.button('다시 불러오기', icon=':material/refresh:', on_click=fetch_preview.clear)
        title = target
    else:
        render_preview(info)
        title = info.get('title') or target

    mode = history_mode(s.fmt)
    dup = is_downloaded(target, output_folder, mode=mode) if s.skip_duplicates else None
    in_queue = target in queued_urls(mode)
    if dup:
        st.warning(f"이미 받은 영상이에요: `{dup.get('filepath', '')}` — 다시 받으려면 「받은 영상 건너뛰기」를 끄세요.",
                   icon='✅')
    elif in_queue:
        st.info('이미 대기열에 있어요.', icon='⏳')
    st.button('다운로드', type='primary', icon=':material/download:', key='dl_single',
              disabled=bool(dup) or in_queue, on_click=enqueue_single,
              args=(target, title, output_folder, s), kwargs={'clear_key': 'url_single'})


def render_collection_tab(kind: str, s: AppSettings, output_folder: str):
    if kind == 'playlist':
        url = st.text_input('재생목록 URL', key='url_pl',
                            placeholder='https://www.youtube.com/playlist?list=...').strip()
        max_items = 0
    else:
        c1, c2 = st.columns([4, 1], vertical_alignment='bottom')
        url = c1.text_input('채널 URL', key='url_ch', placeholder='https://www.youtube.com/@채널이름').strip()
        max_items = int(c2.number_input('최대 개수', min_value=0, max_value=5000, value=50, step=10,
                                        key='ch_max', help='최신 영상부터 가져와요. 0이면 전체 (오래 걸려요)'))
    if not url:
        st.caption('주소를 붙여넣으면 영상 목록을 불러와서 원하는 것만 골라 받을 수 있어요.')
        return
    if not is_youtube_url(url):
        st.error('YouTube 주소가 아니에요.')
        return

    fetcher = fetch_playlist if kind == 'playlist' else fetch_channel
    with st.spinner('목록을 불러오는 중...'):
        data = fetch_playlist(url) if kind == 'playlist' else fetch_channel(url, max_items)
    if data.get('error'):
        st.error(friendly_error(data['error']), icon='⚠️')
        with st.expander('자세한 오류'):
            st.code(data['error'], language=None)
        st.button('다시 불러오기', icon=':material/refresh:', key=f'{kind}_reload', on_click=fetcher.clear)
        return
    entries = [it for it in data.get('items', []) if it.get('url')]
    if not entries:
        st.warning('영상을 찾지 못했어요.')
        return

    title = data['title']
    head, reload_col = st.columns([5, 1], vertical_alignment='center')
    head.markdown(f"**{md_escape(title)}** · {len(entries)}개")
    reload_col.button('새로고침', icon=':material/refresh:', key=f'{kind}_refresh', width='stretch',
                      on_click=fetcher.clear)

    in_subfolder = st.toggle(f'「{safe_title(title)}」 폴더에 저장', value=True, key=f'{kind}_subfolder')
    folder = os.path.join(output_folder, safe_title(title)) if in_subfolder else output_folder

    # Normalise to single-video URLs so a list= parameter never pulls the whole playlist again
    urls = [watch_url(video_id(it['url'])) if video_id(it['url']) else it['url'] for it in entries]
    titles = [it.get('title') or u for it, u in zip(entries, urls)]
    mode = history_mode(s.fmt)
    done = downloaded_urls(urls, folder, mode) if s.skip_duplicates else set()

    selection = st.session_state.get(f'{kind}_select', 'auto')
    default_selected = [(u not in done) if selection == 'auto' else selection == 'all' for u in urls]
    df = pd.DataFrame({
        '선택': default_selected,
        '#': range(1, len(urls) + 1),
        '제목': titles,
        '상태': ['✅ 받음' if u in done else '' for u in urls],
    })
    b1, b2, _ = st.columns([1, 1, 4])
    b1.button('전체 선택', key=f'{kind}_all', width='stretch',
              on_click=set_collection_selection, args=(kind, 'all'))
    b2.button('전체 해제', key=f'{kind}_none', width='stretch',
              on_click=set_collection_selection, args=(kind, 'none'))
    edited = st.data_editor(
        df, hide_index=True, width='stretch', height=min(420, 38 + 35 * len(df)),
        key=f"{kind}_editor_{abs(hash(url))}_{st.session_state.get(f'{kind}_editor_rev', 0)}",
        disabled=['#', '제목', '상태'],
        column_config={
            '선택': st.column_config.CheckboxColumn('선택', width='small'),
            '#': st.column_config.NumberColumn('#', width='small'),
            '제목': st.column_config.TextColumn('제목', width='large'),
            '상태': st.column_config.TextColumn('상태', width='small'),
        },
    )
    picked = [i for i, chosen in enumerate(edited['선택'].tolist()) if chosen]
    if done:
        st.caption(f'이미 받은 {len(done)}개는 기본으로 선택 해제했어요.')
    st.button(f'선택한 {len(picked)}개 다운로드', type='primary', icon=':material/download:',
              key=f'{kind}_download', disabled=not picked, on_click=enqueue_many,
              args=([urls[i] for i in picked], [titles[i] for i in picked], [i + 1 for i in picked],
                    folder, s))


def render_batch_tab(s: AppSettings, output_folder: str):
    text = st.text_area('URL 목록', key='batch_text', height=180,
                        placeholder='한 줄에 하나씩 붙여넣으세요 (공백이나 쉼표로 구분해도 돼요)\n'
                                    'https://www.youtube.com/watch?v=...\nhttps://youtu.be/...')
    upload = st.file_uploader('또는 .txt 파일 올리기', type=['txt'], key='batch_upload')
    raw = text + '\n' + (upload.getvalue().decode('utf-8', errors='ignore') if upload else '')
    videos, others = parse_urls(raw)
    if others:
        st.info(f'영상이 아닌 주소 {len(others)}개(재생목록·채널)는 뺐어요. 해당 탭을 이용하세요.', icon='ℹ️')
    if not videos:
        st.caption('여러 영상을 한 번에 대기열에 넣어요.')
        return
    mode = history_mode(s.fmt)
    skip = (downloaded_urls(videos, output_folder, mode) if s.skip_duplicates else set()) | queued_urls(mode)
    todo = [u for u in videos if u not in skip]
    summary = f'영상 **{len(videos)}개**'
    if len(todo) < len(videos):
        summary += f' · 이미 받았거나 대기 중인 {len(videos) - len(todo)}개 제외'
    st.markdown(summary)
    st.button(f'{len(todo)}개 다운로드', type='primary', icon=':material/download:', key='batch_download',
              disabled=not todo, on_click=enqueue_many,
              args=(todo, todo, [None] * len(todo), output_folder, s), kwargs={'clear_key': 'batch_text'})


def render_schedule_tab(s: AppSettings, output_folder: str):
    st.caption('정한 시각에 자동으로 받기 시작해요. 그때 이 앱이 켜져 있어야 해요.')
    url = st.text_input('YouTube URL', key='sched_url', placeholder='https://www.youtube.com/watch?v=...').strip()
    c1, c2 = st.columns(2)
    day = c1.date_input('날짜', key='sched_date', min_value=datetime.date.today())
    at = c2.time_input('시각', key='sched_time', value=datetime.time(23, 0), step=datetime.timedelta(minutes=5))
    when = datetime.datetime.combine(day, at)
    remaining = when.timestamp() - time.time()
    vid = video_id(url) if url else ''
    if url and not vid:
        st.error('영상 주소를 알아볼 수 없어요.')
    elif vid:
        if remaining <= 0:
            st.warning('이미 지난 시각이라 바로 시작돼요.')
        else:
            h, m = int(remaining // 3600), int(remaining % 3600 // 60)
            st.info(f"**{when.strftime('%Y-%m-%d %H:%M')}** 시작 (약 {h}시간 {m}분 뒤)", icon='⏰')
    target = watch_url(vid) if vid else ''
    st.button('예약하기', type='primary', icon=':material/schedule:', key='sched_go', disabled=not vid,
              on_click=enqueue_single, args=(target, target, output_folder, s),
              kwargs={'scheduled_time': max(when.timestamp(), time.time()), 'clear_key': 'sched_url'})


def render_api_tab():
    st.caption('다른 프로그램에서 다운로드를 요청할 수 있는 REST API예요. 별도 터미널에서 실행하세요.')
    st.code('python api_server.py --port 8000', language='bash')
    st.markdown('''
- 기본은 **이 PC에서만** 접속돼요(`127.0.0.1`). 다른 기기에서 쓰려면 `--host 0.0.0.0`과 함께
  환경변수 `API_TOKEN`을 설정하세요. 요청에는 `X-API-Key: <토큰>` 헤더를 붙여요.
- 대화형 문서: [http://localhost:8000/docs](http://localhost:8000/docs)

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/api/status` | 환경·대기열 상태 |
| `GET` | `/api/info?url=...` | 영상 정보 |
| `GET` | `/api/playlist/info?url=...` | 재생목록 정보 |
| `POST` | `/api/download` | 영상 하나 받기 |
| `POST` | `/api/batch` | 여러 URL 받기 |
| `POST` | `/api/playlist` | 재생목록 받기 |
| `POST` | `/api/channel` | 채널 영상 받기 |
| `POST` | `/api/schedule` | 예약 다운로드 |
| `GET` | `/api/queue` · `/api/queue/{id}` | 대기열 조회 |
| `POST` | `/api/queue/{id}/cancel` · `/retry` | 취소 · 재시도 |
| `DELETE` | `/api/queue/{id}` · `/api/queue` | 항목 삭제 · 끝난 항목 정리 |
| `GET` · `DELETE` | `/api/history` | 기록 조회 · 삭제 |
''')
    st.code('curl -X POST http://localhost:8000/api/download \\\n'
            '  -H "Content-Type: application/json" \\\n'
            '  -d \'{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "audio_only": true, "convert_mp3": true}\'',
            language='bash')


# ─── Download panel (self-refreshing) ───────────────────────────────────────

def _is_busy(items: List[QueueItem]) -> bool:
    soon = time.time() + 60
    return any(i.status in (S.DOWNLOADING, S.PENDING) or (i.status == S.SCHEDULED and i.scheduled_time <= soon)
               for i in items)


def _item_label(item: QueueItem) -> str:
    if item.convert_mp3:
        return '🎵 MP3'
    if item.audio_only:
        return '🎧 오디오'
    return f"🎬 {item.resolution or '최고 화질'}"


def _row():
    """A row whose first element stretches and trailing buttons keep their natural width."""
    return st.container(horizontal=True, vertical_alignment='center', gap='small')


def _render_active(item: QueueItem):
    with st.container(border=True):
        with _row():
            st.markdown(f'**{md_escape(item.title[:90])}**', width='stretch')
            st.button('✖', key=f'cancel_{item.id}', help='취소', on_click=QUEUE.request_cancel, args=(item.id,))
        if item.progress >= 100:
            text = '마무리 중 (병합·변환)...'
        elif item.total_bytes:
            text = (f'{item.progress}% · {human_size(item.downloaded_bytes)} / {human_size(item.total_bytes)}'
                    f' · {human_speed(item.speed)} · 남은 시간 {human_eta(item.eta)}')
        elif item.downloaded_bytes:
            # Live streams and some formats don't report a total size
            text = f'{human_size(item.downloaded_bytes)} 받는 중 · {human_speed(item.speed)} (전체 크기 모름)'
        else:
            text = '준비 중...'
        st.progress(item.progress / 100, text=f'{_item_label(item)} · {text}')


def _render_waiting(items: List[QueueItem]):
    for pos, item in enumerate(items, 1):
        with _row():
            if item.status == S.SCHEDULED:
                when = datetime.datetime.fromtimestamp(item.scheduled_time).strftime('%m-%d %H:%M')
                label = f'⏰ `{when}` {md_escape(item.title[:80])} · {_item_label(item)}'
            else:
                label = f'⏳ {pos}. {md_escape(item.title[:80])} · {_item_label(item)}'
            st.markdown(label, width='stretch')
            st.button('✖', key=f'cancel_{item.id}', help='취소', on_click=QUEUE.cancel, args=(item.id,))


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def _render_finished(item: QueueItem, local: bool):
    with _row():
        if item.status == S.COMPLETED:
            exists = bool(item.filepath) and os.path.isfile(item.filepath)
            size = _safe_getsize(item.filepath) if exists else 0
            st.markdown(f'✅ **{md_escape(item.title[:80])}**  \n'
                        f":gray[{_item_label(item)} · {human_size(size) if exists else '파일 없음'}"
                        f' · {md_escape(os.path.basename(item.filepath))}]', width='stretch')
            if exists and local:
                st.button('📂', key=f'reveal_{item.id}', help='폴더에서 보기', on_click=reveal_file,
                          args=(item.filepath,))
            if exists and size <= MAX_BROWSER_DOWNLOAD:
                path = item.filepath
                st.download_button('💾', data=lambda p=path: _read_file(p), file_name=os.path.basename(path),
                                   key=f'save_{item.id}', help='브라우저로 내려받기', on_click='ignore')
            return
        if item.status == S.FAILED:
            st.markdown(f'❌ **{md_escape(item.title[:80])}**  \n'
                        f':red[{md_escape(friendly_error(item.error, item.error_code))}]', width='stretch')
        else:
            st.markdown(f'🚫 **{md_escape(item.title[:80])}**  \n:gray[취소됨]', width='stretch')
        st.button('🔁', key=f'retry_{item.id}', help='다시 시도', on_click=QUEUE.retry,
                  args=(item.id,), kwargs={'force': True})
        st.button('🗑', key=f'remove_{item.id}', help='목록에서 지우기', on_click=QUEUE.remove, args=(item.id,))


def _notify_finished(items: List[QueueItem], notify: bool):
    notified = st.session_state.setdefault('notified', set())
    for item in items:
        if item.status in TERMINAL and item.id not in notified:
            notified.add(item.id)
            if item.status == S.COMPLETED:
                st.toast(f'다운로드 완료: {item.title[:60]}', icon='✅')
                if notify:
                    browser_notify('✅ 다운로드 완료', item.title[:100])
            elif item.status == S.FAILED:
                st.toast(f'실패: {item.title[:50]} — {friendly_error(item.error, item.error_code)[:60]}', icon='❌')


def render_downloads(was_busy: bool, notify: bool):
    items = QUEUE.get_all()
    _notify_finished(items, notify)
    active = [i for i in items if i.status == S.DOWNLOADING]
    waiting = [i for i in items if i.status in (S.PENDING, S.SCHEDULED)]
    finished = sorted((i for i in items if i.status in TERMINAL), key=lambda i: i.finished_at, reverse=True)
    failed = [i for i in finished if i.status == S.FAILED]

    with _row():
        st.subheader('📦 다운로드 현황', width='stretch')
        if failed:
            st.button(f'실패 {len(failed)}개 다시 시도', icon=':material/replay:', on_click=retry_all_failed)
        if finished:
            st.button('끝난 항목 정리', icon=':material/clear_all:', on_click=QUEUE.clear_completed)

    if not items:
        st.info('아직 받은 게 없어요. 위에서 URL을 붙여넣어 보세요.', icon='👋')
    else:
        done = sum(1 for i in finished if i.status == S.COMPLETED)
        st.caption(f'진행 {len(active)} · 대기 {len(waiting)} · 완료 {done} · 실패 {len(failed)}'
                   f' · 동시 {QUEUE.max_concurrent}개')
    for item in active:
        _render_active(item)
    if waiting:
        with st.expander(f'⏳ 대기 중 {len(waiting)}개', expanded=len(waiting) <= 5):
            _render_waiting(waiting)
    if finished:
        local = not running_in_container()
        for item in finished[:15]:
            _render_finished(item, local)
        if len(finished) > 15:
            with st.expander(f'이전 항목 {len(finished) - 15}개 더 보기'):
                for item in finished[15:]:
                    _render_finished(item, local)

    if _is_busy(items) != was_busy:
        # Switch between the fast and slow refresh fragment
        st.rerun()


@st.fragment(run_every=1)
def downloads_live(notify: bool):
    render_downloads(True, notify)


@st.fragment(run_every=10)
def downloads_idle(notify: bool):
    render_downloads(False, notify)


def render_files(output_folder: str):
    with st.expander('📁 저장된 파일'):
        entries = []
        for root, dirs, files in os.walk(output_folder):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                if name.startswith('.') or name.endswith(('.part', '.ytdl')):
                    continue
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                entries.append((stat.st_mtime, os.path.relpath(path, output_folder), stat.st_size))
        if not entries:
            st.caption('아직 파일이 없어요.')
            return
        entries.sort(reverse=True)
        st.dataframe(
            pd.DataFrame([{'파일': rel, '크기': human_size(size),
                           '받은 시각': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')}
                          for mtime, rel, size in entries[:200]]),
            hide_index=True, width='stretch')
        if len(entries) > 200:
            st.caption(f'최근 200개만 보여줘요 (전체 {len(entries)}개).')


# ─── Page ───────────────────────────────────────────────────────────────────

def main():
    init_session_state()
    ffmpeg_ok = is_ffmpeg_available()
    node_ok = shutil.which('node') is not None

    output_folder = render_sidebar()
    render_header(ffmpeg_ok, node_ok)
    render_options_bar(current_settings(), ffmpeg_ok)
    settings = current_settings()

    tabs = st.tabs(['🎬 영상', '📋 재생목록', '📺 채널', '📝 여러 URL', '⏰ 예약', '🔌 API'])
    with tabs[0]:
        render_single_tab(settings, output_folder)
    with tabs[1]:
        render_collection_tab('playlist', settings, output_folder)
    with tabs[2]:
        render_collection_tab('channel', settings, output_folder)
    with tabs[3]:
        render_batch_tab(settings, output_folder)
    with tabs[4]:
        render_schedule_tab(settings, output_folder)
    with tabs[5]:
        render_api_tab()

    st.divider()
    if _is_busy(QUEUE.get_all()):
        downloads_live(settings.notify)
    else:
        downloads_idle(settings.notify)
    render_files(output_folder)
    persist_settings(settings)


main()
