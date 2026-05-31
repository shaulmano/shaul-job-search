from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

CANDIDATE_URLS = [
    # QA
    'https://www.gotfriends.co.il/jobslobby/qa/',
    'https://www.gotfriends.co.il/jobslobby/qa/qa-team-leader/',
    'https://www.gotfriends.co.il/jobslobby/qa/qa-manager/',
    # Management / PM
    'https://www.gotfriends.co.il/jobslobby/management/',
    'https://www.gotfriends.co.il/jobslobby/project-management/',
    'https://www.gotfriends.co.il/jobslobby/program-management/',
    'https://www.gotfriends.co.il/jobslobby/management/project-manager/',
    'https://www.gotfriends.co.il/jobslobby/management/program-manager/',
    'https://www.gotfriends.co.il/jobslobby/management/pmo/',
    'https://www.gotfriends.co.il/jobslobby/management/release-manager/',
    'https://www.gotfriends.co.il/jobslobby/management/professional-services/',
]

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    for url in CANDIDATE_URLS:
        try:
            page.goto(url, timeout=20000, wait_until='domcontentloaded')
            page.wait_for_timeout(2000)
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            cards = soup.select('a[class^="position"]')
            results.append(f"{len(cards):3d} משרות  →  {url}")
        except Exception as e:
            results.append(f"  ERROR  →  {url}  ({e})")

    browser.close()

output = '\n'.join(results)
print(output)
with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write(output)
