import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv, time, random, os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

RECRUITERS_FILE = r"C:\Users\Shaul\Documents\job-search\all_recruiters_merged.csv"
PROGRESS_FILE   = r"C:\Users\Shaul\Documents\job-search\outreach_done.txt"
MAX_PER_DAY = 150

MESSAGE_SUBJECT = "25 Years in QA & Program Management - Worth a 15-Minute Call?"

CV_IMPACT_LINK = "https://drive.google.com/file/d/1h3PObY_Ap_6HLtNB0AApvWzR1rUu-qii/view?usp=sharing"
CV_PM_LINK  = "https://drive.google.com/file/d/1B3SmlKLlDuCRVxC_jG7f4WeMJnTW4cUK/view?usp=sharing"
CV_QA_LINK     = "https://drive.google.com/file/d/1HDIF60dWsUFVc3lBpsH3l--Bjy46We5t/view?usp=sharing"

# Full message — sent when "Message" button is available (Open Profile)
FULL_MESSAGE = """\
Hi {first},

I'm Shaul Mano - Senior Program Manager & QA Leader with 25+ years of experience at RSA and Symantec.

I'd love to explore if there's anything relevant open. I've included my CVs - feel free to share whichever fits best:

Impact Summary: {cv_impact}
Program Management: {cv_pm}
QA Leadership: {cv_qa}

I'd welcome a quick 15-minute call if anything looks like a fit.

Best,
Shaul Mano
052-4304747"""

# Short note — sent with connection request (300 char max)
CONNECT_NOTE = (
    "Hi {first}, I'm Shaul Mano — 25+ years leading QA & Program Management "
    "at RSA and Symantec. If you work with hi-tech companies in Israel and have "
    "relevant roles, I'd love to connect and share my CV. Let's talk!"
)


def is_session_alive(driver):
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False

def reconnect(retries=5):
    for attempt in range(1, retries + 1):
        try:
            print(f"  Reconnecting to Chrome (attempt {attempt}/{retries})...")
            driver = init_browser()
            _ = driver.current_url
            print("  Reconnected.")
            return driver
        except Exception as e:
            print(f"  Failed: {e}")
            time.sleep(5)
    raise RuntimeError("Could not reconnect to Chrome after multiple attempts.")

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
    options.add_argument("--headless=new")
    options.add_argument(r"--user-data-dir=C:\Users\Shaul\AppData\Local\ChromeOutreach")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-default-apps")
    options.add_argument("--remote-debugging-port=0")
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


def send_direct_message(driver, first):
    try:
        # wait for the message page to load
        time.sleep(3)

        # try multiple selectors for the message input box
        textarea = None
        for sel in [
            "//div[contains(@class,'msg-overlay')]//div[@role='textbox']",
            "//div[contains(@class,'msg-overlay')]//div[@contenteditable='true']",
            "//div[contains(@class,'msg-form')]//div[@role='textbox']",
            "//div[contains(@class,'msg-form')]//div[@contenteditable='true']",
            "//div[@role='textbox' and @contenteditable='true']",
            "//div[@contenteditable='true']",
        ]:
            try:
                textarea = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.XPATH, sel))
                )
                if textarea.is_displayed():
                    break
                textarea = None
            except:
                continue

        if textarea is None:
            return "Message failed: textarea not found"

        # fill subject if field exists
        try:
            subject_field = driver.find_element(By.XPATH,
                "//input[contains(@id,'subject') or contains(@placeholder,'Subject') or contains(@name,'subject')]"
            )
            type_text(driver, subject_field, MESSAGE_SUBJECT)
            time.sleep(0.3)
        except:
            pass

        driver.execute_script("arguments[0].click();", textarea)
        time.sleep(0.5)
        msg = FULL_MESSAGE.format(first=first, cv_impact=CV_IMPACT_LINK, cv_pm=CV_PM_LINK, cv_qa=CV_QA_LINK)
        type_text(driver, textarea, msg)
        time.sleep(0.5)

        # find send button
        send_btn = None
        for sel in [
            "//button[contains(@class,'msg-form__send-button')]",
            "//button[@type='submit' and contains(@class,'send')]",
            "//button[.//span[text()='Send']]",
            "//button[.//span[contains(text(),'Send')]]",
        ]:
            try:
                send_btn = driver.find_element(By.XPATH, sel)
                break
            except:
                continue

        if send_btn is None:
            return "Message failed: send button not found"

        driver.execute_script("arguments[0].click();", send_btn)
        return "Message sent"
    except Exception as e:
        return f"Message failed: {e}"


