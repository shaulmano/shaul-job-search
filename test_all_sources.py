import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from job_server import (
    search_indeed, search_alljobs, search_drushim,
    search_comeet, search_gotfriends, search_experis,
    search_dialog, search_sqlink, search_nisha,
    search_malamteam, search_maof, search_sela, search_one1
)

ROLE = 'QA Manager'
SCRAPERS = {
    'Indeed':      search_indeed,
    'AllJobs':     search_alljobs,
    'Drushim':     search_drushim,
    'Comeet':      search_comeet,
    'GotFriends':  search_gotfriends,
    'Experis':     search_experis,
    'Dialog':      search_dialog,
    'SQLink':      search_sqlink,
    'Nisha':       search_nisha,
    'MalamTeam':   search_malamteam,
    'Maof':        search_maof,
    'Sela':        search_sela,
    'One1':        search_one1,
}

results = []
for name, fn in SCRAPERS.items():
    try:
        jobs = fn(ROLE)
        status = f'{len(jobs)} משרות'
        sample = jobs[0]['title'] if jobs else ''
        results.append(f'{"OK" if jobs else "EMPTY":5}  {name:12}  {status}  {sample[:50]}')
    except Exception as e:
        results.append(f'ERROR  {name:12}  {e}')

with open(r'C:\Users\Shaul\Documents\job-search\debug_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
print('done')
