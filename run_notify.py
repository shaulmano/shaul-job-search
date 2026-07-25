"""Entry point for the scheduled Telegram notifications.

    python run_notify.py            # every source (what the hourly workflow runs)
    python run_notify.py linkedin   # LinkedIn only, for a quick manual check
"""
import os, sys

# Load credentials from config.py when running locally (file is gitignored)
try:
    import config as _cfg
    os.environ.setdefault('TELEGRAM_TOKEN', getattr(_cfg, 'TELEGRAM_TOKEN', ''))
    os.environ.setdefault('TELEGRAM_CHAT_ID', getattr(_cfg, 'TELEGRAM_CHAT_ID', ''))
except ImportError:
    pass  # GitHub Actions: credentials come from repository secrets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_server

mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'full'

if mode == 'linkedin':
    job_server._run_notify_job(
        sources=['linkedin'], always_notify=True, scope=' בלינקדאין')
else:
    # Runs hourly. Silence would be ambiguous — a quiet hour and a broken scraper
    # look identical — so this always reports back, even with nothing new.
    job_server._run_notify_job(
        sources=job_server.SCHEDULED_SOURCES, always_notify=True)
