@echo off
title Job Search Server
set PY=C:\Users\Shaul\AppData\Local\Programs\Python\Python312\python.exe
echo.
echo  [1/3] Installing Python packages...
"%PY%" -m pip install requests beautifulsoup4 lxml playwright curl_cffi -q

echo  [2/3] Installing Playwright browser (Chromium)...
"%PY%" -m playwright install chromium

echo  [3/3] Starting Job Search Server...
echo.
start "" "%~dp0job-search-hub.html"
"%PY%" "%~dp0job_server.py"
