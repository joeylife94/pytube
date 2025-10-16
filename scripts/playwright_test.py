from playwright.sync_api import sync_playwright
import time

APP_URL = 'http://localhost:8501'
TEST_URL = 'https://youtu.be/-CpaiHzIRNc?si=OdbUScvmYnvPXUjf'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
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
    time.sleep(1)

    # Fill URL (first text input is the video URL)
    page.fill('input[type="text"]', TEST_URL)
    time.sleep(0.5)

    # Ensure "Show live progress" is checked
    try:
        if not page.is_checked('text=Show live progress in UI'):
            page.click('text=Show live progress in UI')
            time.sleep(0.2)
    except Exception:
        # ignore if checkbox not found
        pass

    # Click Start download
    page.click('text=Start download')

    # Wait for metadata/title to appear (the app writes a 'Title:' line or an info message)
    try:
        page.wait_for_selector('text=Title:', timeout=20000)
        print('Metadata title appeared')
    except Exception:
        # fallback: wait for the yt-dlp info message
        try:
            page.wait_for_selector('text=Metadata fetched via yt-dlp', timeout=10000)
            print('Metadata fetched via yt-dlp appeared')
        except Exception as e:
            print('Metadata did not appear before timeout:', e)

    # Take a screenshot after metadata phase
    page.screenshot(path='scripts/screenshots/after_fetch.png')

    # Try to find and click the download button
    try:
        page.wait_for_selector('text=Download video now (yt-dlp)', timeout=10000)
        page.click('text=Download video now (yt-dlp)')
        print('Clicked Download video now (yt-dlp)')
    except Exception as e:
        print('Download button not found after metadata wait:', e)
        page.screenshot(path='scripts/screenshots/not_found_after_fetch.png')
        # save html for inspection
        with open('scripts/screenshots/page_after_fetch.html', 'w', encoding='utf-8') as f:
            f.write(page.content())
        browser.close()
        raise

    # Capture live progress screenshots for up to 30s
    for i in range(30):
        page.screenshot(path=f'scripts/screenshots/progress_{i:02d}.png')
        time.sleep(1)

    page.screenshot(path='scripts/screenshots/final.png')
    print('Screenshots saved to scripts/screenshots/')
    browser.close()
