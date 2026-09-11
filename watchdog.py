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


def _api(path, token=None):
    req = urllib.request.Request(
        f'https://api.github.com{path}',
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'job-search-watchdog',
            # A token argument rather than only GITHUB_TOKEN: the run history of
            # situation-room lives in another repository, and the built-in token
            # cannot see outside the one it was minted for.
            **({'Authorization': f'Bearer {token or os.environ.get("GITHUB_TOKEN")}'}
               if (token or os.environ.get('GITHUB_TOKEN')) else {}),
        })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def last_success(repo=REPO, workflow=WORKFLOW, token=None):
    """When did the scan last finish successfully? None if never, or unknown."""
    data = _api(f'/repos/{repo}/actions/workflows/{workflow}/runs'
                f'?status=success&per_page=1', token)
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


def check_scan(state):
    now = datetime.now(timezone.utc)
    try:
        last = last_success()
    except urllib.error.HTTPError as e:
        # Cannot reach the API. Staying quiet is right: alerting here would
        # mean crying wolf about GitHub rather than about the scan.
        print(f'[watchdog] github api {e.code} — no judgement possible')
        return

    if last is None:
        print('[watchdog] no successful run on record — nothing to compare')
        return

    gap = now - last
    hours = gap.total_seconds() / 3600
    print(f'[watchdog] last success {last:%Y-%m-%d %H:%M} UTC, '
          f'{hours:.1f}h ago, threshold {QUIET_HOURS}h')

    if hours < QUIET_HOURS:
        if state.get('alerted'):
            # It came back on its own. Say so, so the earlier alert is closed
            # out rather than left hanging.
            send(f'✅ הסריקה חזרה לפעול\nרצה לפני {hours * 60:.0f} דקות')
            state.pop('alerted', None)
            state.pop('last_alert', None)
            save_state(state)
        else:
            print('[watchdog] healthy')
        return

    last_alert = state.get('last_alert')
    if last_alert:
        since = (now - datetime.fromisoformat(last_alert)).total_seconds() / 3600
        if since < REPEAT_HOURS:
            print(f'[watchdog] still down, but alerted {since:.1f}h ago — quiet '
                  f'until {REPEAT_HOURS}h')
            return

    il = last.astimezone(timezone(timedelta(hours=3)))
    send(
        '⚠️ <b>הסריקה שקטה</b>\n\n'
        f'הריצה המוצלחת האחרונה: {il:%d/%m %H:%M} (שעון ישראל)\n'
        f'כלומר לפני <b>{hours:.1f} שעות</b>.\n\n'
        f'אמורה לרוץ כל 90 דקות, אז משהו תקוע.\n'
        f'https://github.com/{REPO}/actions/workflows/{WORKFLOW}'
    )
    state.update({'alerted': True, 'last_alert': now.isoformat()})
    save_state(state)



# ── the situation room's sync ────────────────────────────────────────────────
#
# The scan going quiet is not the only way jobs stop arriving, and on 10/09 it
# was not the way that happened. The scan ran all night; the sync that copies
# its output into Supabase failed on every attempt for twenty hours because the
# Supabase token had reached its expiry date. Telegram kept working — it never
# touches Supabase — so the only symptom was an app that quietly stopped
# updating, and the only thing that noticed was Shaul.
#
# This check lives here rather than in situation-room on purpose: a private repo
# whose own credentials just died cannot be the thing that tells you they died.
# Telegram is the one channel that does not depend on Supabase, and its
# credentials are here.
#
# One number covers both failure modes. "When did the sync last succeed" is
# false for a sync that is erroring and false for a sync that is not running at
# all, and both mean the same thing: the app is showing stale jobs.
SR_REPO = 'shaulmano/situation-room'
SR_WORKFLOW = 'sync.yml'

# Scheduled three times a day (02:10, 10:10, 18:10 UTC) plus a dispatch from
# every scan that found something, so a healthy gap peaks near nine hours on a
# quiet night. Twelve leaves room for GitHub's delivery lag without letting a
# real outage run past half a day — the last one ran twenty.
SR_QUIET_HOURS = 12


def check_sync(state):
    """Alert if the situation room has not successfully synced in a while."""
    now = datetime.now(timezone.utc)
    token = os.environ.get('SR_SYNC_TOKEN', '')
    if not token:
        print('[watchdog] no SR_SYNC_TOKEN — skipping the sync check')
        return

    try:
        last = last_success(SR_REPO, SR_WORKFLOW, token)
    except urllib.error.HTTPError as e:
        print(f'[watchdog] sync api {e.code} — no judgement possible')
        return

    if last is None:
        print('[watchdog] no successful sync on record — nothing to compare')
        return

    hours = (now - last).total_seconds() / 3600
    print(f'[watchdog] last sync success {last:%Y-%m-%d %H:%M} UTC, '
          f'{hours:.1f}h ago, threshold {SR_QUIET_HOURS}h')

    if hours < SR_QUIET_HOURS:
        if state.get('sync_alerted'):
            send(f'✅ הסנכרון לחדר המצב חזר לעבוד\nהצליח לפני {hours * 60:.0f} דקות')
            state.pop('sync_alerted', None)
            state.pop('sync_last_alert', None)
            save_state(state)
        else:
            print('[watchdog] sync healthy')
        return

    prev = state.get('sync_last_alert')
    if prev:
        since = (now - datetime.fromisoformat(prev)).total_seconds() / 3600
        if since < REPEAT_HOURS:
            print(f'[watchdog] sync still down, alerted {since:.1f}h ago — quiet')
            return

    il = last.astimezone(timezone(timedelta(hours=3)))
    send(
        '⚠️ <b>חדר המצב לא מתעדכן</b>\n\n'
        f'הסנכרון האחרון שהצליח: {il:%d/%m %H:%M} (שעון ישראל)\n'
        f'כלומר לפני <b>{hours:.1f} שעות</b>.\n\n'
        'הסריקה עצמה אולי עובדת — ההודעות האלה מגיעות אליך בכל מקרה — '
        'אבל המשרות לא נכנסות לאפליקציה.\n\n'
        'החשוד הראשון: הטוקן של Supabase פג.\n'
        f'https://github.com/{SR_REPO}/actions/workflows/{SR_WORKFLOW}'
    )
    state.update({'sync_alerted': True, 'sync_last_alert': now.isoformat()})
    save_state(state)


def main():
    state = load_state()
    check_scan(state)
    check_sync(state)
    return 0


if __name__ == '__main__':
    sys.exit(main())
