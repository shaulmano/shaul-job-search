from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    # ── Experis ──────────────────────────────────────────────────────────────
    page.goto('https://experis.co.il/search?q=QA+Manager', timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    soup = BeautifulSoup(page.content(), 'html.parser')

    results.append('=== EXPERIS job cards ===')
    # Try the known parent class
    cards = soup.select('div[class*="content"][class*="p-6"]')
    results.append(f'div[content][p-6] cards: {len(cards)}')
    for c in cards[:3]:
        a = c.find('a', href=True)
        texts = c.get_text(separator=' | ', strip=True)[:150]
        results.append(f'  link={a["href"] if a else "none"} | {texts}')

    # Also check what's in the page structure broadly
    results.append('--- all a[href*="/job/"] ---')
    for a in soup.select('a[href*="/job/"]')[:5]:
        parent = a.find_parent('div')
        pclass = ' '.join(parent.get('class', [])) if parent else ''
        results.append(f'  {a["href"]} | text={a.get_text(strip=True)[:60]} | parent={pclass[:60]}')

    # ── Dialog ───────────────────────────────────────────────────────────────
    page.goto('https://www.dialog.co.il/high-tech/jobs/qa', timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(6000)

    # Try to trigger job load by scrolling
    page.evaluate('window.scrollTo(0, 500)')
    page.wait_for_timeout(2000)

    soup = BeautifulSoup(page.content(), 'html.parser')
    results.append('\n=== DIALOG HTML dump (job-related) ===')

    # Look for any element with class containing 'job' or 'position' or 'result'
    for tag in ['article', 'div', 'li', 'section']:
        found = []
        for el in soup.find_all(tag, class_=True):
            classes = ' '.join(el.get('class', []))
            if any(k in classes.lower() for k in ['job', 'position', 'result', 'card', 'listing', 'item-']):
                text = el.get_text(strip=True)
                if 15 < len(text) < 200:
                    found.append(f'  <{tag} class="{classes[:60]}"> {text[:100]}')
        if found:
            results.append(f'--- {tag} with job/position/result/card ---')
            results.extend(found[:8])

    # Check for any AJAX data or JSON embedded in the page
    results.append('--- script tags with job data ---')
    for s in soup.find_all('script'):
        t = s.get_text()
        if 'job' in t.lower() and len(t) > 100:
            results.append(f'  script snippet: {t[:200]}')
            break

    # Look for the jobs list wrapper
    results.append('--- innerpage / jobs wrapper ---')
    for el in soup.select('.jobs_list, .job_list, [class*="jobs"], [id*="jobs"]'):
        results.append(f'  <{el.name} class="{" ".join(el.get("class",[]))[:60]}"> {el.get_text(strip=True)[:100]}')

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
