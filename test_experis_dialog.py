import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_server import search_experis, search_dialog

results = []

results.append('=== Experis ===')
jobs = search_experis('QA Manager')
results.append(f'  {len(jobs)} jobs found')
for j in jobs[:5]:
    results.append(f'  {j["title"]} | {j["url"]}')

results.append('')
results.append('=== Dialog ===')
jobs = search_dialog('QA Manager')
results.append(f'  {len(jobs)} jobs found')
for j in jobs[:5]:
    results.append(f'  {j["title"]} | {j["url"]}')

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
