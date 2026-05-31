from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page.goto('https://www.dialog.co.il/high-tech/jobs/qa', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    browser.close()

results = []

# כל ה-links שמובילים למשרות
results.append('=== Links למשרות ===')
for a in soup.find_all('a', href=True):
    href = a.get('href','')
    if '/job/' in href or '/משרה/' in href or '/position/' in href:
        results.append(f"  {href} | {a.get_text(strip=True)[:60]}")

# כל ה-divs עם class
results.append('\n=== כל ה-divs עם class שמכילים טקסט קצר ===')
for el in soup.find_all('div', class_=True):
    classes = ' '.join(el.get('class',[]))
    text = el.get_text(strip=True)
    if 10 < len(text) < 150 and not any(c in classes for c in ['nav', 'menu', 'header', 'footer']):
        results.append(f"  <div class='{classes}'> {text[:100]}")

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results[:80]))
print("נכתב לקובץ")
