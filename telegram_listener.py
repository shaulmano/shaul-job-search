#!/usr/bin/env python3
"""Listen for button presses on the job messages.

Why a long-running poller and not a workflow every five minutes: GitHub
delivers scheduled runs 18-38 minutes late (measured over ten runs of the
scan), so a */5 schedule would wake up half an hour after the press and the
button would feel broken. An Actions job can run for six hours, and Telegram
supports long polling, so one long run answers in about a second.

Gaps between runs are safe: Telegram holds updates for 24 hours, so presses
that land while nothing is listening are delivered when polling resumes.

    python telegram_listener.py --seconds 20700   # one shift, 5h45m
    python telegram_listener.py --once            # drain and exit, for testing
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, 'listener_state.json')
JOBS_FILE = os.path.join(HERE, 'jobs.jsonl')
APPS_FILE = os.path.join(HERE, 'applications.json')

TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
CHAT_ID = str(os.environ.get('TELEGRAM_CHAT_ID', ''))
BASE = f'https://api.telegram.org/bot{TOKEN}'

# Telegram caps callback_data at 64 bytes, hence the one-letter verbs.
ACT_APPLIED = 'a'
ACT_SKIP = 's'


def _il_now():
    return datetime.now(timezone(timedelta(hours=3)))


# ── Telegram ────────────────────────────────────────────────────────────────
def call(method, **params):
    data = json.dumps(params).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/{method}', data=data,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')[:200]
        print(f'  [tg] {method} HTTP {e.code}: {body}')
        return {'ok': False}
    except Exception as e:
        print(f'  [tg] {method} failed: {type(e).__name__}: {e}')
        return {'ok': False}


# ── State ───────────────────────────────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def load_jobs():
    jobs = {}
    try:
        with open(JOBS_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get('id'):
                    jobs[rec['id']] = rec
    except FileNotFoundError:
        pass
    return jobs


def save_jobs(jobs):
    with open(JOBS_FILE, 'w', encoding='utf-8') as f:
        for jid in sorted(jobs):
            f.write(json.dumps(jobs[jid], ensure_ascii=False,
                               sort_keys=True) + '\n')


def record_application(job):
    """Mirror into applications.json, which is what the scan reads to stop
    re-reporting a job, and which already holds the 18 manual entries."""
    try:
        with open(APPS_FILE, encoding='utf-8') as f:
            apps = json.load(f)
    except Exception:
        apps = []
    if any(a.get('url') == job.get('url') for a in apps):
        return False
    apps.append({
        'id': job['id'],
        'title': job.get('title', ''),
        'company': job.get('company', ''),
        'source': job.get('source', ''),
        'url': job.get('url', ''),
        'date_applied': _il_now().strftime('%Y-%m-%d'),
        'status': 'נשלח',
        'notes': 'סומן מכפתור בטלגרם',
    })
    with open(APPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(apps, f, ensure_ascii=False, indent=2)
    return True


def commit(paths, message):
    """Persist to git. The runner is discarded after each run, so anything not
    committed is lost. Rebase first because the scan writes the same files."""
    if not os.environ.get('GITHUB_ACTIONS'):
        print('  [git] local run — not committing')
        return
    try:
        subprocess.run(['git', 'config', 'user.name', 'github-actions'],
                       cwd=HERE, check=False)
        subprocess.run(['git', 'config', 'user.email', 'actions@github.com'],
                       cwd=HERE, check=False)
        subprocess.run(['git', 'add', *paths], cwd=HERE, check=False)
        staged = subprocess.run(['git', 'diff', '--cached', '--quiet'],
                                cwd=HERE)
        if staged.returncode == 0:
            return                       # nothing changed
        subprocess.run(['git', 'commit', '-m', message], cwd=HERE, check=False)
        subprocess.run(['git', 'pull', '--rebase', '--autostash'],
                       cwd=HERE, check=False)
        subprocess.run(['git', 'push'], cwd=HERE, check=False)
        print(f'  [git] committed: {message}')
    except Exception as e:
        print(f'  [git] failed: {e}')


# ── Handling a press ────────────────────────────────────────────────────────
def handle_callback(cb):
    data = cb.get('data') or ''
    cb_id = cb.get('id')
    msg = cb.get('message') or {}
    chat_id = str((msg.get('chat') or {}).get('id', ''))

    # The bot only ever answers Shaul. Anyone who finds it gets nothing.
    if CHAT_ID and chat_id != CHAT_ID:
        call('answerCallbackQuery', callback_query_id=cb_id,
             text='לא מורשה', show_alert=False)
        return None

    try:
        action, jid = data.split(':', 1)
    except ValueError:
        call('answerCallbackQuery', callback_query_id=cb_id)
        return None

    jobs = load_jobs()
    job = jobs.get(jid)
    if not job:
        call('answerCallbackQuery', callback_query_id=cb_id,
             text='המשרה כבר לא במאגר', show_alert=True)
        return None

    title = (job.get('title') or '')[:40]

    if action == ACT_APPLIED:
        if job.get('status') == 'applied':
            call('answerCallbackQuery', callback_query_id=cb_id,
                 text='כבר סומנה כהוגשה')
            return None
        job['status'] = 'applied'
        job['acted_at'] = _il_now().isoformat(timespec='seconds')
        jobs[jid] = job
        save_jobs(jobs)
        record_application(job)
        call('answerCallbackQuery', callback_query_id=cb_id,
             text=f'✅ נרשם: {title}')
        commit(['jobs.jsonl', 'applications.json'],
               f'Mark applied: {title}')
        return ('applied', job)

    if action == ACT_SKIP:
        job['status'] = 'skipped'
        job['acted_at'] = _il_now().isoformat(timespec='seconds')
        jobs[jid] = job
        save_jobs(jobs)
        call('answerCallbackQuery', callback_query_id=cb_id,
             text=f'🚫 דולג: {title}')
        commit(['jobs.jsonl'], f'Skip: {title}')
        return ('skipped', job)

    call('answerCallbackQuery', callback_query_id=cb_id)
    return None


def refresh_markup(cb, outcome):
    """Redraw the keyboard so the message shows what was done. The press
    happens on a phone; leaving the buttons as they were makes it impossible
    to tell afterwards which jobs were already handled."""
    msg = cb.get('message') or {}
    label = {'applied': '✅ סומן כהוגש', 'skipped': '🚫 דולג'}[outcome[0]]
    job = outcome[1]
    rows = [[{'text': '🔗 פתח את המשרה', 'url': job.get('url')}],
            [{'text': label, 'callback_data': 'noop'}]]
    call('editMessageReplyMarkup',
         chat_id=(msg.get('chat') or {}).get('id'),
         message_id=msg.get('message_id'),
         reply_markup={'inline_keyboard': rows})


# ── Poll loop ───────────────────────────────────────────────────────────────
def poll(deadline, once=False):
    state = load_state()
    offset = state.get('offset')
    handled = 0

    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        # Long poll, but never past the shift's end.
        wait = 0 if once else max(1, min(50, int(remaining)))
        res = call('getUpdates', offset=offset, timeout=wait, limit=20,
                   allowed_updates=['callback_query'])
        if not res.get('ok'):
            time.sleep(5)
            continue

        updates = res.get('result') or []
        for u in updates:
            offset = u['update_id'] + 1
            cb = u.get('callback_query')
            if not cb:
                continue
            outcome = handle_callback(cb)
            if outcome:
                refresh_markup(cb, outcome)
                handled += 1
                print(f'  [listener] {outcome[0]}: '
                      f'{(outcome[1].get("title") or "")[:48]}')

        if updates:
            state['offset'] = offset
            save_state(state)
            commit(['listener_state.json'], 'listener offset')

        if once:
            break

    print(f'[listener] shift over — {handled} press(es) handled')
    return handled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=int, default=20700,
                    help='how long this shift lasts (default 5h45m)')
    ap.add_argument('--once', action='store_true',
                    help='drain whatever is queued and exit')
    args = ap.parse_args()

    if not TOKEN or not CHAT_ID:
        print('[listener] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set')
        return 1

    print(f'[listener] starting {_il_now():%Y-%m-%d %H:%M} IL, '
          f'{"single drain" if args.once else f"{args.seconds}s shift"}')
    poll(time.time() + (0 if args.once else args.seconds), once=args.once)
    return 0


if __name__ == '__main__':
    sys.exit(main())
