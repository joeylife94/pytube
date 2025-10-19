from playwright.sync_api import sync_playwright
import time
import os
from pathlib import Path

APP_URL = 'http://localhost:8501'
TEST_URL = 'https://youtu.be/-CpaiHzIRNc?si=OdbUScvmYnvPXUjf'

# Decide headless mode: in CI we run headless. You can force headless by setting PLAYWRIGHT_HEADLESS=1
HEADLESS = os.getenv('PLAYWRIGHT_HEADLESS') == '1' or os.getenv('CI') is not None

def run_playwright_test():
    screenshots_dir = Path('scripts') / 'screenshots'
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        # Print console messages from the page to our stdout for debugging
        def on_console(msg):
            try:
                print(f'PAGE LOG: {msg.type}: {msg.text}')
            except Exception:
                pass

        page.on('console', on_console)

        page.goto(APP_URL)
        # Wait for initial load (give Streamlit time to render)
        try:
            page.wait_for_load_state('networkidle', timeout=60000)
        except Exception:
            # networkidle may not be reliable with Streamlit; fallback to a short sleep
            time.sleep(2)

        # Fill URL (first text input is the video URL)
        page.fill('input[type="text"]', TEST_URL)
        time.sleep(0.5)

        # Ensure "Show live progress" is checked
        try:
            checkbox_locator = page.locator('text=Show live progress in UI')
            if checkbox_locator.count() > 0:
                # click if not checked
                try:
                    if not page.is_checked('text=Show live progress in UI'):
                        checkbox_locator.click()
                        time.sleep(0.2)
                except Exception:
                    # best-effort click
                    try:
                        checkbox_locator.click()
                    except Exception:
                        pass
        except Exception:
            # ignore if checkbox not found
            pass

        # Click Start download
        page.click('text=Start download')

        # Wait for metadata/title to appear (the app writes a 'Title:' line or an info message)
        # Wait longer for metadata to appear (Streamlit may take time to fetch)
        try:
            # wait up to 600s for metadata (600000 ms)
            page.wait_for_selector('text=Title:', timeout=600000)
            print('Metadata title appeared')
        except Exception:
            # fallback: wait for the yt-dlp info message
            try:
                # wait up to 600s for yt-dlp fallback metadata
                page.wait_for_selector('text=Metadata fetched via yt-dlp', timeout=600000)
                print('Metadata fetched via yt-dlp appeared')
            except Exception as e:
                print('Metadata did not appear before timeout:', e)
                # capture page for debugging
                page.screenshot(path='scripts/screenshots/metadata_timeout.png')
                with open('scripts/screenshots/page_metadata_timeout.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())

        # Take a screenshot after metadata phase
        page.screenshot(path='scripts/screenshots/after_fetch.png')

        # Try to find and click the download button
        try:
            # wait up to 600s for download button to appear
            page.wait_for_selector('text=Download video now (yt-dlp)', timeout=600000)
            page.click('text=Download video now (yt-dlp)')
            print('Clicked Download video now (yt-dlp)')
        except Exception as e:
            print('Download button not found after metadata wait:', e)
            # take a few diagnostic screenshots and save page HTML
            page.screenshot(path='scripts/screenshots/not_found_after_fetch.png')
            with open('scripts/screenshots/page_after_fetch.html', 'w', encoding='utf-8') as f:
                f.write(page.content())
            # also attempt to capture any textareas or visible UI sections
            try:
                page.screenshot(path='scripts/screenshots/not_found_after_fetch_2.png', full_page=True)
            except Exception:
                pass
            browser.close()
            raise

        # Capture live progress screenshots for up to 30s
        # Capture live progress screenshots for up to ~600s, once every 2s (≈300 captures)
        for i in range(300):
            page.screenshot(path=f'scripts/screenshots/progress_{i:03d}.png')
            time.sleep(2)

        page.screenshot(path='scripts/screenshots/final.png')
        print('Screenshots saved to scripts/screenshots/')
        browser.close()


if __name__ == '__main__':
    run_playwright_test()
