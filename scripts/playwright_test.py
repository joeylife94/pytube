from pathlib import Path
import os

from playwright.sync_api import sync_playwright

APP_URL = 'http://localhost:8501'
HEADLESS = os.getenv('PLAYWRIGHT_HEADLESS') == '1' or os.getenv('CI') is not None


def run_playwright_test() -> None:
    """Smoke-test the Streamlit shell without depending on live YouTube responses.

    Real YouTube metadata/download tests are intentionally excluded from the PR gate
    because they depend on external network state, video availability, bot detection,
    and yt-dlp/YouTube compatibility. This test verifies that the current application
    renders its primary navigation and single-video input successfully.
    """
    screenshots_dir = Path('scripts') / 'screenshots'
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        page.goto(APP_URL, wait_until='domcontentloaded', timeout=30_000)

        # Current app-shell contract. Keep this test aligned with app.py labels.
        page.get_by_role('heading', name='🎬 YouTube Downloader').wait_for(timeout=30_000)
        page.get_by_label('YouTube URL').wait_for(timeout=30_000)

        for label in ['Single', 'Playlist', 'Channel', 'Batch', 'Queue', 'Schedule', 'API']:
            page.get_by_text(label, exact=True).first.wait_for(timeout=10_000)

        page.get_by_role('button', name='🔍 Fetch info').wait_for(timeout=10_000)

        page.screenshot(path=str(screenshots_dir / 'ui_smoke.png'), full_page=True)
        print('UI smoke test passed: app shell, tabs, URL input, and Fetch info button are visible.')
        browser.close()


if __name__ == '__main__':
    run_playwright_test()
