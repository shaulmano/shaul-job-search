#!/usr/bin/env python3
"""Scan the three boards that block the cloud, from Shaul's own machine.

Malam Team, SQLink and One1 answer a GitHub runner with HTTP 403 behind
Cloudflare - "Just a moment..." for two of them and a WAF block page for the
third, measured 11/10/2026. It is not a selector that moved and no code in the
scrapers can fix it: the block is on the address the request comes from. So
those three were taken out of SCHEDULED_SOURCES and live here instead, where
the request leaves a home connection and the boards answer normally.

Everything else stays in the cloud. This scans three sources, writes what it
finds straight into the situation room's database, and touches nothing else -
no git, no jobs.jsonl, no Telegram. That matters: the hourly cloud run commits
those files, and a local run doing the same is what left the working copy stuck
mid-rebase on 18/08/2026.

Output is English on purpose. Hebrew comes out reversed in PowerShell, and this
runs in a scheduled window Shaul reads at a glance.

    python local_blocked_scan.py              # the three blocked boards
    python local_blocked_scan.py sqlink       # just one, for checking
    python local_blocked_scan.py --dry-run    # scan and print, write nothing
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1/11/2026: malamteam יצא מכאן וחזר לענן, שהוא כבר לא חוסם אותו, ו-secretjobs
# נכנס. הוא מחזיר 403 לראנר של GitHub, ומפה הוא גם מרענן את העותק השמור של
# רשימת המשרות שלו, שבלי ריענון מזקין עד שאף משרה בו לא עוברת את סינון הגיל.
BLOCKED_SOURCES = ['secretjobs', 'sqlink', 'one1']
PROJECT_REF = os.environ.get('SUPABASE_PROJECT_REF', 'egxsgxoecucmwaktprez')
BATCH = 100

# Same transient set the situation room's own sync uses: Supabase drops the
# occasional request and a retry costs less than a failed run.
_TRANSIENT = ('upstream connect error', 'connection termination', '502', '503',
              '504', 'timeout', 'EOF', 'reset by peer')


def log(msg):
    """One line, timestamped, flushed. The window is the only progress report."""
    print(f'[{datetime.now():%H:%M:%S}] {msg}', flush=True)


def sb_token():
    if os.environ.get('SUPABASE_ACCESS_TOKEN'):
        return os.environ['SUPABASE_ACCESS_TOKEN']
    path = os.path.expanduser('~/.situation-room/sb-token')
    if not os.path.isfile(path):
        raise SystemExit(f'No Supabase token at {path}')
    return open(path).read().strip()


def sql(query, attempts=4):
    """POST via curl: urllib and requests are refused by Cloudflare (error 1010)."""
    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        json.dump({'query': query}, fh)
    last = None
    try:
        for attempt in range(attempts):
            out = subprocess.run(
                ['curl', '-s', '--max-time', '180', '-X', 'POST',
                 f'https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query',
                 '-H', f'Authorization: Bearer {sb_token()}',
                 '-H', 'Content-Type: application/json',
                 '--data-binary', f'@{path}'],
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=200,
            ).stdout or ''
            if out.strip().startswith('{') and '"message"' in out:
                last = out[:300]
                if any(t in out for t in _TRANSIENT) and attempt < attempts - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(last)
            if not out.strip() and attempt < attempts - 1:
                time.sleep(2 ** attempt)
                continue
            return json.loads(out) if out.strip() else []
    finally:
        os.unlink(path)
    raise RuntimeError(last or 'no response from Supabase')


def q(v):
    if v is None or v == '':
        return 'null'
    return "'" + str(v).replace("'", "''") + "'"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    dry = '--dry-run' in sys.argv
    sources = args or BLOCKED_SOURCES

    log('Local scan: the boards Cloudflare blocks in the cloud')
    log(f'Sources: {", ".join(sources)}')

    import job_server as js
    import foreign_filter
    foreign_filter.install(js)

    roles = js.SCHEDULED_ROLES
    log(f'Roles: {len(roles)}')

    found, per_source, errors = [], {}, {}
    for src in sources:
        scraper = js.SCRAPERS.get(src)
        if not scraper:
            log(f'  {src}: not registered, skipping')
            errors[src] = 'not registered'
            per_source[src] = 0
            continue
        got = 0
        for role in roles:
            try:
                jobs = scraper(role, js._SCAN_WINDOW)
            except Exception as e:
                log(f'  {src} / {role}: ERROR {type(e).__name__}: {e}')
                # The first error is the useful one. Later roles usually fail
                # the same way, and a reason field holding twelve copies of it
                # tells nobody anything.
                errors.setdefault(src, f'{type(e).__name__}: {e}'[:200])
                continue
            if jobs:
                found.extend(jobs)
                got += len(jobs)
            log(f'  {src} / {role}: {len(jobs)} rows')
        per_source[src] = got
        log(f'{src}: {got} rows total')

    # One row per url. The boards repeat the same posting across roles.
    unique = {}
    for j in found:
        u = j.get('url')
        if u and u not in unique:
            unique[u] = j
    rows = list(unique.values())
    log(f'{len(found)} rows scraped, {len(rows)} unique by url')

    # The situation room decides on-target by title, exactly as its own sync
    # does, so a job arriving by this path is treated no differently.
    on_target_kw = ('qa', 'quality', 'test', 'release', 'delivery', 'program',
                    'project', 'pmo', 'בדיקות', 'איכות', 'פרויקט', 'תוכנית')

    def on_target(j):
        return any(k in (j.get('title') or '').lower() for k in on_target_kw)

    if dry:
        log('--dry-run: not writing. Sample:')
        for j in rows[:10]:
            log(f'  {j.get("source")} | {j.get("title")} | {j.get("company")}')
        return

    # Which of these the database already has. Without this the run cannot say
    # how many postings are actually new, and "scanned 468" reads like 468
    # arrived when the real number may be zero.
    known = set()
    urls = [j['url'] for j in rows]
    for i in range(0, len(urls), 200):
        try:
            got = sql('select url from jobs where url in (%s);'
                      % ','.join(q(u) for u in urls[i:i + 200]))
            known.update(r['url'] for r in (got or []))
        except Exception as e:
            # Not worth failing the run over. The count degrades, the write
            # does not.
            log(f'  could not check existing urls: {type(e).__name__}: {e}')
            break

    log(f'{len(rows) - len(known)} of them are new, {len(known)} already known')

    log(f'Writing {len(rows)} rows to the situation room...')
    written = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        vals = ','.join(
            '(%s,%s,%s,%s,%s,%s,%s,now(),now(),%s)' % (
                q(js._job_id(j['url'])),
                q((j.get('title') or '')[:200]),
                q((j.get('company') or '')[:120] or None),
                q(j.get('source') or 'unknown'),
                q(j['url']),
                q((j.get('location') or '')[:120] or None),
                q(j.get('date') or None),
                'true' if any(k in (j.get('title') or '').lower()
                              for k in on_target_kw) else 'false',
            )
            for j in chunk
        )
        # Conflict on the url, not the id: the bot's file and a live scan give
        # the same posting two different ids, and the url is what identifies it.
        sql(
            'insert into jobs '
            '(id,title,company,source,url,location,posted,first_seen,last_seen,on_target) '
            'values %s on conflict (url) do update set title=excluded.title, '
            'company=excluded.company, location=excluded.location, '
            'posted=excluded.posted, last_seen=excluded.last_seen, '
            'on_target=excluded.on_target;' % vals
        )
        written += len(chunk)
        log(f'  wrote {written}/{len(rows)}')

    # Record the run in `scans`, the same table the cloud sources write to, so
    # the sources screen in the situation room shows this path too.
    #
    # Until 1.11.2026 it did not, and the consequence was not cosmetic: a run
    # that never fired, or fired and found nothing, looked exactly like a quiet
    # market. Shaul noticed only weeks later, by the absence of jobs. A source
    # that reports nothing cannot be seen to be broken.
    by_source = {}
    for j in rows:
        s = j.get('source') or 'unknown'
        cur = by_source.setdefault(s, {'raw': 0, 'on': 0, 'fresh': 0})
        cur['raw'] += 1
        if on_target(j):
            cur['on'] += 1
        if j['url'] not in known:
            cur['fresh'] += 1

    log('Recording the run...')
    for src in sources:
        c = by_source.get(src, {'raw': 0, 'on': 0, 'fresh': 0})
        reason = errors.get(src)
        # No error and no rows is still a failure worth seeing: a board that
        # answers politely with nothing is a scraper whose selector moved.
        if reason is None and per_source.get(src, 0) == 0:
            reason = 'returned nothing'
        try:
            sql(
                'insert into scans (source, raw, on_target, fresh, failed, '
                'reason, ran_at) values (%s,%s,%s,%s,%s,%s,now());' % (
                    q(src), per_source.get(src, 0), c['on'], c['fresh'],
                    'true' if reason else 'false', q(reason),
                )
            )
        except Exception as e:
            log(f'  could not record {src}: {type(e).__name__}: {e}')

    log('Done.')
    for src in sources:
        c = by_source.get(src, {'raw': 0, 'on': 0, 'fresh': 0})
        note = errors.get(src) or ('returned nothing'
                                   if per_source.get(src, 0) == 0 else '')
        log(f'  {src}: {per_source.get(src, 0)} scraped, {c["on"]} on target, '
            f'{c["fresh"]} new{" | " + note if note else ""}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f'FAILED: {type(e).__name__}: {e}')
        raise
