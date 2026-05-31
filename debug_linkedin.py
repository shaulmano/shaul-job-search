import sys
sys.stdout.reconfigure(encoding='utf-8')

import time
from selenium import webdriver
from selenium.webdriver.common.by import By

TEST_URL = "https://www.linkedin.com/in/batel-zilbershmidt-84504183"

options = webdriver.ChromeOptions()
options.add_argument('--start-maximized')
driver = webdriver.Chrome(options=options)

driver.get("https://www.linkedin.com/login")
print("התחבר ל-LinkedIn בדפדפן, אז חזור לכאן ולחץ Enter.")
input(">> Enter: ")

driver.get(TEST_URL)
time.sleep(5)

# Click "More" button
print("מחפש כפתור More...")
more_btns = driver.find_elements(By.XPATH, "//button[.//span[normalize-space()='More']]")
print(f"נמצאו {len(more_btns)} כפתורי More")

if more_btns:
    print("לוחץ על More הראשון...")
    more_btns[0].click()
    time.sleep(2)

    print("\n=== כל האלמנטים לאחר פתיחת More ===\n")
    # Look for dropdown items
    for tag in ['li', 'div', 'span', 'a']:
        items = driver.find_elements(By.TAG_NAME, tag)
        for el in items:
            role = el.get_attribute('role') or ''
            text = el.text.strip()[:60]
            if role in ('option', 'menuitem', 'listitem') or 'Connect' in text:
                print(f"<{tag}> role={role!r} text={text!r}")

input("\nPress Enter to close...")
driver.quit()
