@echo off
title Chrome - LinkedIn Outreach (port 9223)
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --user-data-dir="C:\ChromeDebug2"
echo Chrome opened on port 9223
echo Wait for LinkedIn to load, then run run_outreach.bat
pause
