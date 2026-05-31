from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json, re

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page.goto('https://www.dialog.co.il/high-tech/jobs/qa', timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(5000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    browser.close()

# Try JSON-LD first
results.append('=== Dialog JSON-LD ===')
for s in soup.find_all('script', type='application/ld+json'):
    try:
        data = json.loads(s.string)
        if data.get('@type') == 'ItemList':
            items = data.get('itemListElement', [])
            results.append(f'ItemList with {len(items)} items')
            for item in items[:3]:
                job = item.get('item', {})
                results.append(f'  title={job.get("title","")} | url={job.get("url","")} | company={job.get("hiringOrganization",{}).get("name","")}')
    except Exception as e:
        results.append(f'parse error: {e}')

# Check jobs_list > list children
results.append('\n=== Dialog jobs_list > list children ===')
jobs_list = soup.select_one('div.jobs_list div.list')
if jobs_list:
    children = jobs_list.find_all(True, recursive=False)
    results.append(f'Direct children: {len(children)}')
    for ch in children[:5]:
        cls = ' '.join(ch.get('class', []))
        results.append(f'  <{ch.name} class="{cls}"> {ch.get_text(strip=True)[:120]}')
        # find links inside
        for a in ch.find_all('a', href=True)[:3]:
            results.append(f'    link: {a["href"]} | {a.get_text(strip=True)[:60]}')

# Check what elements have job numbers next to them
results.append('\n=== Elements around job_no ===')
for el in soup.select('div.job_no')[:3]:
    parent = el.find_parent()
    if parent:
        pclass = ' '.join(parent.get('class', []))
        results.append(f'parent: <{parent.name} class="{pclass}"> {parent.get_text(strip=True)[:120]}')
        for a in parent.find_all('a', href=True):
            results.append(f'  link: {a["href"]} | {a.get_text(strip=True)[:60]}')

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