def _cdp_click_text(driver, *texts):
    """Find a visible element matching any of the given texts and CDP-click it."""
    coords = driver.execute_script("""
        var texts = arguments[0];
        for (var el of document.querySelectorAll('button, div, span')) {
            var t = (el.innerText || el.textContent || '').trim();
            if (texts.indexOf(t) === -1) continue;
            var r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            return {x: r.left + r.width / 2, y: r.top + r.height / 2};
        }
        return null;
    """, list(texts))
    if not coords:
        return False
    cdp_click(driver, coords['x'], coords['y'])
    return True


def _fill_and_send(driver, note):
    time.sleep(0.5)

    # click "Add a note" via CDP — same trust requirement as Connect button
    coords = driver.execute_script("""
        var btn = document.querySelector('button[aria-label="Add a note"]')
                  || document.querySelector('button[aria-label="הוסף הערה"]');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return null;
        return {x: r.left + r.width / 2, y: r.top + r.height / 2};
    """)
    if not coords:
        return "Connect sent (no note - dialog not found)"
    cdp_click(driver, coords['x'], coords['y'])

    time.sleep(2)

    # find textarea — wait up to 10s
    ta = None
    for sel in [
        "//textarea[@name='message']",
        "//textarea",
        "//div[@contenteditable='true' and @role='textbox']",
        "//div[@contenteditable='true']",
    ]:
        try:
            el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, sel)))
            if el.is_displayed():
                ta = el
                break
        except:
            continue

    if ta is None:
        return "Connect sent (no note - textarea not found)"

    # use execCommand to insert text — bypasses Hebrew keyboard layout
    try:
        driver.execute_script("""
            arguments[0].focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            document.execCommand('insertText', false, arguments[1]);
        """, ta, note)
        time.sleep(0.5)
    except:
        return "Connect sent (no note - could not type)"

    # click Send
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((
            By.XPATH,
            "//button[normalize-space(.)='Send' or normalize-space(.)='שלח']"
        ))).click()
        return "Connect sent"
    except:
        return "Could not click Send"


def _find_connect_el(driver):
    """Return the Connect element near the top of the page, or None."""
    return driver.execute_script("""
        var words = ['connect', 'התחבר'];
        var candidates = Array.from(document.querySelectorAll('span, button, div'));
        for (var el of candidates) {
            var t = (el.textContent || '').trim().toLowerCase();
            if (words.indexOf(t) === -1) continue;
            var rect = el.getBoundingClientRect();
            if (rect.top <= 0 || rect.top > 500 || rect.width === 0 || rect.height === 0) continue;
            if (el.closest('a')) continue;       // skip link elements
            if (el.closest('aside')) continue;   // skip sidebar
            if (el.closest('nav')) continue;     // skip navigation bar
            if (rect.top < 100) continue;        // skip top nav area
            return el;
        }
        return null;
    """)


def _find_more_el(driver):
    """Return the More button near the top of the page, or None."""
    return driver.execute_script("""
        var candidates = Array.from(document.querySelectorAll('button, div'));
        for (var el of candidates) {
            var t = (el.textContent || '').trim().toLowerCase();
            if (t !== 'more' && t !== 'עוד') continue;
            var rect = el.getBoundingClientRect();
            if (rect.top <= 0 || rect.top > 500 || rect.width === 0) continue;
            return el;
        }
        return null;
    """)


