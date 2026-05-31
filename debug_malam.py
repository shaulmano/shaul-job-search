from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page.goto('https://career.malamteam.com/%D7%A8%D7%A9%D7%99%D7%9E%D7%AA-%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/', timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')
results = []
for card in soup.select('div.job-item-container')[:5]:
    top = card.select_one('.job-item-top')
    meta = card.select_one('.job-meta')
    link = card.select_one('a')
    title_text = top.get_text(strip=True) if top else ''
    meta_text = meta.get_text(strip=True) if meta else ''
    title = title_text.replace(meta_text, '').strip()
    href = link.get('href', '') if link else ''
    results.append(f"title: {title}")
    results.append(f"href: {href}")
    results.append('---')

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print("נכתב לקובץ")
