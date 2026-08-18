@echo off
REM Local scan, for checking things by hand.
REM
REM This used to end with: git add / git commit / git pull --rebase / git push.
REM The hourly GitHub Actions workflow commits the same two files, so the two
REM raced each other - that is what left the working copy stuck mid-rebase and
REM 116 commits behind origin on 18/08/2026. The cloud run is what publishes;
REM a local run is now read-only as far as git is concerned.
REM
REM The scheduled task JobSearchNotify still fires this at 07:00, 13:00 and
REM 19:00, duplicating what the cloud already does every hour. To stop that,
REM from an admin PowerShell:  Disable-ScheduledTask -TaskName JobSearchNotify

cd /d C:\Users\Shaul\Documents\job-search
python run_notify.py
