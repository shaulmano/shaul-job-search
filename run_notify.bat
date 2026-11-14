@echo off
REM Fired by the Windows scheduled task JobSearchNotify at 07:00, 13:00, 19:00.
REM
REM It used to run the full scan, which the cloud already does every 90 minutes:
REM the same boards, the same roles, a second Telegram message for the same jobs.
REM Since 11/10/2026 it runs only what the cloud cannot reach.
REM
REM 14/11/2026: the list is empty again. Malam Team was moved here that
REM morning and moved straight back out: it answered 403 from this machine
REM too, on a home connection, so the block was never about the address.
REM The whole domain sits behind a Cloudflare JavaScript challenge now.
REM
REM This file still does nothing until a source is added to BLOCKED_SOURCES,
REM and a run with an empty list exits in one line. Keep the task: it is the
REM only path ready for the next board that blocks the cloud.
REM
REM Jobs written here are NOT scored here. The next cloud run scores whatever
REM has no match row yet, so they show up on the board within the hour.
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
echo  ====================================================
echo.

REM -u so each line prints while it runs instead of all at the end. This window
REM is the only report of what happened, so it has to say so as it goes.
python -u local_blocked_scan.py

echo.
echo  Finished. Closing in 20 seconds (press a key to close now).
timeout /t 20
