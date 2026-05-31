import sys
sys.stdout.reconfigure(encoding='utf-8')

import time, re, csv, os
from selenium import webdriver
from selenium.webdriver.common.by import By

OUTPUT_FILE = r"C:\Users\Shaul\Documents\job-search\my_connections.csv"

TECH_KW = [
    'tech', 'software', 'system', 'cyber', 'cloud', 'data', 'ai ', ' ai',
    'saas', 'fintech', 'medtech', 'biotech', 'startup', 'r&d', 'devops',
    'digital', 'platform', 'network', 'security', 'dev', 'engineer',
    'microsoft', 'google', 'amazon', 'intel', 'nvidia', 'cisco', 'ibm',
    'amdocs', 'check point', 'checkpoint', 'nice', 'wix', 'fiverr',
    'monday', 'mobileye', 'mellanox', 'radware', 'imperva', 'varonis',
    'cyberark', 'armis', 'sisense', 'riskified', 'payoneer', 'taboola',
    'outbrain', 'appsflyer', 'elbit', 'rafael', 'cellebrite', 'lightricks',
    'lemonade', 'elementor', 'tipalti', 'servicenow', 'workday', 'zendesk',
    'similarweb', 'qualcomm', 'broadcom', 'marvell', 'cadence', 'synopsys',
]

def is_tech(company):
    c = (company or '').lower()
    return any(kw in c for kw in TECH_KW)

def connect():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

def extract_connections(driver):
    return driver.execute_script("""
        var results = [];
        var seen = new Set();
        var links = document.querySelectorAll('a[href*="/in/"]');
        for (var a of links) {
            var url = a.href.split('?')[0].replace(/[/]+$/, '');
            if (!url.match(/linkedin\\.com\\/in\\/[^/]+$/) || seen.has(url)) continue;
            var text = (a.innerText || '').trim();
            if (!text || text.length < 3) continue;
            seen.add(url);
            var lines = text.split('\\n').map(function(l){ return l.trim(); }).filter(function(l){ return l.length > 0; });
            var name = lines[0] || '';
            var occ  = lines[1] || '';
            results.push({url: url, name: name, occupation: occ});
        }
        return results;
    """)

def parse_name(name):
    parts = name.strip().split(' ', 1)
    return parts[0], parts[1] if len(parts) > 1 else ''

def scroll_and_collect(driver):
    all_connections = {}
    prev_count = 0
    stall = 0

    while stall < 8:
        cards = extract_connections(driver)
        for c in cards:
            url = c['url']
            if url not in all_connections:
                all_connections[url] = c

        count = len(all_connections)
        print(f"\r  Found {count} connections...", end='', flush=True)

        if count == prev_count:
            stall += 1
        else:
            stall = 0
        prev_count = count

        # נסה לגלול את הקונטיינר הנכון
        driver.execute_script("""
            var el = document.querySelector('.scaffold-finite-scroll__content')
                  || document.querySelector('.mn-connections__list')
                  || document.querySelector('main')
                  || document.body;
            el.scrollTop += 1000;
            window.scrollBy(0, 1000);
        """)
        time.sleep(2)

    print()
    return list(all_connections.values())

def main():
    print("Connecting to Chrome...")
    driver = connect()

    print("Opening connections page...")
    driver.get("https://www.linkedin.com/mynetwork/invite-connect/connections/")
    time.sleep(4)

    print("Scanning connections (auto-scrolling)...")
    connections = scroll_and_collect(driver)

    print(f"\nTotal found: {len(connections)} connections")

    rows = []
    for c in connections:
        first, last = parse_name(c['name'])
        occ = c['occupation']

        job_title, company = '', ''
        if ' at ' in occ:
            job_title, company = occ.split(' at ', 1)
        elif ' @ ' in occ:
            job_title, company = occ.split(' @ ', 1)
        else:
            job_title = occ

        rows.append({
            'firstName': first.strip(),
            'lastName': last.strip(),
            'linkedinUrl': c['url'],
            'jobTitle': job_title.strip(),
            'company': company.strip(),
            'isTech': 'yes' if is_tech(company) else 'no',
        })

    rows.sort(key=lambda r: (0 if r['isTech'] == 'yes' else 1, r['company']))

    with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['firstName','lastName','linkedinUrl','jobTitle','company','isTech'])
        writer.writeheader()
        writer.writerows(rows)

    tech = [r for r in rows if r['isTech'] == 'yes']
    print(f"Tech companies: {len(tech)}")
    print(f"Other: {len(rows) - len(tech)}")
    print(f"\nSaved to: {OUTPUT_FILE}")
    print("\n--- Tech connections sample ---")
    for r in tech[:10]:
        print(f"  {r['firstName']} {r['lastName']} | {r['jobTitle']} @ {r['company']}")

if __name__ == '__main__':
    main()
