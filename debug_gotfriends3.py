from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

urls = [
    'https://www.gotfriends.co.il/jobslobby/qa/qa-team-leader/',
    'https://www.gotfriends.co.il/jobslobby/qa/',
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    results = []
    for url in urls:
        page.goto(url, timeout=30000, wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.select('a[class^="position"]')
        results.append(f"\n=== {url} ===")
        results.append(f"נמצאו {len(cards)} משרות")
        for card in cards[:5]:
            num_el = card.select_one('.career_num')
            num_text = num_el.get_text(strip=True) if num_el else ''
            title = card.get_text(strip=True).replace(num_text, '').strip()
            results.append(f"  - {title}")

    browser.close()

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print("נכתב ל debug_output.txt")
