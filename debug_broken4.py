from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    # AllJobs - wait longer for JS
    results.append('=== AllJobs Playwright ===')
    page.goto('https://www.alljobs.co.il/SearchResultsPage.aspx?position=QA+Manager', timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(6000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    # Try many link patterns
    for pat in ['a[href*="/Job/"]', 'a[href*="JobId"]', 'a[href*="/jobs/"]', '[class*="job-item"] a', '[class*="JobItem"] a', '[class*="single-job"] a']:
        els = soup.select(pat)
        if els:
            results.append(f'  {pat}: {len(els)}')
            results.append(f'    {els[0].get("href","")[:70]} | {els[0].get_text(strip=True)[:40]}')
    # Look at all divs with job-ish classes
    for el in soup.find_all(['div','li','article'], class_=True):
        cls = ' '.join(el.get('class',[]))
        if any(k in cls.lower() for k in ['job','position','result','vacancy','listing']):
            results.append(f'  <{el.name} class="{cls[:60]}"> {el.get_text(strip=True)[:80]}')
            break  # just first one
    # Show first 20 text lines
    lines = [l for l in soup.get_text('\n', strip=True).split('\n') if l.strip()]
    results.append(f'  text lines: {len(lines)}')
    results.extend([f'  {l}' for l in lines[:20]])

    # Drushim - try XHR intercept approach - look at page.url after AJAX
    results.append('\n=== Drushim - wait for results loader ===')
    page.goto('https://www.drushim.co.il/jobs/searchjobs/?q=QA+Manager', timeout=30000, wait_until='domcontentloaded')
    # Wait for the results to finish loading
    try:
        page.wait_for_selector('[class*="jobBox"], [class*="JobBox"], [data-job-id], .job-item', timeout=12000)
    except Exception:
        page.wait_for_timeout(8000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    # Try many patterns
    for pat in ['[class*="jobBox"]', '[class*="JobBox"]', '[data-job-id]', '[class*="job-card"]',
                '[class*="jobCard"]', '[class*="single"]', 'li[class*="job"]']:
        els = soup.select(pat)
        if els:
            results.append(f'  {pat}: {len(els)}')
            results.append(f'    {els[0].get_text(strip=True)[:100]}')
    # Look for any elements with data- attributes suggesting job data
    els_with_data = soup.find_all(attrs={'data-job-id': True})
    results.append(f'  data-job-id elements: {len(els_with_data)}')
    # Show all divs with class names
    seen_classes = set()
    for el in soup.find_all(['div','li','article'], class_=True):
        cls = ' '.join(el.get('class',[]))
        if cls not in seen_classes and len(cls) < 60:
            seen_classes.add(cls)
            if len(seen_classes) <= 30:
                results.append(f'  class: {cls}')
    # show text
    lines = [l for l in soup.get_text('\n', strip=True).split('\n') if l.strip()]
    results.append(f'  text lines: {len(lines)}')
    results.extend([f'  {l}' for l in lines[:15]])

    # One1 - click category and find job items
    results.append('\n=== One1 - after clicking QA category ===')
    page.goto('https://www.one1.co.il/careers/', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    try:
        page.click('a.jobcats:has-text("בדיקות ואוטומציה")', timeout=5000)
        page.wait_for_timeout(3000)
    except Exception as e:
        results.append(f'  click error: {e}')
        try:
            page.click('text=בדיקות ואוטומציה', timeout=5000)
            page.wait_for_timeout(3000)
        except Exception as e2:
            results.append(f'  click2 error: {e2}')
    soup = BeautifulSoup(page.content(), 'html.parser')
    # Look for job cards
    for pat in ['[class*="job-item"]', '[class*="jobItem"]', '[class*="position"]',
                '[class*="career-item"]', '[class*="jobcard"]', '.job', '[class*="opening"]']:
        els = soup.select(pat)
        if els:
            results.append(f'  {pat}: {len(els)}')
            results.append(f'    {els[0].get_text(strip=True)[:100]}')
            a = els[0].find('a', href=True)
            if a:
                results.append(f'    href: {a.get("href","")[:70]}')
    # All divs/li with any class
    for el in soup.find_all(['div','li','article'], class_=True):
        cls = ' '.join(el.get('class',[]))
        if 'job' in cls.lower() or 'career' in cls.lower() or 'position' in cls.lower():
            results.append(f'  <{el.name} class="{cls[:60]}"> {el.get_text(strip=True)[:80]}')
            break

    # Maof - use the jobs page with QA category filter
    results.append('\n=== Maof - job cards structure ===')
    page.goto('https://www.maof-hr.co.il/%d7%9e%d7%a9%d7%a8%d7%95%d7%aa/', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    # Look for job cards
    for pat in ['article', '[class*="job"]', '[class*="position"]', '[class*="listing"]',
                '.post', '[class*="item"]', '[class*="card"]']:
        els = soup.select(pat)
        if els:
            a = els[0].find('a', href=True)
            results.append(f'  {pat}: {len(els)} | first href: {a.get("href","")[:60] if a else "none"} | {els[0].get_text(strip=True)[:80]}')
    # All links with maof
    for a in soup.find_all('a', href=True):
        h = a.get('href','')
        txt = a.get_text(strip=True)
        if 'maof' in h and len(h) > 35 and txt:
            results.append(f'  link: {h[:70]} | {txt[:40]}')
    # Show page text
    lines = [l for l in soup.get_text('\n', strip=True).split('\n') if l.strip()]
    results.append(f'  text lines: {len(lines)}')
    results.extend([f'  {l}' for l in lines[:20]])

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
