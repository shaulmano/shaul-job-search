import sys
sys.stdout.reconfigure(encoding='utf-8')

import csv
import requests

PROXYCURL_API_KEY = "GI2eUSb83NIBWeM-u-DKpw"
RECRUITERS_FILE   = r"C:\Users\Shaul\Documents\job-search\phantom_recruiters.csv"

def get_credits():
    r = requests.get(
        'https://nubela.co/proxycurl/api/credit-balance',
        headers={'Authorization': f'Bearer {PROXYCURL_API_KEY}'}
    )
    print(f"  (credit status: {r.status_code}, body: {r.text[:100]})")
    return r.json().get('credit_balance', '?')

def normalize_url(url):
    url = url.strip()
    if url.startswith('https://linkedin.com'):
        url = url.replace('https://linkedin.com', 'https://www.linkedin.com', 1)
    return url

with open(RECRUITERS_FILE, encoding='utf-8-sig') as f:
    recruiters = list(csv.DictReader(f))[:3]

print(f"קרדיטים לפני:")
before = get_credits()
print()

for r in recruiters:
    url   = normalize_url(r['linkedinProfileUrl'])
    first = r['firstName'].strip()
    last  = r['lastName'].strip()
    print(f"{first} {last}")
    print(f"  URL: {url}")

    resp = requests.get(
        'https://nubela.co/proxycurl/api/v2/linkedin',
        headers={'Authorization': f'Bearer {PROXYCURL_API_KEY}'},
        params={'linkedin_profile_url': url, 'personal_email': 'include'},
        timeout=20
    )
    print(f"  Status: {resp.status_code}")
    data = resp.json()
    print(f"  שם: {data.get('full_name','')}")
    print(f"  חברה: {(data.get('experiences') or [{}])[0].get('company','')}")
    print(f"  מיילים: {data.get('personal_emails') or data.get('work_email') or 'אין'}")
    print()

print(f"קרדיטים אחרי:")
get_credits()
