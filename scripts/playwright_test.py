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
    starts and renders its primary navigation and single-video input successfully.
    """
    screenshots_dir = Path('scripts') / 'screenshots'
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        page.goto(APP_URL, wait_until='domcontentloaded', timeout=30_000)

        # Current app-shell contract. Keep this test aligned with app.py structure.
        page.get_by_role('heading', name='🎬 YouTube Downloader').wait_for(timeout=30_000)
        page.get_by_role('textbox', name='YouTube URL').first.wait_for(timeout=30_000)

        tabs = page.get_by_test_id('stTabs').get_by_role('tab')
        tab_count = tabs.count()
        if tab_count != 7:
            raise AssertionError(f'Expected 7 primary tabs, found {tab_count}')

        page.screenshot(path=str(screenshots_dir / 'ui_smoke.png'), full_page=True)
        print('UI smoke test passed: app shell, 7 tabs, and URL input are visible.')
        browser.close()


if __name__ == '__main__':
    run_playwright_test()
