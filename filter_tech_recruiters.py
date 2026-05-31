import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv, re, os

INPUT_FILE  = r"C:\Users\Shaul\Documents\job-search\recruiters_scraped.csv"
OUTPUT_FILE = r"C:\Users\Shaul\Documents\job-search\recruiters_scraped_tech.csv"

TECH_TITLE_KW = [
    'tech', 'technical', 'hi-tech', 'high-tech', 'hitech',
    'software', 'r&d', 'cyber', 'data scientist',
    ' ai', 'ai ', 'cloud', 'saas', 'fintech',
    'medtech', 'biotech', 'it recruiter',
    'startup', 'dev',
]

TECH_COMPANY_KW = [
    'tech', 'software', 'systems', 'solutions', 'digital',
    'cyber', 'cloud', 'networks', 'labs', 'technologies',
    'microsoft', 'google', 'amazon', 'apple', 'intel', 'nvidia',
    'cisco', 'ibm', 'salesforce', 'oracle', 'sap',
    'amdocs', 'check point', 'nice', 'wix', 'fiverr',
    'monday.com', 'mobileye', 'mellanox', 'radware', 'imperva',
    'varonis', 'cyberark', 'armis', 'sisense', 'riskified',
    'payoneer', 'taboola', 'outbrain', 'appsflyer', 'experis',
]

def is_bad_name(first):
    if not first:
        return True
    if 'mutual connection' in first.lower():
        return True
    if first.count(',') >= 2:
        return True
    if not re.match(r'^[A-Za-zא-ת]+', first):
        return True
    return False

def is_tech(row):
    title   = (row.get('jobTitle') or '').lower()
    company = (row.get('company') or '').lower()
    for kw in TECH_TITLE_KW:
        if kw in title:
            return True
    for kw in TECH_COMPANY_KW:
        if kw in company:
            return True
    return False

with open(INPUT_FILE, encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

print(f"Input: {len(rows)} rows")

clean = []
for r in rows:
    if is_bad_name(r.get('firstName', '')):
        continue
    if not is_tech(r):
        continue
    clean.append(r)

print(f"Tech recruiters: {len(clean)}")
print(f"Removed: {len(rows) - len(clean)}")

with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['firstName','lastName','linkedinProfileUrl','jobTitle','company'])
    writer.writeheader()
    writer.writerows(clean)

print(f"Saved to: {OUTPUT_FILE}")
print()
print("Sample:")
for r in clean[:10]:
    print(f"  {r['firstName']} {r['lastName']} | {r['jobTitle']} | {r['company']}")
