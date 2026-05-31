import sys
sys.stdout.reconfigure(encoding='utf-8')

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD

TEST_URL = "https://www.linkedin.com/in/moria-david-1b401216a"

options = webdriver.ChromeOptions()
options.add_argument('--start-maximized')
options.add_argument(r'--user-data-dir=C:\Users\Shaul\AppData\Local\Google\Chrome\User Data')
options.add_argument('--profile-directory=Default')
driver = webdriver.Chrome(options=options)

try:
    # Already logged in via existing profile — go straight to LinkedIn
    driver.get('https://www.linkedin.com/feed')
    time.sleep(4)
    print(f"דף נוכחי: {driver.current_url}")

    if 'login' in driver.current_url:
        print("לא מחובר — מתחבר ידנית בדפדפן ולחץ Enter.")
        input(">> Enter: ")

    # Go to profile
    print(f"\nנכנס לפרופיל: {TEST_URL}")
    driver.get(TEST_URL)
    time.sleep(4)

    # Click Contact info
    print("מחפש Contact info...")
    try:
        contact_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@href,'detail/contact-info')]|//span[text()='Contact info']/ancestor::a|//a[contains(.,'Contact info')]")
        ))
        contact_btn.click()
        time.sleep(2)

        print("\n=== תוכן Contact info ===\n")
        # Get all text in the modal
        modal = driver.find_element(By.XPATH, "//div[@role='dialog']|//div[contains(@class,'pv-contact-info')]")
        print(modal.text)

    except Exception as e:
        print(f"לא נמצא Contact info: {e}")
        print("\nכל הלינקים בדף:")
        for a in driver.find_elements(By.TAG_NAME, 'a'):
            txt = a.text.strip()
            href = a.get_attribute('href') or ''
            if 'contact' in href.lower() or 'contact' in txt.lower():
                print(f"  {txt!r} → {href}")

    input("\nPress Enter to close...")

finally:
    driver.quit()
