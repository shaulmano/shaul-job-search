from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import quote

ROLE = 'QA Manager'

SITES = {
    'Experis': [
        f'https://www.experis.co.il/jobs?q={quote(ROLE)}',
        f'https://www.experis.co.il/search?q={quote(ROLE)}',
        'https://www.experis.co.il/jobs',
    ],
    'Dialog': [
        f'https://www.dialog.co.il/career/?s={quote(ROLE)}',
        f'https://www.dialog.co.il/careers/?s={quote(ROLE)}',
        'https://www.dialog.co.il/jobs/',
        'https://www.dialog.co.il/career/',
    ],
    'Nisha': [
        'https://www.nisha.co.il/jobs/',
        'https://www.nisha.co.il/career/',
        f'https://www.nisha.co.il/?s={quote(ROLE)}',
        'https://www.nisha.co.il/',
    ],
    'Maof': [
        'https://www.maof-hr.co.il/jobs/',
        'https://www.maof-hr.co.il/career/',
        'https://www.maof-hr.co.il/',
        f'https://www.maof-hr.co.il/?s={quote(ROLE)}',
    ],
}

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    for site, urls in SITES.items():
        results.append(f'\n=== {site} ===')
        for url in urls:
            try:
                resp = page.goto(url, timeout=15000, wait_until='domcontentloaded')
                status = resp.status if resp else '?'
                title = page.title()
                results.append(f'  {status}  {url}')
                results.append(f'       כותרת: {title[:60]}')
            except Exception as e:
                results.append(f'  ERR  {url}  ({e})')

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print("נכתב לקובץ")
