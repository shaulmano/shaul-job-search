from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import quote

ROLE = 'QA Manager'

URLS = {
    'Experis_search': f'https://www.experis.co.il/search?q={quote(ROLE)}',
    'Experis_home': 'https://www.experis.co.il/',
    'Dialog_home': 'https://www.dialog.co.il/',
    'Dialog_hightech': 'https://www.dialog.co.il/high-tech/',
}

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    for name, url in URLS.items():
        try:
            page.goto(url, timeout=20000, wait_until='domcontentloaded')
            page.wait_for_timeout(3000)
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')

            results.append(f'\n=== {name} ===')
            results.append(f'URL: {url}')

            # חפש links שמכילים job/career/משרה
            job_links = []
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                text = a.get_text(strip=True)
                if any(k in href.lower() for k in ['job', 'career', 'position', 'משרה', 'דרוש']):
                    job_links.append(f"  {href} | {text[:40]}")
            results.append(f"Links רלוונטיים ({len(job_links)}):")
            results.extend(job_links[:10])

        except Exception as e:
            results.append(f'\n=== {name} ERROR: {e} ===')

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print("נכתב לקובץ")
