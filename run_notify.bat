@echo off
REM Fired by the Windows scheduled task JobSearchNotify at 07:00, 13:00, 19:00.
REM
REM It used to run the full scan, which the cloud already does every 90 minutes:
REM the same boards, the same roles, a second Telegram message for the same jobs.
REM Since 11/10/2026 it runs only what the cloud cannot reach.
REM
REM Malam Team, SQLink and One1 answer a GitHub runner with HTTP 403 behind
REM Cloudflare, so they were taken out of SCHEDULED_SOURCES. From this machine
REM they answer normally. This is now the only path by which those three reach
REM the situation room, and the only thing this file does.
REM
REM Still read-only as far as git is concerned. The cloud run owns jobs.jsonl
REM and seen_jobs.json; a local run committing them is what left the working
REM copy stuck mid-rebase and 116 commits behind origin on 18/08/2026.
REM
REM To run the full local scan by hand:  python run_notify.py
REM To stop this task:  Disable-ScheduledTask -TaskName JobSearchNotify

title Job scan - boards blocked in the cloud
cd /d C:\Users\Shaul\Documents\job-search

echo.
echo  ====================================================
echo   Scanning the boards Cloudflare blocks in the cloud
echo   Malam Team, SQLink, One1
echo  ====================================================
echo.

REM -u so each line prints while it runs instead of all at the end. This window
REM is the only report of what happened, so it has to say so as it goes.
python -u local_blocked_scan.py

echo.
echo  Finished. Closing in 20 seconds (press a key to close now).
timeout /t 20
