from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # נפתח דפדפן אמיתי לראות מה קורה
    page = browser.new_page()
    page.goto('https://www.gotfriends.co.il/jobs/', timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)

    # נחפש את שדה החיפוש
    inputs = page.query_selector_all('input[type="text"], input[type="search"], input[placeholder]')
    lines = []
    for i, inp in enumerate(inputs):
        placeholder = inp.get_attribute('placeholder') or ''
        name = inp.get_attribute('name') or ''
        lines.append(f"Input {i}: placeholder='{placeholder}' name='{name}'")

    with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w') as f:
        f.write('\n'.join(lines))

    page.wait_for_timeout(3000)
    browser.close()
