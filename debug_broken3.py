from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    # Drushim - wait for job cards
    results.append('=== Drushim ===')
    page.goto('https://www.drushim.co.il/jobs/searchjobs/?q=QA+Manager', timeout=25000, wait_until='domcontentloaded')
    try:
        page.wait_for_selector('[class*="jobBox"], [class*="job-item"], [class*="JobItem"], .job_', timeout=8000)
    except Exception:
        page.wait_for_timeout(5000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    for sel in ['[class*="jobBox"]','[class*="job-item"]','[class*="JobItem"]','.job_','[class*="result"]']:
        els = soup.select(sel)
        if els:
            results.append(f'  {sel}: {len(els)}')
            results.append(f'    {els[0].get_text(strip=True)[:100]}')
    for a in soup.find_all('a', href=True)[:20]:
        h = a.get('href','')
        if '/job/' in h or '/משרה/' in h:
            results.append(f'  link: {h[:70]} | {a.get_text(strip=True)[:40]}')

    # One1 - find QA jobs URL
    results.append('\n=== One1 ===')
    page.goto('https://www.one1.co.il/careers/', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    # Try clicking QA category
    try:
        page.click('text=בדיקות ואוטומציה', timeout=5000)
        page.wait_for_timeout(2000)
    except Exception:
        pass
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append(f'URL after click: {page.url}')
    for a in soup.find_all('a', href=True):
        h = a.get('href','')
        if 'one1' in h and ('job' in h.lower() or 'career' in h.lower() or 'position' in h.lower()):
            results.append(f'  link: {h[:70]} | {a.get_text(strip=True)[:40]}')
    # Look for job cards
    for el in soup.select('[class*="job"], [class*="position"], [class*="career-item"]')[:5]:
        results.append(f'  <{el.name} class="{" ".join(el.get("class",[]))[:40]}"> {el.get_text(strip=True)[:80]}')

    # Maof - try jobs page
    results.append('\n=== Maof jobs page ===')
    page.goto('https://www.maof-hr.co.il/%d7%9e%d7%a9%d7%a8%d7%95%d7%aa/', timeout=20000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append(f'URL: {page.url}')
    for el in soup.select('article, [class*="job"], [class*="position"]')[:5]:
        a = el.find('a', href=True)
        h = a.get('href','') if a else ''
        results.append(f'  {h[:60]} | {el.get_text(strip=True)[:80]}')

    # AllJobs - try curl_cffi
    results.append('\n=== AllJobs curl_cffi ===')
    try:
        from curl_cffi import requests as cf
        r = cf.get('https://www.alljobs.co.il/SearchResultsPage.aspx?position=QA+Manager',
                   impersonate='chrome124', timeout=15)
        soup2 = BeautifulSoup(r.text, 'html.parser')
        links = soup2.select('a[href*="/Job/"]')
        results.append(f'  status={r.status_code} links={len(links)}')
        if links:
            results.append(f'  {links[0]["href"]} | {links[0].get_text(strip=True)[:40]}')
        else:
            body = soup2.get_text()[:200]
            results.append(f'  body: {body}')
    except Exception as e:
        results.append(f'  error: {e}')

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
