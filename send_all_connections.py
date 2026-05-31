import sys
sys.stdout.reconfigure(encoding='utf-8')

import time, random, csv, os, re
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DAILY_LIMIT  = 20
SOURCE_FILE  = r"C:\Users\Shaul\Desktop\linkedin\pending_to_review.csv"

MESSAGE = """\
Hi {first},

I hope you're doing well. We're connected on LinkedIn and I wanted to reach out directly.

I'm currently looking for my next role as a Senior Program Manager or QA Leader, with 25+ years of experience at companies like RSA and Symantec.

Is there anything open at your company that might be a fit? I would love it if you could forward my CV to your recruiting team.

Happy to send my CV anytime.

Thanks,
Shaul Mano"""


def load_rows():
    with open(SOURCE_FILE, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f)), csv.DictReader(open(SOURCE_FILE, encoding='utf-8-sig')).fieldnames

def save_rows(rows, fieldnames):
    if 'status' not in fieldnames:
        fieldnames = fieldnames + ['status', 'dateSent']
    with open(SOURCE_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

def get_pending(rows):
    return [r for r in rows if r.get('status', '') != 'sent']

def sent_today(rows):
    today = str(date.today())
    return sum(1 for r in rows if r.get('status') == 'sent' and r.get('dateSent') == today)

def connect_browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--user-data-dir=C:\\ChromeBot")
    options.add_argument("--window-position=-32000,0")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)

def login(driver):
    driver.get('https://www.linkedin.com/feed/')
    time.sleep(4)
    if any(x in driver.current_url for x in ['feed', 'mynetwork', 'jobs', 'messaging']):
        print("Already logged in.")
        return
    print(f"Not logged in! URL: {driver.current_url}")

def type_text(driver, element, text):
    driver.execute_script("""
        arguments[0].focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, arguments[1]);
    """, element, text)

def send_message(driver, first, last):
    wait = WebDriverWait(driver, 10)
    try:
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
        to_field.send_keys(f"{first} {last}".strip())
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
        return 'sent' if sent else 'error: send button not found'

    except Exception as e:
        return f'error: {e}'


def main():
    rows, fieldnames = load_rows()
    if 'status' not in fieldnames:
        fieldnames = list(fieldnames) + ['status', 'dateSent']
    for r in rows:
        r.setdefault('status', '')
        r.setdefault('dateSent', '')

    already_today = sent_today(rows)
    remaining_today = DAILY_LIMIT - already_today
    pending = get_pending(rows)

    print(f"Total: {len(rows)} | Sent: {len(rows)-len(pending)} | Remaining: {len(pending)}")
    print(f"Sent today: {already_today} | Sending now: {min(remaining_today, len(pending))}")

    if not pending:
        print("All done!")
        return

    if remaining_today <= 0:
        print(f"Already sent {already_today} today. Waiting until tomorrow...")
        time.sleep(23 * 3600)
        os.execv(sys.executable, [sys.executable] + sys.argv)
        return

    random.shuffle(pending)
    batch = pending[:remaining_today]

    print("\nSending to:")
    for i, r in enumerate(batch, 1):
        print(f"  [{i}] {r['firstName']} {r['lastName']}")
    print()

    driver = connect_browser()
    login(driver)

    sent_count = 0
    try:
        for i, r in enumerate(batch, 1):
            first, last = r['firstName'], r['lastName']
            print(f"[{i}/{len(batch)}] {first} {last} ... ", end='', flush=True)
            result = send_message(driver, first, last)

            for row in rows:
                if row['firstName'] == first and row['lastName'] == last:
                    row['status'] = result
                    row['dateSent'] = str(date.today())
                    break
            save_rows(rows, fieldnames)

            if result == 'sent':
                sent_count += 1
                print("Sent!")
            else:
                print(result)

            if i < len(batch):
                delay = int(random.uniform(1200, 2700))
                for remaining in range(delay, 0, -1):
                    m, s = divmod(remaining, 60)
                    print(f"\r  Next message in: {m:02d}:{s:02d}", end='', flush=True)
                    time.sleep(1)
                print("\r                              \r", end='', flush=True)

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        print(f"\n=== Done: {sent_count}/{len(batch)} sent ===")
        try:
            driver.quit()
            print("Browser closed.")
        except Exception:
            pass
        print("Waiting until tomorrow...")
        time.sleep(23 * 3600)
        print("Restarting...")
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == '__main__':
    main()
