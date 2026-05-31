import sys
sys.stdout.reconfigure(encoding='utf-8')
import re
from selenium import webdriver
from selenium.webdriver.common.by import By

def connect():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

def clean_name(raw):
    name = re.split(r'[•·\U0001F535\U0001F534]', raw)[0]
    name = re.sub(r'\b(1st|2nd|3rd)\b', '', name)
    return name.strip()

driver = connect()
print("Page:", driver.current_url)

links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/in/"]')
print(f"Total /in/ links: {len(links)}")

seen = set()
for link in links:
    href = (link.get_attribute('href') or '').split('?')[0].rstrip('/')
    if not href or href in seen or '/in/' not in href:
        continue
    text = link.text.strip()
    if len(text) < 5:
        continue
    seen.add(href)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = clean_name(lines[0]) if lines else ''
    title_company = lines[1] if len(lines) > 1 else ''
    print(f"  Name: {name}")
    print(f"  Title/Company: {title_company}")
    print()
