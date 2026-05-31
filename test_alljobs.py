import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_server import search_alljobs

results = []
jobs = search_alljobs('QA Manager')
results.append(f'AllJobs: {len(jobs)} jobs')
for j in jobs[:5]:
    results.append(f'  {j["title"]} | {j["url"]}')

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
