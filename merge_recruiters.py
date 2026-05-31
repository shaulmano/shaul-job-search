import csv, os

files = ['all_recruiters.csv', 'recruiters_new.csv']
seen_urls = set()
rows = []

for fname in files:
    with open(fname, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('linkedinProfileUrl', '').strip().rstrip('/')
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            rows.append({
                'firstName': row.get('firstName', '').strip(),
                'lastName': row.get('lastName', '').strip(),
                'linkedinProfileUrl': url,
                'jobTitle': row.get('jobTitle', '').strip(),
                'company': row.get('company', '').strip(),
                'location': row.get('location', '').strip(),
            })

out = 'all_recruiters_merged.csv'
with open(out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['firstName','lastName','linkedinProfileUrl','jobTitle','company','location'])
    w.writeheader()
    w.writerows(rows)

print(f'Total: {len(rows):,} unique recruiters saved to {out}')
