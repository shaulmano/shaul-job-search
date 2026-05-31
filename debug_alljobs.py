from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page.goto('https://www.alljobs.co.il/SearchResultsPage.aspx?position=QA+Manager', timeout=30000, wait_until='networkidle')
    soup = BeautifulSoup(page.content(), 'html.parser')
    browser.close()

results = []
# print first 3000 chars of body text to see what's there
body = soup.get_text(separator='\n', strip=True)
lines = [l for l in body.split('\n') if l.strip()]
results.append(f'Total text lines: {len(lines)}')
results.append('--- first 40 lines ---')
results.extend(lines[:40])

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
