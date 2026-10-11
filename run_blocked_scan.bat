@echo off
REM The three boards Cloudflare blocks for GitHub runners: Malam Team, SQLink,
REM One1. They answer fine from here, so this run is the only way they reach the
REM situation room. Everything else is scanned in the cloud.
REM
REM Writes straight to the database. Deliberately no git, no jobs.jsonl and no
REM Telegram: the hourly cloud run owns those files, and a local run touching
REM them is what left the working copy stuck mid-rebase on 18/08/2026.

title Job scan - blocked boards
cd /d C:\Users\Shaul\Documents\job-search

echo.
echo  ====================================================
echo   Scanning the boards blocked in the cloud
echo   Malam Team, SQLink, One1
echo  ====================================================
echo.

REM -u so each line appears while it runs instead of at the end: the whole point
REM of this window is watching it work.
python -u local_blocked_scan.py

echo.
echo  Finished. This window closes in 20 seconds.
echo  (Press a key to close it now.)
timeout /t 20
