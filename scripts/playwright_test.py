from pathlib import Path
import os

from playwright.sync_api import sync_playwright

APP_URL = os.getenv('APP_URL', 'http://localhost:8501')
HEADLESS = os.getenv('PLAYWRIGHT_HEADLESS') == '1' or os.getenv('CI') is not None
EXPECTED_TABS = ['영상', '재생목록', '채널', '여러 URL', '예약', 'API']


def run_playwright_test() -> None:
    """Smoke-test the Streamlit shell without depending on live YouTube responses.

    Real YouTube metadata/download tests are intentionally excluded from the PR gate
    because they depend on external network state, video availability, bot detection,
    and yt-dlp/YouTube compatibility. This test verifies that the app starts and
    renders its header, download options, tabs and the download panel.
    """
    screenshots_dir = Path('scripts') / 'screenshots'
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(APP_URL, wait_until='domcontentloaded', timeout=30_000)

        # Current app-shell contract. Keep this test aligned with app.py structure.
        page.get_by_role('heading', name='🎬 YouTube 다운로더').wait_for(timeout=30_000)
        page.get_by_role('textbox', name='YouTube URL').first.wait_for(timeout=30_000)
        page.get_by_text('📦 다운로드 현황').wait_for(timeout=30_000)

        tabs = page.get_by_test_id('stTabs').get_by_role('tab')
        labels = [tabs.nth(i).inner_text() for i in range(tabs.count())]
        if len(labels) != len(EXPECTED_TABS) or not all(
                expected in label for expected, label in zip(EXPECTED_TABS, labels)):
            raise AssertionError(f'Unexpected tabs: {labels}')

        page.screenshot(path=str(screenshots_dir / 'ui_smoke.png'), full_page=True)
        # ASCII only: Windows consoles (cp949 etc.) can't print the tab emoji
        print(f'UI smoke test passed: header, URL input, download panel and {len(labels)} tabs.')
        browser.close()


if __name__ == '__main__':
    run_playwright_test()
