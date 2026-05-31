import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def connect():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

driver = connect()
wait = WebDriverWait(driver, 15)

driver.get("https://www.linkedin.com/messaging/")
time.sleep(4)

# Find and use search box
inputs = driver.find_elements(By.TAG_NAME, 'input')
print(f"All inputs on page: {len(inputs)}")
for inp in inputs:
    print(f"  placeholder='{inp.get_attribute('placeholder')}' | aria-label='{inp.get_attribute('aria-label')}' | class='{inp.get_attribute('class')[:50]}'")

# Try to search
try:
    search_box = wait.until(EC.presence_of_element_located((
        By.CSS_SELECTOR, 'input[placeholder*="Search"], input[aria-label*="Search"]'
    )))
    search_box.click()
    time.sleep(1)
    search_box.send_keys('Thanks for connecting')
    search_box.send_keys(Keys.RETURN)
    print("\nSearched! Waiting 4 seconds...")
    time.sleep(4)
except Exception as e:
    print(f"Search failed: {e}")

# Now dump what we see
print(f"\nCurrent URL: {driver.current_url}")
all_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/in/"]')
print(f"\nAll /in/ links: {len(all_links)}")
for l in all_links[:20]:
    print(f"  href: {l.get_attribute('href')[:80]}")
    print(f"  text: {l.text[:50]!r}")
    print()

# Check for list items
lis = driver.find_elements(By.CSS_SELECTOR, 'li')
print(f"\nTotal li elements: {len(lis)}")

# Print all classes that contain 'conversation' or 'msg'
els = driver.find_elements(By.XPATH, '//*[contains(@class,"conversation") or contains(@class,"msg-")]')
classes = set()
for el in els:
    cls = el.get_attribute('class') or ''
    for c in cls.split():
        if 'conversation' in c or 'msg-' in c:
            classes.add(c)
print(f"\nRelevant classes: {sorted(classes)}")
