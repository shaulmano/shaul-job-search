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

if os.getenv('GITHUB_ACTIONS'):
    # GitHub Actions: use fast sources only (no Playwright installed)
    pass
else:
    # Local: use all sources for maximum coverage
    job_server.SCHEDULED_SOURCES_FAST = job_server.SCHEDULED_SOURCES

job_server._run_notify_job()
