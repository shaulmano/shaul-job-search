from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

url = 'https://www.gotfriends.co.il/jobs/?q=QA+Manager'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page.goto(url, timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(4000)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')

print("=== 3 כרטיסיות משרה ראשונות ===")
for card in soup.select('a[class^="position"]')[:3]:
    print(f"href: {card.get('href', 'NONE')}")
    num = card.select_one('.career_num')
    title = card.get_text(strip=True).replace(num.get_text(strip=True) if num else '', '').strip()
    print(f"title: {title}")
    print("---")
