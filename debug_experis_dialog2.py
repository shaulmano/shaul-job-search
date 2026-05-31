from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import quote

ROLE = 'QA Manager'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    results = []

    # Experis
    page.goto(f'https://experis.co.il/search?q={quote(ROLE)}', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('=== Experis ===')
    for a in soup.find_all('a', href=True):
        href = a.get('href','')
        if '/job/' in href:
            results.append(f"  link: {href} | {a.get_text(strip=True)[:60]}")
            parent = a.find_parent()
            if parent:
                results.append(f"  parent: <{parent.name} class='{' '.join(parent.get('class',[]))}'>")
            break

    # Dialog QA
    page.goto('https://www.dialog.co.il/high-tech/jobs/qa', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('\n=== Dialog /high-tech/jobs/qa ===')
    results.append(f'כותרת: {page.title()}')
    for tag in ['article', 'li', 'div']:
        found = []
        for el in soup.find_all(tag, class_=True):
            classes = ' '.join(el.get('class',[]))
            text = el.get_text(strip=True)
            if 20 < len(text) < 200:
                found.append(f"  <{tag} class='{classes}'> {text[:80]}")
        if found:
            results.append(f"--- {tag} elements ---")
            results.extend(found[:5])
            break

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print("נכתב לקובץ")
