import sys
sys.stdout.reconfigure(encoding='utf-8')
import time
from selenium import webdriver

def connect():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

driver = connect()
driver.get("https://www.linkedin.com/mynetwork/invite-connect/connections/")
time.sleep(4)

print("URL:", driver.current_url)

selectors = [
    'li.mn-connection-card',
    'li[class*="connection"]',
    'li[class*="mn-"]',
    'a[href*="/in/"]',
    '[data-view-name*="connection"]',
]

for sel in selectors:
    els = driver.find_elements('css selector', sel)
    print(f"{sel}: {len(els)}")

lis = driver.find_elements('css selector', 'li')
print(f"\nTotal li: {len(lis)}")
classes = set()
for li in lis[:50]:
    c = li.get_attribute('class') or ''
    if c:
        classes.add(c[:80])
print("Li classes sample:")
for c in list(classes)[:15]:
    print(f"  {c}")

links = driver.find_elements('css selector', 'a[href*="/in/"]')
print(f"\n/in/ links: {len(links)}")
for l in links[:5]:
    href = l.get_attribute('href') or ''
    print(f"  {href[:80]}")
    print(f"  text: {l.text.encode('ascii', errors='replace').decode()[:60]!r}")