def cdp_click(driver, x, y):
    """Dispatch a trusted mouse click via Chrome DevTools Protocol."""
    for event in ('mouseMoved', 'mousePressed', 'mouseReleased'):
        driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
            'type': event,
            'x': x, 'y': y,
            'button': 'none' if event == 'mouseMoved' else 'left',
            'clickCount': 0 if event == 'mouseMoved' else 1,
            'modifiers': 0,
            'pointerType': 'mouse',
        })
    time.sleep(0.1)


def send_connect_request(driver, first, profile_url):
    note = CONNECT_NOTE.format(first=first)

    # wait for the profile action bar to load (More button is a reliable indicator)
    try:
        WebDriverWait(driver, 10).until(lambda d: d.execute_script("""
            for (var el of document.querySelectorAll('button, div, span')) {
                var t = (el.textContent || '').trim().toLowerCase();
                if (t !== 'more' && t !== 'עוד') continue;
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && !el.closest('nav')) return true;
            }
            return false;
        """))
    except:
        pass

    # Single step: find Connect within first 700px of page (profile area only),
    # scroll it into view instantly, then return coordinates from same script.
    # window.scrollTo(0,0) done above so r.top == absolute page position before scroll.
    coords = driver.execute_script("""
        function isConnect(t) {
            var lo = t.toLowerCase();
            return lo === 'connect' || lo === 'התחבר' ||
                   lo.endsWith(' connect') || lo.endsWith(' התחבר');
        }
        for (var el of document.querySelectorAll('div, span, button, a')) {
            var t = (el.innerText || el.textContent || '').trim();
            if (!isConnect(t)) continue;
            if (el.closest('nav') || el.closest('aside')) continue;
            var r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            if (r.top < 70) continue;           // skip sticky nav bar
            if (r.top > 700) continue;          // skip "People similar to" section
            el.scrollIntoView({block: 'center', behavior: 'instant'});
            r = el.getBoundingClientRect();     // re-read after instant scroll
            return {x: r.left + r.width / 2, y: r.top + r.height / 2,
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    """)

    if not coords:
        return "No Connect button"

    print(f"  clicking Connect at {coords}")

    # check if element is an A-link (href-based connect)
    href = driver.execute_script("""
        var el = document.elementFromPoint(arguments[0], arguments[1]);
        if (!el) return null;
        var a = el.closest('a');
        return a ? a.getAttribute('href') : null;
    """, coords['x'], coords['y'])

    if href and ('invite' in href or 'connect' in href.lower()):
        # navigate directly to the custom-invite URL
        full_url = ('https://www.linkedin.com' + href) if href.startswith('/') else href
        print(f"  link-based connect → {full_url}")
        driver.get(full_url)
        # wait for "Add a note" button to appear (up to 15 sec) before interacting
        try:
            WebDriverWait(driver, 15).until(lambda d: d.execute_script(
                "return !!document.querySelector('button[aria-label=\"Add a note\"]')"
                " || !!document.querySelector('button[aria-label=\"הוסף הערה\"]');"
            ))
        except:
            return "Connect link - dialog not found"
        return _fill_and_send(driver, note)

    # standard CDP click for button/div Connect elements
    time.sleep(0.5)
    cdp_click(driver, coords['x'], coords['y'])

    # wait up to 6 sec for the "Add a note" dialog to appear
    dialog_appeared = False
    for _ in range(12):
        time.sleep(0.5)
        in_dom = driver.execute_script(
            "return !!document.querySelector('button[aria-label=\"Add a note\"]')"
            " || !!document.querySelector('button[aria-label=\"הוסף הערה\"]');"
        )
        if in_dom:
            dialog_appeared = True
            break

    if not dialog_appeared:
        return "Connect clicked - no dialog (auto-sent or wrong element)"

    return _fill_and_send(driver, note)


def focus_window(driver):
    """Bring the Chrome window to the foreground."""
    try:
        driver.switch_to.window(driver.current_window_handle)
        driver.maximize_window()
    except:
        pass


