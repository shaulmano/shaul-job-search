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

BLOCKED_SOURCES = ['malamteam', 'sqlink', 'one1']
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

    found, per_source = [], {}
    for src in sources:
        scraper = js.SCRAPERS.get(src)
        if not scraper:
            log(f'  {src}: not registered, skipping')
            continue
        got = 0
        for role in roles:
            try:
                jobs = scraper(role, js._SCAN_WINDOW)
            except Exception as e:
                log(f'  {src} / {role}: ERROR {type(e).__name__}: {e}')
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

    if not rows:
        log('Nothing to write. Done.')
        return

    # The situation room decides on-target by title, exactly as its own sync
    # does, so a job arriving by this path is treated no differently.
    on_target_kw = ('qa', 'quality', 'test', 'release', 'delivery', 'program',
                    'project', 'pmo', 'בדיקות', 'איכות', 'פרויקט', 'תוכנית')

    if dry:
        log('--dry-run: not writing. Sample:')
        for j in rows[:10]:
            log(f'  {j.get("source")} | {j.get("title")} | {j.get("company")}')
        return

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

    log('Done.')
    for src, n in per_source.items():
        log(f'  {src}: {n}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f'FAILED: {type(e).__name__}: {e}')
        raise
