@echo off
REM Fired by the Windows scheduled task JobSearchNotify at 07:00, 13:00, 19:00.
REM
REM It used to run the full scan, which the cloud already does every 90 minutes:
REM the same boards, the same roles, a second Telegram message for the same jobs.
REM Since 11/10/2026 it runs only what the cloud cannot reach.
REM
REM 14/11/2026: Malam Team. It brought 474 jobs and then went silent on
REM 1/11. From a GitHub runner it answers HTTP 403 with "Just a moment...",
REM and seven browser fingerprints, Chrome 124 through 152, Safari and
REM Firefox, all got 403 from the same runner that SQLink answers with 200.
REM So it is the address, not the fingerprint, and no code in the cloud can
REM fix it. From this machine the board answers normally, and this file is
REM the only path by which it reaches the situation room.
REM
REM These jobs are written to the database but NOT scored here. The next
REM cloud run scores whatever has no match row yet, so they show up on the
REM board within the hour, not at once.
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
echo   Malam Team
echo  ====================================================
echo.

REM -u so each line prints while it runs instead of all at the end. This window
REM is the only report of what happened, so it has to say so as it goes.
python -u local_blocked_scan.py

echo.
echo  Finished. Closing in 20 seconds (press a key to close now).
timeout /t 20
