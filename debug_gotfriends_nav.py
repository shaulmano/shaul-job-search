from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    page.goto('https://www.gotfriends.co.il/jobs/', timeout=30000, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')
links = []
for a in soup.find_all('a', href=True):
    href = a.get('href', '')
    if '/jobslobby/' in href and href not in links:
        links.append(href)

output = '\n'.join(sorted(set(links)))
with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write(output)
print(f"נכתבו {len(links)} קישורים")
