import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv, time, random, os, re
import requests

GOOGLE_API_KEY = "AIzaSyBB_s6uJR7t1ZcGiDM2Vr7uFaAd1_t35y4"
SEARCH_ENGINE_ID = "c21d67191ce5744aa"

OUTPUT_FILE   = r"C:\Users\Shaul\Documents\job-search\google_recruiters_new.csv"
EXISTING_FILE = r"C:\Users\Shaul\Documents\job-search\recruiters_new.csv"

SEARCHES = [
    # מגייסים ישירים
    'site:linkedin.com/in "technical recruiter" "israel"',
    'site:linkedin.com/in "recruiter" "high tech" "israel"',
    'site:linkedin.com/in "talent acquisition" "israel"',
    'site:linkedin.com/in "recruitment manager" "israel"',
    'site:linkedin.com/in "HR recruiter" "israel"',
    'site:linkedin.com/in "recruiter" "startup" "israel"',
    'site:linkedin.com/in "recruiter" "R&D" "israel"',
    'site:linkedin.com/in "headhunter" "israel"',
    'site:linkedin.com/in "talent acquisition" "tel aviv"',
    'site:linkedin.com/in "talent acquisition specialist" "israel"',
    # בכירי HR
    'site:linkedin.com/in "chief HR officer" "israel"',
    'site:linkedin.com/in "chief people officer" "israel"',
    'site:linkedin.com/in "VP HR" "israel"',
    'site:linkedin.com/in "VP people" "israel"',
    'site:linkedin.com/in "head of HR" "israel"',
    'site:linkedin.com/in "head of people" "israel"',
    'site:linkedin.com/in "HR director" "israel"',
    'site:linkedin.com/in "people director" "israel"',
    'site:linkedin.com/in "director of people" "israel"',
    'site:linkedin.com/in "HR manager" "israel" "tech"',
    'site:linkedin.com/in "HR business partner" "israel"',
    # מנהלים שמגייסים ישירות
    'site:linkedin.com/in "VP QA" "israel"',
    'site:linkedin.com/in "VP quality" "israel"',
    'site:linkedin.com/in "head of QA" "israel"',
    'site:linkedin.com/in "QA director" "israel"',
    'site:linkedin.com/in "VP engineering" "israel"',
    'site:linkedin.com/in "engineering director" "israel"',
    'site:linkedin.com/in "VP R&D" "israel"',
    'site:linkedin.com/in "head of R&D" "israel"',
]


def load_existing_urls():
    urls = set()
    for f in [EXISTING_FILE, OUTPUT_FILE]:
        if os.path.exists(f):
            with open(f, encoding='utf-8-sig') as fh:
                for row in csv.DictReader(fh):
                    u = row.get('linkedinProfileUrl', '').strip().rstrip('/')
                    if u:
                        urls.add(u)
    return urls


def init_output():
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerow(['firstName', 'lastName', 'linkedinProfileUrl', 'jobTitle', 'company', 'location'])


def save_profile(first, last, url, job_title):
    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        csv.writer(f).writerow([first, last, url, job_title, '', 'Israel'])


def parse_name(title):
    # "First Last - Job Title | LinkedIn"
    name_part = title.split('|')[0].split('-')[0].strip()
    name_part = re.sub(r'[^\w\s]', '', name_part).strip()
    parts = name_part.split()
    if len(parts) >= 2:
        return parts[0], ' '.join(parts[1:])
    elif len(parts) == 1:
        return parts[0], ''
    return '', ''


def parse_job(title):
    parts = title.split('|')[0].split('-')
    if len(parts) >= 2:
        return parts[1].strip()
    return ''


def search_google(query, existing_urls):
    found = []
    for start in range(1, 10, 10):  # רק עמוד 1 = 10 תוצאות
        params = {
            'key': GOOGLE_API_KEY,
            'cx': SEARCH_ENGINE_ID,
            'q': query,
            'num': 10,
            'start': start,
        }
        try:
            res = requests.get(
                'https://www.googleapis.com/customsearch/v1',
                params=params, timeout=15
            )
            data = res.json()

            if 'error' in data:
                print(f"  API error: {data['error'].get('message','')}")
                return found

            items = data.get('items', [])
            if not items:
                break

            for item in items:
                link = item.get('link', '')
                match = re.search(r'linkedin\.com/in/([\w\-]+)', link)
                if not match:
                    continue

                profile_url = f"https://www.linkedin.com/in/{match.group(1)}"
                if profile_url.rstrip('/') in existing_urls:
                    continue

                title    = item.get('title', '')
                first, last = parse_name(title)
                job_title   = parse_job(title)

                existing_urls.add(profile_url.rstrip('/'))
                found.append((first, last, profile_url, job_title))
                print(f"  + {first} {last} | {job_title[:40]}")

            time.sleep(random.uniform(1, 2))

        except Exception as e:
            print(f"  Error: {e}")
            break

    return found


def main():
    init_output()
    existing_urls = load_existing_urls()
    print(f"Existing URLs: {len(existing_urls)}")
    print()

    total = 0
    for query in SEARCHES:
        print(f"\nSearching: {query}")
        results = search_google(query, existing_urls)
        for first, last, url, job in results:
            save_profile(first, last, url, job)
            total += 1
        print(f"  Added: {len(results)}")
        time.sleep(random.uniform(1, 3))

    print(f"\n=== Done. Total new: {total} ===")
    print(f"File: {OUTPUT_FILE}")
    print("\nReview and copy relevant rows to recruiters_new.csv")


if __name__ == '__main__':
    main()
