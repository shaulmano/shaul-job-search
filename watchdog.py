#!/usr/bin/env python3
"""Tell Shaul when the scan has gone quiet.

The scan reports on every run, even an empty one, so a message arriving means
things are fine. The failure this catches is the opposite: nothing arriving at
all, which on the night of 18/08/2026 went unnoticed for two hours because
silence looks exactly like "no new jobs" from the outside.

Runs as its own workflow on its own schedule — a watchdog living inside the
thing it watches would go quiet with it.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = os.environ.get('GITHUB_REPOSITORY', 'shaulmano/shaul-job-search')
WORKFLOW = 'notify.yml'

# The scan fires every 90 minutes and GitHub delivers scheduled runs 18-38
# minutes late, so a healthy gap peaks near 2h10m. Four hours means at least
# two consecutive slots were missed — a real problem, not a slow queue.
QUIET_HOURS = 4

# Once it is down it stays down, and an alert every couple of hours would train
# him to ignore the alerts. Repeat at most this often while the outage lasts.
REPEAT_HOURS = 12

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'watchdog_state.json')


def _api(path):
    req = urllib.request.Request(
        f'https://api.github.com{path}',
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'job-search-watchdog',
            **({'Authorization': f'Bearer {os.environ["GITHUB_TOKEN"]}'}
               if os.environ.get('GITHUB_TOKEN') else {}),
        })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def last_success():
    """When did the scan last finish successfully? None if never, or unknown."""
    data = _api(f'/repos/{REPO}/actions/workflows/{WORKFLOW}/runs'
                f'?status=success&per_page=1')
    runs = data.get('workflow_runs') or []
    if not runs:
        return None
    return datetime.fromisoformat(runs[0]['updated_at'].replace('Z', '+00:00'))


def send(text):
    token = os.environ.get('TELEGRAM_TOKEN', '')
    chat = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not chat:
        print('[watchdog] no telegram credentials — not sending')
        return False
    payload = json.dumps({'chat_id': chat, 'text': text,
                          'parse_mode': 'HTML'}).encode()
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/sendMessage',
        data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f'[watchdog] telegram sent (HTTP {r.status})')
            return True
    except Exception as e:
        print(f'[watchdog] telegram failed: {e}')
        return False


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f'[watchdog] could not write state: {e}')


def main():
    now = datetime.now(timezone.utc)
    try:
        last = last_success()
    except urllib.error.HTTPError as e:
        # Cannot reach the API. Staying quiet is right: alerting here would
        # mean crying wolf about GitHub rather than about the scan.
        print(f'[watchdog] github api {e.code} — no judgement possible')
        return 0

    state = load_state()

    if last is None:
        print('[watchdog] no successful run on record — nothing to compare')
        return 0

    gap = now - last
    hours = gap.total_seconds() / 3600
    print(f'[watchdog] last success {last:%Y-%m-%d %H:%M} UTC, '
          f'{hours:.1f}h ago, threshold {QUIET_HOURS}h')

    if hours < QUIET_HOURS:
        if state.get('alerted'):
            # It came back on its own. Say so, so the earlier alert is closed
            # out rather than left hanging.
            send(f'✅ הסריקה חזרה לפעול\nרצה לפני {hours * 60:.0f} דקות')
            save_state({})
        else:
            print('[watchdog] healthy')
        return 0

    last_alert = state.get('last_alert')
    if last_alert:
        since = (now - datetime.fromisoformat(last_alert)).total_seconds() / 3600
        if since < REPEAT_HOURS:
            print(f'[watchdog] still down, but alerted {since:.1f}h ago — quiet '
                  f'until {REPEAT_HOURS}h')
            return 0

    il = last.astimezone(timezone(timedelta(hours=3)))
    send(
        '⚠️ <b>הסריקה שקטה</b>\n\n'
        f'הריצה המוצלחת האחרונה: {il:%d/%m %H:%M} (שעון ישראל)\n'
        f'כלומר לפני <b>{hours:.1f} שעות</b>.\n\n'
        f'אמורה לרוץ כל 90 דקות, אז משהו תקוע.\n'
        f'https://github.com/{REPO}/actions/workflows/{WORKFLOW}'
    )
    save_state({'alerted': True, 'last_alert': now.isoformat()})
    return 0


if __name__ == '__main__':
    sys.exit(main())
