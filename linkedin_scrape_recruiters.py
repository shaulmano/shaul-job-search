import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv, time, random, os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

OUTPUT_FILE = r"C:\Users\Shaul\Documents\job-search\recruiters_new.csv"

# LinkedIn search queries — focused on Israeli hi-tech recruiters
# industry codes: 4=Software, 6=Internet, 7=Computer Hardware, 96=IT Services, 14=Semiconductors, 3=Defense
INDUSTRY_FILTER = "4%2C6%2C7%2C96%2C14%2C3"
GEO_FILTER      = "101620260"   # Israel

SEARCHES = [
    # מגייסים ישירים
    "Technical Recruiter",
    "Recruiter High Tech",
    "Talent Acquisition",
    "Recruitment Manager",
    "HR Recruiter",
    "Recruiter Startup",
    "Recruiter R&D",
    "Headhunter Israel",
    # בכירי HR
    "Chief HR Officer",
    "Chief People Officer",
    "VP HR",
    "VP People",
    "Head of HR",
    "Head of People",
    "HR Director",
    "People Director",
    "Director of People",
    # מנהלים שמגייסים ישירות
    "VP QA",
    "VP Quality",
    "Head of QA",
    "QA Director",
    "VP Engineering",
    "Engineering Director",
    "VP RnD",
    "Head of RnD",
]

MAX_PAGES = 10  # 10 results per page = up to 100 profiles per search


def init_browser():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)


def load_existing_urls():
    if not os.path.exists(OUTPUT_FILE):
        return set()
    with open(OUTPUT_FILE, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return set(r.get('linkedinProfileUrl', '').strip() for r in reader)


def init_output_file():
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['firstName', 'lastName', 'linkedinProfileUrl', 'jobTitle', 'company', 'location'])


def save_profile(first, last, url, title, company, location):
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([first, last, url, title, company, location])


_LINKEDIN_NOISE = [
    "i'm hiring", "im hiring", "open to work", "open to opportunities",
    "hiring", "recruiting", "🔍", "💼", "🌟", "✅", "🚀",
]

def parse_name(full_name):
    cleaned = full_name.strip()
    lower = cleaned.lower()
    for noise in _LINKEDIN_NOISE:
        idx = lower.find(noise)
        if idx != -1:
            cleaned = cleaned[:idx].strip(" -|·•")
            lower = cleaned.lower()
    parts = cleaned.split(' ', 2)
    first = parts[0] if parts else ''
    last  = parts[1] if len(parts) > 1 else ''
    return first, last


def scrape_search(driver, query, existing_urls):
    print(f"\nSearching: '{query}'")
    found = 0

    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={query.replace(' ', '%20')}"
            f"&geoUrn=%5B%22{GEO_FILTER}%22%5D"
            f"&industry=%5B{INDUSTRY_FILTER}%5D"
            f"&page={page}"
        )
        driver.get(url)
        time.sleep(random.uniform(3, 5))

        # check for commercial use limit
        if 'search/results' not in driver.current_url:
            print(f"  Redirected — stopping search for this query.")
            break

        print(f"  Page {page} URL: {driver.current_url[:80]}")

        # wait for any profile link to appear
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/in/')]"))
            )
        except:
            print(f"  Page {page}: no results found.")
            break

        # collect all profile links on the page
        all_links = driver.find_elements(By.XPATH, "//a[contains(@href,'linkedin.com/in/') or (contains(@href,'/in/') and not(contains(@href,'linkedin.com/company')))]")
        if not all_links:
            print(f"  Page {page}: no profile links found.")
            break

        page_new = 0
        seen_urls = set()
        for link in all_links:
            try:
                href = link.get_attribute('href') or ''
                if '/in/' not in href:
                    continue
                profile_url = href.split('?')[0].rstrip('/')
                if not profile_url or profile_url in existing_urls or profile_url in seen_urls:
                    continue
                seen_urls.add(profile_url)

                name = link.get_attribute('aria-label') or link.text.strip()
                name = name.replace('View', '').replace("'s profile", '').strip()
                if not name or len(name) < 2:
                    continue

                # try to get title/company from nearby elements
                try:
                    parent = link.find_element(By.XPATH, "./ancestor::li[1]")
                    title    = ''
                    company  = ''
                    location = 'Israel'
                    spans = parent.find_elements(By.XPATH, ".//div[@class] | .//span[@class]")
                    texts = [s.text.strip() for s in spans if s.text.strip()]
                    if len(texts) > 1:
                        title = texts[1]
                    if len(texts) > 2:
                        company = texts[2]
                except:
                    title = company = ''
                    location = 'Israel'

                first, last = parse_name(name)
                save_profile(first, last, profile_url, title, company, location)
                existing_urls.add(profile_url)
                page_new += 1
                found += 1

            except Exception:
                continue

        print(f"  Page {page}: +{page_new} new profiles (total this query: {found})")

        if page_new == 0:
            break

        time.sleep(random.uniform(4, 8))

    return found


def main():
    init_output_file()
    existing_urls = load_existing_urls()
    print(f"Already in file: {len(existing_urls)} profiles")
    print(f"Output: {OUTPUT_FILE}\n")
    input("Press Enter to start...")

    driver = init_browser()
    print(f"Connected to browser. URL: {driver.current_url}")

    total = 0
    try:
        for query in SEARCHES:
            found = scrape_search(driver, query, existing_urls)
            total += found
            time.sleep(random.uniform(5, 10))

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        print(f"\n=== DONE ===")
        print(f"Total new profiles saved: {total}")
        print(f"File: {OUTPUT_FILE}")
        input("Press Enter to close...")
        driver.quit()


if __name__ == '__main__':
    main()