def process_profile(driver, url, first):
    focus_window(driver)
    driver.get(url)
    time.sleep(random.uniform(3, 5))

    # skip if already a 1st-degree connection
    is_connected = bool(driver.find_elements(
        By.XPATH, "//span[contains(@class,'dist-value') and text()='1st'] | "
                  "//span[contains(@class,'distance-badge') and contains(.,'1st')]"
    ))
    if is_connected:
        return "Skipped - already connected"

    return send_connect_request(driver, first, url)


def main():
    # --url MODE: test a single specific profile
    url_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == '--url'), None)
    if url_arg:
        print(f"*** URL MODE — testing: {url_arg} ***\n")
        driver = init_browser()
        print(f"Connected to browser. URL: {driver.current_url}\n")
        result = process_profile(driver, url_arg.strip(), 'Test')
        print(f"Result: {result}")
        driver.quit()
        return

    test_mode = '--test' in sys.argv

    driver = init_browser()
    print(f"Connected to browser. URL: {driver.current_url}\n")

    day = 1
    total_sent = 0

    try:
        while True:
            with open(RECRUITERS_FILE, encoding='utf-8-sig') as f:
                recruiters = list(csv.DictReader(f))

            done_urls = load_done()
            pending   = [r for r in recruiters if r['linkedinProfileUrl'].strip() not in done_urls]

            if not pending:
                print("\n=== All profiles done! ===")
                break

            if test_mode:
                batch = pending[:3]
            else:
                batch = pending[:MAX_PER_DAY]

            print(f"\n=== Day {day} | Sending {len(batch)} | Remaining after: {len(pending)-len(batch)} ===\n")

            messages = 0
            connects = 0

            for i, r in enumerate(batch, 1):
                url   = r['linkedinProfileUrl'].strip()
                first = (r.get('firstName', '') or '').strip().split()[0] if r.get('firstName', '').strip() else 'there'
                last  = (r.get('lastName',  '') or '').strip().split()[0] if r.get('lastName',  '').strip() else ''

                print(f"[{i}/{len(batch)}] {first} {last} ... ", end='', flush=True)

                try:
                    if not is_session_alive(driver):
                        driver = reconnect()
                    result = process_profile(driver, url, first)
                except Exception as e:
                    err = str(e)
                    if 'invalid session' in err.lower() or 'no such session' in err.lower() or 'session deleted' in err.lower() or 'chrome not reachable' in err.lower() or not err.strip():
                        print(f"Session lost, reconnecting...")
                        try:
                            driver = reconnect()
                            result = process_profile(driver, url, first)
                        except Exception as e2:
                            result = f"Error: {e2}"
                    else:
                        result = f"Error: {e}"

                mark_done(url, result)

                if 'Message sent' in result:
                    messages += 1
                elif 'Connect sent' in result:
                    connects += 1

                print(result)

                if i < len(batch):
                    wait = random.uniform(60, 420)
                    for remaining in range(int(wait), 0, -1):
                        m, s = divmod(remaining, 60)
                        print(f"\r  Next in: {m:02d}:{s:02d}", end='', flush=True)
                        time.sleep(1)
                    print("\r                    \r", end='', flush=True)

            total_sent += connects + messages
            print(f"\n=== Day {day} done | Sent: {connects+messages} | Total so far: {total_sent} ===")

            if len(pending) - len(batch) == 0:
                print("All profiles completed!")
                break

            # Wait until midnight with countdown
            import datetime
            now = datetime.datetime.now()
            midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            print(f"\nNext batch at midnight ({midnight.strftime('%Y-%m-%d 00:00')})")
            while True:
                remaining = midnight - datetime.datetime.now()
                if remaining.total_seconds() <= 0:
                    break
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m, s   = divmod(rem, 60)
                print(f"\r  Next batch in: {h:02d}:{m:02d}:{s:02d}", end='', flush=True)
                time.sleep(1)
            print("\r  Starting next batch...                ")
            day += 1

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        print(f"\nTotal sent: {total_sent}")
        driver.quit()


if __name__ == '__main__':
    main()
