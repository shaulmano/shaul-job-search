from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    # AllJobs
    page.goto('https://www.alljobs.co.il/SearchResultsPage.aspx?position=QA+Manager', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(5000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('=== AllJobs ===')
    results.append(f'URL: {page.url}')
    body_lines = [l for l in soup.get_text('\n', strip=True).split('\n') if l.strip()]
    results.append(f'Text lines: {len(body_lines)}')
    results.extend(body_lines[:15])
    for a in soup.select('a[href]')[:5]:
        if any(k in a.get('href','').lower() for k in ['job','position','משרה']):
            results.append(f'  link: {a["href"][:80]} | {a.get_text(strip=True)[:40]}')

    # Drushim
    page.goto('https://www.drushim.co.il/jobs/searchjobs/?q=QA+Manager', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(5000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('\n=== Drushim ===')
    results.append(f'URL: {page.url}')
    body_lines = [l for l in soup.get_text('\n', strip=True).split('\n') if l.strip()]
    results.append(f'Text lines: {len(body_lines)}')
    results.extend(body_lines[:15])
    for a in soup.select('a[href*="/job/"]')[:5]:
        results.append(f'  link: {a["href"][:80]} | {a.get_text(strip=True)[:40]}')

    # Maof
    page.goto('https://www.maof-hr.co.il/?s=QA+Manager', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('\n=== Maof ===')
    for el in soup.select('article')[:3]:
        a = el.find('a', href=True)
        results.append(f'  {a["href"][:60] if a else "no link"} | {el.get_text(strip=True)[:80]}')

    # Sela
    page.goto('https://blog.sela.co.il/Jobs', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('\n=== Sela ===')
    results.append(f'URL: {page.url}')
    body_lines = [l for l in soup.get_text('\n', strip=True).split('\n') if l.strip()]
    results.extend(body_lines[:10])
    for a in soup.select('a[href]')[:5]:
        h = a.get('href','')
        if 'job' in h.lower() or 'sela' in h.lower():
            results.append(f'  link: {h[:80]} | {a.get_text(strip=True)[:40]}')

    # One1
    page.goto('https://www.one1.co.il/careers/', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('\n=== One1 ===')
    results.append(f'URL: {page.url}')
    for el in soup.select('[class*="position"], [class*="job"], [class*="career"]')[:5]:
        a = el.find('a', href=True)
        results.append(f'  <{el.name} class="{" ".join(el.get("class",[]))[:40]}"> {el.get_text(strip=True)[:80]}')

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
