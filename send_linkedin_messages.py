import sys
sys.stdout.reconfigure(encoding='utf-8')

import time, random, csv, os
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DAILY_LIMIT = 20
PROGRESS_FILE = r"C:\Users\Shaul\Documents\job-search\friends_outreach_progress.csv"

CONTACTS = [
    ("Limor",     "Cohen",                "https://www.linkedin.com/in/limor-cohen-83544b8"),
    ("Abhishek",  "Devendraiah",          "https://www.linkedin.com/in/abhishekhd"),
    ("Allon",     "Zygiel",               "https://www.linkedin.com/in/allon-zygiel-93b76949"),
    ("Lydia",     "Mor",                  "https://www.linkedin.com/in/lydiamor"),
    ("Shahar",    "Man",                  "https://www.linkedin.com/in/shahar-man"),
    ("Dudi",      "Vaanunu",              "https://www.linkedin.com/in/dudi-vaanunu"),
    ("Shlomi",    "Matza",                "https://www.linkedin.com/in/shlomi-matza"),
    ("Avia",      "Gottfrid",             "https://www.linkedin.com/in/avia-gottfrid"),
    ("Sharon",    "Schusheim",            "https://www.linkedin.com/in/sharon-schusheim"),
    ("Eran",      "Kinsbruner",           "https://www.linkedin.com/in/eran-kinsbruner"),
    ("Eran",      "Damelin",              "https://www.linkedin.com/in/eran-damelin"),
    ("Alexander", "Haye",                 "https://www.linkedin.com/in/alexander-haye"),
    ("Galit",     "Zvi Bersuc",           "https://www.linkedin.com/in/galit-zvi-bersuc"),
    ("Tali",      "Shem Tov",             "https://www.linkedin.com/in/tali-shem-tov"),
    ("Vladyslav", "Didyk",                "https://www.linkedin.com/in/vladyslav-didyk"),
    ("Uzi",       "Shabat",               "https://www.linkedin.com/in/uzi-shabat"),
    ("Nadav",     "Sinai",                "https://www.linkedin.com/in/nadav-sinai"),
    ("Adam",      "Cheriki",              "https://www.linkedin.com/in/adam-cheriki"),
    ("Yakov",     "Gavriel",              "https://www.linkedin.com/in/yakov-gavriel"),
    ("Limor",     "Elhayani",             "https://www.linkedin.com/in/limor-elhayani"),
    ("Elli",      "Shlomo",               "https://www.linkedin.com/in/elli-shlomo"),
    ("Igor",      "Diamandi",             "https://www.linkedin.com/in/igor-diamandi"),
    ("Maytal",    "Marks",                "https://www.linkedin.com/in/maytal-marks"),
    ("Sagi",      "Trybel",               "https://www.linkedin.com/in/sagi-trybel"),
    ("Sergey",    "Meerovich",            "https://www.linkedin.com/in/sergey-meerovich"),
    ("Rafi",      "Itzhaki",              "https://www.linkedin.com/in/rafi-itzhaki"),
    ("Aliza",     "Oz Pipman",            "https://www.linkedin.com/in/aliza-oz-pipman"),
    ("Kfir",      "Amitai",               "https://www.linkedin.com/in/kfir-amitai"),
    ("Maya",      "Bakshi",               "https://www.linkedin.com/in/maya-bakshi"),
    ("Iren",      "Chestny",              "https://www.linkedin.com/in/iren-chestny"),
    ("Revital",   "Lavi",                 "https://www.linkedin.com/in/revital-lavi"),
    ("Yishai",    "Herman",               "https://www.linkedin.com/in/yishai-herman"),
    ("Tamir",     "Zano",                 "https://www.linkedin.com/in/tamir-zano"),
    ("Paule",     "Tzuker",               "https://www.linkedin.com/in/paule-tzuker"),
    ("Oshrat",    "Sabag",                "https://www.linkedin.com/in/oshrat-sabag"),
    ("Rami",      "Azulay",               "https://www.linkedin.com/in/rami-azulay"),
    ("Ilya",      "Kats",                 "https://www.linkedin.com/in/ilya-kats"),
    ("Alina",     "Rabinovich",           "https://www.linkedin.com/in/alina-rabinovich"),
    ("Orna",      "Dreman",               "https://www.linkedin.com/in/orna-dreman"),
    ("Omri",      "Perek",                "https://www.linkedin.com/in/omri-perek"),
    ("Dror",      "Elad",                 "https://www.linkedin.com/in/dror-elad"),
    ("Efi",       "Neeman",               "https://www.linkedin.com/in/efi-neeman"),
    ("Karin",     "Rein",                 "https://www.linkedin.com/in/karin-rein"),
    ("Merav",     "Dagai",                "https://www.linkedin.com/in/merav-dagai"),
    ("Shaul",     "Ash",                  "https://www.linkedin.com/in/shaul-ash"),
    ("Ewen",      "Fortune",              "https://www.linkedin.com/in/ewen-fortune"),
    ("Gilad",     "Reshetnik",            "https://www.linkedin.com/in/gilad-reshetnik"),
    ("Alon",      "Shiri",                "https://www.linkedin.com/in/alon-shiri"),
    ("Avi",       "Huberman",             "https://www.linkedin.com/in/avi-huberman"),
    ("Lipaz",     "Tzitrinovich Daudi",   "https://www.linkedin.com/in/lipaz-tzitrinovich-daudi"),
    ("Jehonathan","Samuel",               "https://www.linkedin.com/in/jehonathan-samuel"),
    ("Ruthy",     "Yakobowitz-Goldberg",  "https://www.linkedin.com/in/ruthy-yakobowitz-goldberg"),
    ("Michal",    "Sofer Herstein",       "https://www.linkedin.com/in/michal-sofer-herstein"),
    ("Hadas",     "Lahav",                "https://www.linkedin.com/in/hadas-lahav"),
    ("Dror",      "Reifer",               "https://www.linkedin.com/in/dror-reifer"),
    ("Yoseph",    "Reuveni",              "https://www.linkedin.com/in/yoseph-reuveni"),
    ("Vlad",      "Breger",               "https://www.linkedin.com/in/vlad-breger"),
    ("Noam",      "Ruff",                 "https://www.linkedin.com/in/noam-ruff"),
    ("Dominik",   "Klotz",               "https://www.linkedin.com/in/dominik-klotz"),
    ("Eitan",     "Linker",               "https://www.linkedin.com/in/eitan-linker"),
    ("Gil",       "Pal",                  "https://www.linkedin.com/in/gil-pal"),
    # New friends added
    ("Keren",    "Mann-Derey",           "https://www.linkedin.com/in/keren-mann-derey-12a1bb20"),
    ("Meital",   "Burstein",             "https://www.linkedin.com/in/meitalburstein"),
    ("Barak",    "Zigdon",               "https://www.linkedin.com/in/barakzigdon"),
    ("Yoav",     "Gross",                "https://www.linkedin.com/in/yoav-gross-6b18a0128"),
    ("Dan",      "Zaitoun",              "https://www.linkedin.com/in/dan-zaitoun-b8593542"),
    ("Ido",      "Goldberg",             "https://www.linkedin.com/in/idogold"),
    ("Ana",      "Paskal",               "https://www.linkedin.com/in/ana-paskal-4ab7015"),
    ("Motty",    "Alon",                 "https://www.linkedin.com/in/motty-alon"),
    ("Yoav",     "Moran",                "https://www.linkedin.com/in/yoav-moran-23571a1"),
    ("Tzahi",    "Nemet",                "https://www.linkedin.com/in/tzahi-nemet-762b8a45"),
    ("Eyal",     "Gur",                  "https://www.linkedin.com/in/eyal-gur-5006672"),
    ("Sarit",    "Novik",                "https://www.linkedin.com/in/saritnovik"),
    ("Yossi",    "Yakubov",              "https://www.linkedin.com/in/yossiyakubov"),
    ("Ran",      "Adler",                "https://www.linkedin.com/in/ran-adler-86a260b4"),
    ("Isaac",    "Brecher",              "https://www.linkedin.com/in/isaacbrecher"),
    ("Or",       "Carmi",                "https://www.linkedin.com/in/orcarmi"),
    ("Rami",     "Schwartz",             "https://www.linkedin.com/in/ramischwartz"),
    ("Shira",    "Zandani",              "https://www.linkedin.com/in/shira-zandani-a6432911"),
    ("Merav",    "Eshet",                "https://www.linkedin.com/in/merav-eshet"),
    ("Alma",     "Zohar",                "https://www.linkedin.com/in/alma-zohar-700ba229"),
    ("Yariv",    "Amar",                 "https://www.linkedin.com/in/yarivamar"),
    ("Nir",      "Ben Aharon",           "https://www.linkedin.com/in/nir-ben-aharon-3826219"),
    ("Rinat",    "Amar",                 "https://www.linkedin.com/in/rinat-amar1"),
    ("Ilanit",   "Nulman",               "https://www.linkedin.com/in/ilanit-nulman-949892"),
    ("Leonid",   "Suslov",               "https://www.linkedin.com/in/leonidsuslov"),
    ("Yossi",    "Yacov",                "https://www.linkedin.com/in/yossiy"),
    ("Ido",      "Zilberberg",           "https://www.linkedin.com/in/idozilberberg"),
    ("Hadas",    "Raz",                  "https://www.linkedin.com/in/hadas-raz-551535ab"),
    ("Lior",     "Asher",                "https://www.linkedin.com/in/lior-asher-878a483"),
    ("Yoram",    "Goren",                "https://www.linkedin.com/in/yoram-goren-48925b"),
]

