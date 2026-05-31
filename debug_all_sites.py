from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import quote

ROLE = 'QA Manager'

SITES = {
    'AllJobs':    f'https://www.alljobs.co.il/SearchResultsPage.aspx?position={quote(ROLE)}',
    'Drushim':    f'https://www.drushim.co.il/jobs/searchjobs/?q={quote(ROLE)}',
    'Experis':    f'https://www.experis.co.il/jobs?keyword={quote(ROLE)}',
    'Dialog':     f'https://www.dialog.co.il/jobs?q={quote(ROLE)}',
    'SQLink':     f'https://www.sqlink.com/career/?s={quote(ROLE)}',
    'Nisha':      f'https://www.nisha.co.il/jobs/?s={quote(ROLE)}',
    'MalamTeam':  'https://career.malamteam.com/%D7%A8%D7%A9%D7%99%D7%9E%D7%AA-%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/',
    'Maof':       f'https://www.maof-hr.co.il/%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/?s={quote(ROLE)}',
    'Sela':       'https://blog.sela.co.il/Jobs',
    'One1':       'https://www.one1.co.il/careers/',
}

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    for name, url in SITES.items():
        try:
            page.goto(url, timeout=25000, wait_until='domcontentloaded')
            page.wait_for_timeout(3000)
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')

            # נחפש elements שנראים כמו כרטיסיות משרה
            candidates = []
            for tag in ['article', 'li', 'div', 'a']:
                for el in soup.find_all(tag, class_=True):
                    classes = ' '.join(el.get('class', []))
                    text = el.get_text(strip=True)
                    if (('job' in classes.lower() or 'position' in classes.lower() or 'career' in classes.lower())
                            and 20 < len(text) < 300):
                        candidates.append(f"  <{tag} class='{classes}'> {text[:80]}")
                if candidates:
                    break

            results.append(f"\n=== {name} ===")
            results.append(f"URL: {url}")
            if candidates:
                results.append(f"נמצאו {len(candidates)} אלמנטים:")
                results.extend(candidates[:5])
            else:
                results.append("לא נמצאו אלמנטים מתאימים")
                # נדפיס כותרות דף
                title = soup.find('title')
                results.append(f"כותרת דף: {title.get_text() if title else 'N/A'}")

        except Exception as e:
            results.append(f"\n=== {name} ===")
            results.append(f"שגיאה: {e}")

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print("נכתב לקובץ")
