from playwright.sync_api import sync_playwright
import time

APP_URL = 'http://localhost:8501'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(APP_URL)
    time.sleep(2)
    page.screenshot(path='scripts/screenshots/debug_initial.png')
    html = page.content()
    with open('scripts/screenshots/page.html', 'w', encoding='utf-8') as f:
        f.write(html)

    # Print button texts
    buttons = page.query_selector_all('button')
    texts = [b.inner_text() for b in buttons]
    print('Found buttons:')
    for t in texts:
        print('-', repr(t))

    # Also print visible text that matches 'Download'
    download_texts = page.query_selector_all("xpath=//*[contains(text(), 'Download') or contains(text(), 'download') or contains(text(), 'Download video')]")
    print('\nDownload-like elements:')
    for el in download_texts:
        try:
            print('-', el.inner_text())
        except Exception:
            print('-', '<unreadable>')

    page.screenshot(path='scripts/screenshots/debug_buttons.png')
    print('Screenshots and page html saved under scripts/screenshots/')
    browser.close()