MESSAGE = """\
Hi {first},

I hope you're doing well. We're connected on LinkedIn and I wanted to reach out directly.

I'm currently looking for my next role as a Senior Program Manager or QA Leader, with 25+ years of experience at companies like RSA and Symantec.

Is there anything open at your company that might be a fit? I would love it if you could forward my CV to your recruiting team.

Happy to send my CV anytime.

Thanks,
Shaul Mano"""


def load_done():
    if not os.path.exists(PROGRESS_FILE):
        return set()
    with open(PROGRESS_FILE, encoding='utf-8-sig') as f:
        return {r['url'] for r in csv.DictReader(f)}

def sent_today():
    if not os.path.exists(PROGRESS_FILE):
        return 0
    today = str(date.today())
    with open(PROGRESS_FILE, encoding='utf-8-sig') as f:
        return sum(1 for r in csv.DictReader(f) if r['date'] == today and r['status'] == 'sent')

def mark_done(url, first, last, status):
    exists = os.path.exists(PROGRESS_FILE)
    with open(PROGRESS_FILE, 'a', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['url','firstName','lastName','status','date'])
        if not exists:
            writer.writeheader()
        writer.writerow({'url': url, 'firstName': first, 'lastName': last, 'status': status, 'date': str(date.today())})

def connect_browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--window-position=-32000,0")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)

