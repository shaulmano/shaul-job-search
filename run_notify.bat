@echo off
cd /d C:\Users\Shaul\Documents\job-search
git pull --rebase --autostash
python run_notify.py
git add docs/jobs.html seen_jobs.json
git commit -m "Update jobs.html + seen_jobs.json (local run)"
git pull --rebase --autostash
git push
