import sys
sys.stdout.reconfigure(encoding='utf-8')

import time, random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TEST_FIRST = "Uzi"
TEST_LAST  = "Shabat"

MESSAGE = """\
Hi {first},

I hope you're doing well. We're connected on LinkedIn and I wanted to reach out directly.

I'm currently looking for my next role as a Senior Program Manager or QA Leader, with 25+ years of experience at companies like RSA and Symantec.

Is there anything open at your company that might be a fit? I would love it if you could forward my CV to your recruiting team.

Happy to send my CV anytime.

Thanks,
Shaul Mano"""

def connect_browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--user-data-dir=C:\\ChromeBot")
    options.add_argument("--window-position=-32000,0")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)

def type_text(driver, element, text):
    driver.execute_script("""
        arguments[0].focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, arguments[1]);
    """, element, text)

def send_message(driver, first, last):
    wait = WebDriverWait(driver, 10)
    driver.get("https://www.linkedin.com/feed/")
    time.sleep(3)
    if 'feed' not in driver.current_url:
        print("ERROR: Not logged in!")
        return

    driver.get("https://www.linkedin.com/messaging/")
    time.sleep(3)

    compose_btn = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//button[contains(@class,'msg-conversations-container__compose-btn') or normalize-space()='Compose a new message']")
    ))
    compose_btn.click()
    time.sleep(2)

    to_field = wait.until(EC.presence_of_element_located(
        (By.XPATH, "//input[contains(@class,'msg-connections-typeahead__search-field') or @placeholder='Type a name or multiple names']")
    ))
    to_field.send_keys(f"{first} {last}")
    time.sleep(2)

    result = wait.until(EC.presence_of_element_located(
        (By.XPATH, "//li[contains(@class,'msg-connections-typeahead__search-result')]")
    ))
    driver.execute_script("arguments[0].click();", result)
    time.sleep(1)

    msg_box = wait.until(EC.presence_of_element_located(
        (By.XPATH, "//div[@role='textbox' and @contenteditable='true']")
    ))
    type_text(driver, msg_box, MESSAGE.format(first=first))
    time.sleep(1)

    sent = driver.execute_script("""
        var btns = document.querySelectorAll('button');
        for (var btn of btns) {
            var cls = btn.className || '';
            var lbl = (btn.getAttribute('aria-label') || '').toLowerCase();
            var txt = (btn.innerText || '').trim().toLowerCase();
            if (cls.includes('send') || lbl.includes('send') || txt === 'send') {
                btn.click();
                return btn.className;
            }
        }
        return null;
    """)
    if sent:
        print(f"Sent to {first} {last}!")
    else:
        print("ERROR: Send button not found")

driver = connect_browser()
print("Browser opened (off-screen)")
send_message(driver, TEST_FIRST, TEST_LAST)
print("Done. Closing in 5 seconds...")
time.sleep(5)
driver.quit()