def login(driver):
    from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD
    wait = WebDriverWait(driver, 15)
    driver.get('https://www.linkedin.com/login')
    time.sleep(3)
    if 'feed' in driver.current_url or 'mynetwork' in driver.current_url:
        print("Already logged in.")
        return
    wait.until(EC.presence_of_element_located((By.ID, 'username'))).send_keys(LINKEDIN_EMAIL)
    driver.find_element(By.ID, 'password').send_keys(LINKEDIN_PASSWORD)
    driver.find_element(By.XPATH, "//button[@type='submit']").click()
    time.sleep(random.uniform(4, 6))
    print("Logged in to LinkedIn.")

def type_text(driver, element, text):
    driver.execute_script("""
        arguments[0].focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, arguments[1]);
    """, element, text)

def send_message(driver, url, first, full_name):
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
        search_name = ' '.join(full_name.split()[:2])
        to_field.send_keys(search_name)
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
        if not sent:
            return 'error: send button not found'
        time.sleep(2)
        return 'sent'

    except Exception as e:
        return f'error: {e}'


def main():
    done = load_done()
    pending = [(f, l, u) for f, l, u in CONTACTS if u not in done]

    print(f"Total: {len(CONTACTS)} | Done: {len(done)} | Remaining: {len(pending)}")
    if not pending:
        print("All done!")
        return

    already_today = sent_today()
    remaining_today = DAILY_LIMIT - already_today
    if remaining_today <= 0:
        print(f"Already sent {already_today} today (limit {DAILY_LIMIT}). Waiting until tomorrow...")
        time.sleep(23 * 3600)
        os.execv(sys.executable, [sys.executable] + sys.argv)
        return

    batch = pending[:remaining_today]
    print(f"Sent today so far: {already_today} | Sending now: {len(batch)}")
    print()

    print("Sending to:")
    for i, (first, last, url) in enumerate(batch, 1):
        print(f"  [{i}] {first} {last}")

    driver = connect_browser()
    login(driver)

    sent = 0
    try:
        for i, (first, last, url) in enumerate(batch, 1):
            print(f"[{i}/{len(batch)}] {first} {last} ... ", end='', flush=True)
            result = send_message(driver, url, first, f"{first} {last}")
            mark_done(url, first, last, result)
            if result == 'sent':
                sent += 1
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
        print(f"\n=== Done: {sent}/{len(batch)} sent ===")
        print("Waiting until tomorrow...")
        time.sleep(23 * 3600)
        print("Restarting...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

if __name__ == '__main__':
    main()
