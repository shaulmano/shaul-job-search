import sys
sys.stdout.reconfigure(encoding='utf-8')
import requests
import time
from config import SNOV_CLIENT_ID, SNOV_CLIENT_SECRET

def get_token():
    r = requests.post('https://api.snov.io/v1/oauth/access_token', data={
        'grant_type': 'client_credentials',
        'client_id': SNOV_CLIENT_ID,
        'client_secret': SNOV_CLIENT_SECRET
    })
    return r.json().get('access_token')

token = get_token()
print(f"Token OK: {bool(token)}\n")

# בדיקת קרדיטים
r = requests.get(
    'https://api.snov.io/v1/check-user-balance',
    headers={'Authorization': f'Bearer {token}'}
)
print(f"קרדיטים ({r.status_code}): {r.json()}\n")

# חיפוש מייל — שלב 1: הפעלת משימה
print("מחפש מייל: Moria David @ sqlinkgroup.com")
r2 = requests.post(
    'https://api.snov.io/v2/emails-by-domain-by-name/start',
    headers={'Authorization': f'Bearer {token}'},
    json={'rows': [{'first_name': 'Moria', 'last_name': 'David', 'domain': 'sqlinkgroup.com'}]}
)
print(f"Start status: {r2.status_code}")
data2 = r2.json()
print(f"Response: {data2}\n")

task_hash = data2.get('task_hash') or (data2.get('data') or {}).get('task_hash')

if task_hash:
    print(f"Task hash: {task_hash}")
    print("ממתין 5 שניות לתוצאה...")
    time.sleep(5)

    r3 = requests.get(
        f'https://api.snov.io/v2/emails-by-domain-by-name/result',
        headers={'Authorization': f'Bearer {token}'},
        params={'task_hash': task_hash}
    )
    print(f"Result status: {r3.status_code}")
    print(f"Result: {r3.json()}")
