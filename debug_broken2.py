from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    # AllJobs - find correct URL
    results.append('=== AllJobs - trying URLs ===')
    for url in [
        'https://www.alljobs.co.il/jobs/q/QA-Manager/',
        'https://www.alljobs.co.il/Search/Upload/SearchFreeText/0/0/0/0/QA%20Manager',
    ]:
        page.goto(url, timeout=20000, wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        final_url = page.url
        soup = BeautifulSoup(page.content(), 'html.parser')
        job_links = soup.select('a[href*="/Job/"], a[href*="/job/"]')
        results.append(f'  {url[:60]} -> {final_url[:60]} | links={len(job_links)}')
        if job_links:
            results.append(f'    sample: {job_links[0]["href"]} | {job_links[0].get_text(strip=True)[:40]}')

    # Drushim - look at job structure
    results.append('\n=== Drushim - job structure ===')
    page.goto('https://www.drushim.co.il/jobs/searchjobs/?q=QA+Manager', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(5000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    # Try all link patterns
    for pattern in ['a[href*="/job/"]', 'a[href*="drushim"]', '[class*="job"] a']:
        links = soup.select(pattern)
        if links:
            results.append(f'  {pattern}: {len(links)} found')
            results.append(f'    {links[0]["href"][:60]} | {links[0].get_text(strip=True)[:40]}')
    # All divs with class containing numbers or job-ish words
    for el in soup.find_all(['div','li','article'], class_=True):
        cls = ' '.join(el.get('class',[]))
        if any(k in cls for k in ['job_','Job','position','result','listing']):
            results.append(f'  <{el.name} class="{cls[:50]}"> {el.get_text(strip=True)[:80]}')

    # One1 - navigate to QA category
    results.append('\n=== One1 - QA category ===')
    page.goto('https://www.one1.co.il/careers/', timeout=25000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    # Find QA category link
    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True)
        href = a.get('href','')
        if any(k in text for k in ['בדיקות', 'QA', 'automation']):
            results.append(f'  QA link: {href} | {text[:60]}')

    # Maof - look more carefully
    results.append('\n=== Maof - structure ===')
    page.goto('https://www.maof-hr.co.il/?s=QA+Manager', timeout=20000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append(f'URL: {page.url}')
    for el in soup.select('article, .job, [class*="position"]')[:5]:
        a = el.find('a', href=True)
        results.append(f'  {a["href"][:60] if a else "no-link"} | {el.get_text(strip=True)[:80]}')
    # check all links on page
    for a in soup.find_all('a', href=True)[:10]:
        h = a.get('href','')
        if 'maof' in h and '?' not in h and len(h) > 30:
            results.append(f'  link: {h[:70]} | {a.get_text(strip=True)[:40]}')

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
