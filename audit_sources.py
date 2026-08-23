#!/usr/bin/env python3
"""Per-source health check: how many jobs each scraper produces, and where they
die.

This exists because four scrapers were broken for weeks and nothing said so.
Dialog asked for a category that does not exist, Nisha ran a WordPress site
search that answered "QA Manager" with an accountant, SQLink never sent the
role at all, and AllJobs pointed three roles at the security-guarding trade.
From the outside every one of them looked like a quiet source.

The trap is counting raw scraper output. A source can return 80 rows a scan and
be completely broken; the only number that means anything is how many survive
the filters. So that is what this reports, per source and per role, along with
the stage each job dies at.

    python audit_sources.py              # scheduled sources, all roles
    python audit_sources.py --all        # every registered scraper
    python audit_sources.py --source dialog --role "Project Manager"

Read-only. Scrapes, counts, sends nothing and records nothing.
"""
import argparse
import ast
import re
import sys
import textwrap
import time

import job_server as js

HERE = __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0]


def _load_gates():
    """_is_mgmt and _BAD_TITLE_KW live inside _run_notify_job, so lift them out
    of the source rather than retyping them — a copy here would drift."""
    src = open(js.__file__, encoding='utf-8').read()
    ns = {}
    exec(textwrap.dedent(
        re.search(r'( {4}def _is_mgmt\(title\):.*?\n\n)', src, re.S).group(1)), ns)
    bad = ast.literal_eval(textwrap.dedent(
        re.search(r'_BAD_TITLE_KW = (\[.*?\n    \])', src, re.S).group(1)))
    nontech = ast.literal_eval(textwrap.dedent(
        re.search(r'_NONTECH = (\[.*?\n    \])', src, re.S).group(1)))
    return ns['_is_mgmt'], bad, nontech


_IS_MGMT, _BAD, _NONTECH = _load_gates()

STAGES = ['not management', 'bad keyword', 'off topic', 'non-tech company']


def stage_of(job):
    """Which gate a job dies at, or None if it survives all of them."""
    t = job.get('title') or ''
    c = job.get('company') or ''
    if not _IS_MGMT(t):
        return 'not management'
    if any(k in t.lower() for k in _BAD):
        return 'bad keyword'
    if not js._RELEVANT_TITLE_RE.search(t):
        return 'off topic'
    if any(k in (t + ' ' + c).lower() for k in _NONTECH):
        return 'non-tech company'
    return None


def audit(sources, roles, verbose):
    print(f'window={js._SCAN_WINDOW}  roles={len(roles)}  sources={len(sources)}')
    print()
    summary = {}

    for src in sources:
        fn = js.SCRAPERS.get(src)
        if not fn:
            print(f'{src}: not registered in SCRAPERS')
            continue
        raw_total, deaths, survivors, errors = 0, {s: 0 for s in STAGES}, set(), []
        empty_roles = []

        for role in roles:
            try:
                jobs = fn(role, js._SCAN_WINDOW)
            except Exception as e:
                errors.append(f'{role}: {type(e).__name__}: {e}'[:90])
                continue
            if not jobs:
                empty_roles.append(role)
            raw_total += len(jobs)
            for j in jobs:
                s = stage_of(j)
                if s is None:
                    survivors.add(j.get('url'))
                else:
                    deaths[s] += 1
            if verbose and jobs:
                hits = [j for j in jobs if stage_of(j) is None]
                print(f'  {src:<12} {role:<30} {len(jobs):>3} raw -> {len(hits):>2} ok')
                for h in hits[:3]:
                    print(f'{"":>16}{(h.get("title") or "")[:60]}')
            time.sleep(0.4)

        summary[src] = (raw_total, len(survivors), deaths, empty_roles, errors)

    print()
    print('=' * 78)
    print(f'{"source":<13}{"raw":>6}{"on-target":>11}   where the rest died')
    print('=' * 78)
    for src, (raw, ok, deaths, empty, errors) in summary.items():
        died = ', '.join(f'{k} {v}' for k, v in deaths.items() if v)
        flag = '  <-- PRODUCES NOTHING' if ok == 0 else ''
        print(f'{src:<13}{raw:>6}{ok:>11}   {died or "-"}{flag}')
        if empty:
            print(f'{"":<13}roles returning zero rows: {", ".join(empty)[:60]}')
        for e in errors[:2]:
            print(f'{"":<13}ERROR {e}')

    total_ok = sum(v[1] for v in summary.values())
    broken = [s for s, v in summary.items() if v[1] == 0]
    print('-' * 78)
    print(f'{"TOTAL":<13}{sum(v[0] for v in summary.values()):>6}{total_ok:>11}')
    if broken:
        print()
        print(f'!! {len(broken)} source(s) produced nothing on target: {", ".join(broken)}')
        print('   A source that scrapes rows but never passes one is a broken')
        print('   scraper, not a quiet market. Check that it receives the role.')
    return 1 if broken else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true',
                    help='every scraper, not just the scheduled ones')
    ap.add_argument('--source', action='append', help='limit to these sources')
    ap.add_argument('--role', action='append', help='limit to these roles')
    ap.add_argument('-v', '--verbose', action='store_true',
                    help='per-role detail and sample titles')
    args = ap.parse_args()

    sources = (args.source or
               (list(js.SCRAPERS) if args.all else list(js.SCHEDULED_SOURCES)))
    roles = args.role or list(js.SCHEDULED_ROLES)
    return audit(sources, roles, args.verbose)


if __name__ == '__main__':
    sys.exit(main())
