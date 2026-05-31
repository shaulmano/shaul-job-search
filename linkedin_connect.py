import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv, time, random, os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

RECRUITERS_FILE = r"C:\Users\Shaul\Documents\job-search\recruiters_new.csv"
PROGRESS_FILE   = r"C:\Users\Shaul\Documents\job-search\connect_done.txt"

MAX_PER_RUN = 20  # LinkedIn allows ~100/week — stay safe with 20/day

NOTE = (
    "Hi {first},\n"
    "I'm Shaul — actively looking for my next role as a Senior Program Manager / QA Leader.\n"
    "Happy to send my CV if anything fits.\n"
    "Let's connect!"
)

# Best, Shaul Mano | 052-4304747 | https://linkedin.com/in/shaul-mano-0a7a392/


def load_done():
    if not os.path.exists(PROGRESS_FILE):
        return set()
    with open(PROGRESS_FILE, encoding='utf-8') as f:
        return set(line.split(' | ')[0].strip() for line in f if line.strip())


def mark_done(url, result):
    with open(PROGRESS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{url} | {result}\n")


def init_browser():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)


def send_connect(driver, profile_url, first):
    driver.get(profile_url)
    time.sleep(random.uniform(3, 5))

    note_text = NOTE.format(first=first)
    connected = False

    # try direct Connect button
    try:
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//button[.//span[text()='Connect']]")
        ))
        btn.click()
        connected = True
    except:
        pass

    # try Connect inside More dropdown
    if not connected:
        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(
                (By.XPATH, "//button[.//span[text()='More']]")
            )).click()
            time.sleep(1)
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(
                (By.XPATH, "//span[text()='Connect']/ancestor::li | //span[text()='Connect']/ancestor::div[@role='option']")
            )).click()
            connected = True
        except:
            pass

    if not connected:
        return "No Connect button"

    time.sleep(2)

    # click Add a note
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//button[.//span[text()='Add a note']]")
        )).click()
        time.sleep(1)
    except:
        pass

    # fill the note
    try:
        textarea = WebDriverWait(driver, 5).until(EC.presence_of_element_located(
            (By.XPATH, "//textarea[@name='message']")
        ))
        textarea.click()
        textarea.clear()
        for ch in note_text:
            textarea.send_keys(ch)
            time.sleep(random.uniform(0.02, 0.05))
    except:
        return "Could not fill note"

    time.sleep(0.5)

    # click Send
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(
            (By.XPATH, "//button[.//span[text()='Send']]")
        )).click()
        return "Sent"
    except:
        return "Could not click Send"


def main():
    with open(RECRUITERS_FILE, encoding='utf-8-sig') as f:
        recruiters = list(csv.DictReader(f))

    done_urls = load_done()
    pending   = [r for r in recruiters if r['linkedinProfileUrl'].strip() not in done_urls]

    test_mode = '--test' in sys.argv
    if test_mode:
        pending = pending[:3]
        print("*** TEST MODE — 3 profiles only ***\n")

    print(f"Total profiles : {len(recruiters)}")
    print(f"Already done   : {len(done_urls)}")
    print(f"Remaining      : {len(pending)}")
    print(f"Sending today  : up to {MAX_PER_RUN}")
    print()
    input("Press Enter to start...")

    driver = init_browser()
    print(f"Connected to browser. URL: {driver.current_url}\n")

    sent  = 0
    batch = pending[:MAX_PER_RUN]

    try:
        for i, r in enumerate(batch, 1):
            url   = r['linkedinProfileUrl'].strip()
            first = r['firstName'].strip()
            last  = r['lastName'].strip()

            print(f"[{i}/{len(batch)}] {first} {last} ... ", end='', flush=True)
            result = send_connect(driver, url, first)
            mark_done(url, result)

            if result == "Sent":
                sent += 1
                print("Connected!")
            else:
                print(result)

            time.sleep(random.uniform(25, 40))

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        print(f"\n=== DONE ===")
        print(f"Sent today: {sent}")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == '__main__':
    main()
