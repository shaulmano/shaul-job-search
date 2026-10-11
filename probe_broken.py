#!/usr/bin/env python3
"""Live probe for the two scrapers that produce nothing: SQLink and One1.

Written to run on a GitHub runner, because the sites answer there and not from
a sandbox. It prints what each endpoint actually returns — status, size, page
title, how many of the elements the scraper looks for exist — so a fix is based
on the current page instead of on what the page used to be.

Read-only. Fetches, counts, sends nothing and records nothing.

    python probe_broken.py
"""
import re
import sys

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as cf
    CF = True
except ImportError:                                   # pragma: no cover
    CF = False
    import requests as cf                             # type: ignore


def _get(url, **kw):
    kw.setdefault('timeout', 25)
    if CF:
        kw.setdefault('impersonate', 'chrome124')
    return cf.get(url, **kw)


def _title(html):
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    return (m.group(1).strip()[:90] if m else '(none)')


def probe_sqlink():
    print('\n=== SQLink ===')
    urls = [
        'https://www.sqlink.com/career/db/',
        'https://www.sqlink.com/career/dba/',
        'https://www.sqlink.com/career/',
        'https://www.sqlink.com/',
    ]
    for u in urls:
        try:
            r = _get(u)
        except Exception as e:
            print(f'{u} -> ERROR {type(e).__name__}: {e}')
            continue
        html = r.text or ''
        soup = BeautifulSoup(html, 'html.parser')
        # What the scraper currently looks for, and a few plausible successors.
        counts = {
            'article': len(soup.select('article')),
            '.job-item': len(soup.select('.job-item')),
            '[class*=job]': len(soup.select('[class*="job"]')),
            'li.wpjb-loop-row': len(soup.select('li.wpjb-loop-row')),
            'a[href*=career]': len(soup.select('a[href*="career"]')),
            'a[href*=job]': len(soup.select('a[href*="job"]')),
        }
        print(f'{u} -> HTTP {r.status_code}, {len(html)} bytes, title={_title(html)}')
        print(f'    {counts}')
        if r.status_code == 200 and len(html) > 2000:
            hrefs = [a.get('href', '') for a in soup.find_all('a', href=True)]
            jobish = [h for h in hrefs if re.search(r'(job|career|position|משרה)', h, re.I)]
            print(f'    sample job-ish links: {jobish[:6]}')


def probe_one1():
    print('\n=== One1 ===')
    base = 'https://www.one1.co.il'
    try:
        r = _get(f'{base}/careers/')
        html = r.text or ''
        print(f'{base}/careers/ -> HTTP {r.status_code}, {len(html)} bytes, title={_title(html)}')
        soup = BeautifulSoup(html, 'html.parser')
        print(f'    accordion_item in page: {len(soup.select(".accordion_item"))}')
        print(f'    job_title spans: {len(soup.select(".job_title"))}')
        # The page tells us which ajax action it calls; the old one may be gone.
        actions = sorted(set(re.findall(r'action["\']?\s*[:=]\s*["\']([a-z0-9_]+)', html, re.I)))
        print(f'    ajax actions named in page: {actions[:12]}')
        nonce = sorted(set(re.findall(r'["\']([a-z0-9_]*nonce[a-z0-9_]*)["\']\s*:\s*["\']([a-f0-9]{6,})', html, re.I)))
        print(f'    nonce-looking pairs: {[(k, "<redacted>") for k, _ in nonce][:6]}')
    except Exception as e:
        print(f'{base}/careers/ -> ERROR {type(e).__name__}: {e}')

    # The call the scraper makes today.
    from urllib.parse import quote
    post_data = ('action=oneglobal_search_job_ajax&catid='
                 f'&searchtype=catsearch&career_page_link={quote(base + "/careers/")}')
    try:
        if CF:
            r = cf.post(f'{base}/wp-admin/admin-ajax.php?lang=he', data=post_data,
                        impersonate='chrome124', timeout=25,
                        headers={'Referer': f'{base}/careers/',
                                 'Content-Type': 'application/x-www-form-urlencoded'})
        else:
            r = cf.post(f'{base}/wp-admin/admin-ajax.php?lang=he', data=post_data, timeout=25,
                        headers={'Referer': f'{base}/careers/',
                                 'Content-Type': 'application/x-www-form-urlencoded'})
        body = r.text or ''
        print(f'admin-ajax -> HTTP {r.status_code}, {len(body)} bytes, '
              f'content-type={r.headers.get("content-type", "?")}')
        print(f'    first 200 chars: {body[:200]!r}')
    except Exception as e:
        print(f'admin-ajax -> ERROR {type(e).__name__}: {e}')


if __name__ == '__main__':
    print(f'curl_cffi available: {CF}')
    which = sys.argv[1:] or ['sqlink', 'one1']
    if 'sqlink' in which:
        probe_sqlink()
    if 'one1' in which:
        probe_one1()
