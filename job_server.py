#!/usr/bin/env python3
"""
Job Search Server — backend for job-search-hub.html
Uses Playwright (headless Chrome) for JS-rendered Israeli sites.
Run via start_jobs.bat
"""

import collections
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
import requests
from bs4 import BeautifulSoup

# GitHub Actions runners are UTC, so timestamps in the messages were three hours
# behind. Pin them to Israel time instead of trusting the machine clock.
try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo('Asia/Jerusalem')
except Exception:      # no IANA database (bare Windows) — local clock is already IL
    _TZ = None


def _now_il():
    return datetime.now(_TZ) if _TZ else datetime.now()

try:
    from curl_cffi import requests as cf_requests
    CURL_CFFI_OK = True
except ImportError:
    CURL_CFFI_OK = False

# Shaul's rule, 26/08/2026: nothing older than two days from the day of the
# scan. Applied wherever a source states a date - some give none, and those
# ride on _SCAN_WINDOW instead, which is the closest thing to a date they have.
_MAX_JOB_AGE_DAYS = 2

PORT = int(os.environ.get('PORT', 8765))
PW_SEMAPHORE = threading.Semaphore(1)       # max 1 Chromium instance at once
_LINKEDIN_LOCK = threading.Semaphore(1)     # max 1 LinkedIn request at a time

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

TIME_MAP = {'20h': 'r72000', '36h': 'r129600', '72h': 'r259200', 'week': 'r604800', 'month': 'r2592000'}

# ── Playwright helper ─────────────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False
    print('⚠  Playwright not installed — Israeli sites will be skipped.')
    print('   Run: pip install playwright && playwright install chromium\n')

def pw_get_html(url, wait_selector=None, wait_ms=2500):
    """Load a page with headless Chromium and return the rendered HTML."""
    with PW_SEMAPHORE:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent=HEADERS['User-Agent'],
                    locale='he-IL',
                )
                page.goto(url, timeout=25000, wait_until='domcontentloaded')
                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=6000)
                    except Exception:
                        page.wait_for_timeout(wait_ms)
                else:
                    page.wait_for_timeout(wait_ms)
                return page.content()
            finally:
                browser.close()


# ── LinkedIn (guest API — no login, no Playwright needed) ─────────────────────
def _linkedin_fetch_recruiter(job):
    """Fetch recruiter name+URL and SaaS signals from the LinkedIn job detail
    page (guest API) — one request, reused for both, so this doesn't add any
    extra load on top of what already runs."""
    import re
    try:
        # URL may be slug form: .../senior-pm-at-company-4413268911/
        m = re.search(r'(\d{7,})/?$', job['url'])
        if not m:
            return job
        job_id = m.group(1)
        detail_url = f'https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}'
        r = requests.get(detail_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return job
        soup = BeautifulSoup(r.text, 'html.parser')
        # Recruiter link is always an <a href*="linkedin.com/in/"> inside .message-the-recruiter
        link_el = soup.select_one('.message-the-recruiter a[href*="linkedin.com/in/"]')
        if link_el:
            job['recruiter_name'] = link_el.get_text(strip=True)
            job['recruiter_url']  = link_el.get('href', '').split('?')[0]
        desc_el = soup.select_one('.description__text')
        if desc_el:
            job['li_description'] = desc_el.get_text(' ', strip=True)[:3000]
        for item in soup.select('.description__job-criteria-item'):
            sub = item.select_one('.description__job-criteria-subheader')
            # Accept-Language is he-IL, so this header usually reads "תעשיות"
            # rather than "Industries" — match both.
            if sub and ('industr' in sub.get_text(strip=True).lower()
                        or 'תעשי' in sub.get_text(strip=True)):
                val_el = item.select_one('.description__job-criteria-text')
                if val_el:
                    job['li_industries'] = val_el.get_text(strip=True)
                break
    except Exception:
        pass
    return job


# The guest endpoint ignores count= and answers with 10 results whatever you
# ask for, so a single request only ever saw the first ten postings per role.
# start= is honoured, and measuring it gave 48-50 unique jobs over five pages
# against 10 from one. Five pages x nine roles is 45 requests at a 3s throttle,
# about 160s of the 900s scan budget.
_LINKEDIN_MAX_PAGES = 5
_LINKEDIN_PAGE_SIZE = 10
_LINKEDIN_ENRICH_CAP = 20


def _linkedin_page(role, tpr, start):
    """One page of results. Returns the parsed HTML, or raises after 3 x 429."""
    url = (
        'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search'
        f'?keywords={quote(role)}&location=Israel&f_TPR={tpr}'
        f'&start={start}&count=50'
    )
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f'  [linkedin] 429 — waiting {wait}s before retry...')
                time.sleep(wait)
                continue
            r.raise_for_status()
            time.sleep(3)   # throttle: min 3s between LinkedIn requests
            return r.text
        except requests.exceptions.HTTPError:
            if attempt == 2:
                raise
    raise Exception('LinkedIn 429 after 3 retries')


def search_linkedin(role, time_filter='20h'):
    import concurrent.futures
    tpr = TIME_MAP.get(time_filter, 'r72000')

    jobs, seen_urls = [], set()
    with _LINKEDIN_LOCK:
        for page in range(_LINKEDIN_MAX_PAGES):
            start = page * _LINKEDIN_PAGE_SIZE
            try:
                html = _linkedin_page(role, tpr, start)
            except Exception:
                # Page one failing is a real error; later pages failing just
                # means this role is done, and what we already have still counts.
                if page == 0:
                    raise
                break

            soup = BeautifulSoup(html, 'html.parser')
            before = len(jobs)
            for card in soup.find_all('li'):
                title_el   = card.find('h3', class_='base-search-card__title')
                company_el = card.find('h4', class_='base-search-card__subtitle')
                link_el    = card.find('a', class_='base-card__full-link')
                time_el    = card.find('time')
                loc_el     = card.find('span', class_='job-search-card__location')

                if not (title_el and company_el and link_el):
                    continue

                href = link_el.get('href', '').split('?')[0]
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                jobs.append({
                    'title':          title_el.get_text(strip=True),
                    'company':        company_el.get_text(strip=True),
                    'date':           time_el.get('datetime', '')[:10] if time_el else '',
                    'url':            href,
                    'source':         'LinkedIn',
                    'location':       loc_el.get_text(strip=True) if loc_el else 'Israel',
                    'recruiter_name': '',
                    'recruiter_url':  '',
                })

            # Stop only on an empty page. A short one is not the end of the
            # results: LinkedIn regularly returns 9 parseable cards out of 10,
            # and stopping on that cost 39 of the 48 jobs for "Project Manager".
            if len(jobs) - before == 0:
                break

    # Enrich with recruiter info in parallel (best-effort, 15s budget).
    # Paging multiplied the job count by five, and this fires one detail request
    # per job, so it is capped: past the cap the extra requests are the ones most
    # likely to earn a 429 on the searches that matter, and the 15s budget was
    # never going to reach them anyway. Only the title gates decide relevance;
    # the description this fetches is used solely for the SaaS tag.
    if jobs:
        head, tail = jobs[:_LINKEDIN_ENRICH_CAP], jobs[_LINKEDIN_ENRICH_CAP:]
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                head = list(ex.map(_linkedin_fetch_recruiter, head, timeout=15))
        except Exception:
            pass
        jobs = head + tail

    return jobs


# ── Generic Playwright scraper ────────────────────────────────────────────────
def pw_scrape(url, source, base_url, selectors, title_sel, link_sel,
              company_sel=None, date_sel=None, wait_sel=None):
    if not PLAYWRIGHT_OK:
        return []
    try:
        html = pw_get_html(url, wait_selector=wait_sel)
    except Exception as e:
        print(f'  [{source}] Playwright error: {e}')
        return []

    soup = BeautifulSoup(html, 'html.parser')
    jobs = []

    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            for card in cards:
                t_el = card.select_one(title_sel)
                l_el = card.select_one(link_sel) or card.find('a', href=True)
                if not t_el or not l_el:
                    continue
                title = t_el.get_text(strip=True)[:120]
                if len(title) < 4:
                    continue
                href = l_el.get('href', '')
                if href and not href.startswith('http'):
                    href = base_url + href
                company = ''
                if company_sel:
                    c_el = card.select_one(company_sel)
                    if c_el:
                        company = c_el.get_text(strip=True)
                date = ''
                if date_sel:
                    d_el = card.select_one(date_sel)
                    if d_el:
                        date = d_el.get('datetime', d_el.get_text(strip=True))[:10]
                jobs.append({
                    'title': title, 'company': company, 'date': date,
                    'url': href, 'source': source, 'location': 'Israel',
                })
            if jobs:
                break  # first matching selector is enough

    seen, unique = set(), []
    for j in jobs:
        if j['url'] and j['url'] not in seen and base_url in j['url']:
            seen.add(j['url'])
            unique.append(j)
    return unique[:50]


# ── AllJobs ───────────────────────────────────────────────────────────────────
# Position ids, taken from the taxonomy AllJobs ships in
# /JavaScript/SearchEngineData.js — 1347 categories, each with a live vacancy
# count. Re-read it if these ever look stale.
#
# The previous map was wrong in ways that quietly cost most of this source:
#   380  is "מנהל פרויקטים באבטחה וביטחון" — the security-guarding trade, not
#        software. It was what both Project Manager and Program Manager asked
#        for, which is where the guard-company postings came from.
#   1554 is "מנהל פרויקטים אבטחת מידע/סייבר", cyber only, 31 vacancies.
#   432 / 1532 / 1533 / 1913 / 1984 / 2011 are individual-contributor testing
#        and automation categories — rejected downstream anyway, so every one
#        of them was scraping pages to throw away.
# And the two big software project-management categories, 237 and 1548, were
# never queried at all: 335 vacancies between them.
_ALLJOBS_POSITION_IDS = {
    'qa manager':                    [824, 1365],   # מנהל איכות | מנהל QA, ראש צוות QA
    'qa director':                   [824, 1365],
    'head of qa':                    [824, 1365],
    'qa team leader':                [1365, 824],
    'project manager':               [237, 1548, 1187, 759],
    'program manager':               [237, 1548, 1187],
    'release manager':               [237, 1548],   # no release-specific category exists
    'delivery manager':              [237, 1548, 1187],
    'professional services manager': [1647, 237],   # Professional Services
}

# 237  מנהל פרויקטים בתוכנה              129 vacancies
# 1548 מנהל פרויקטים במערכות מידע        206
# 1187 PMO                                72
# 759  מנהל פרויקטים במחשבים ורשתות       49
# 1647 Professional Services              17


def _alljobs_position_ids(role):
    r = role.lower().strip()
    if r in _ALLJOBS_POSITION_IDS:
        return _ALLJOBS_POSITION_IDS[r]
    # Substring fallback, longest key first. Iteration order used to decide it,
    # so "QA Team Leader" matched the bare "qa" entry before "qa team lead" and
    # got the generic testing categories instead of its own.
    for key in sorted(_ALLJOBS_POSITION_IDS, key=len, reverse=True):
        if key in r or r in key:
            return _ALLJOBS_POSITION_IDS[key]
    # Falling back to QA for a project role is worse than returning nothing:
    # it fills the scan with jobs that cannot match and hides the miss.
    print(f'  [AllJobs] no position id mapped for {role!r} — skipping')
    return []

def search_alljobs(role, time_filter='20h'):
    if not CURL_CFFI_OK:
        return []
    base = 'https://www.alljobs.co.il'
    pos_ids = _alljobs_position_ids(role)
    jobs, seen = [], set()
    for pos_id in pos_ids:
        try:
            url = f'{base}/SearchResultsGuest.aspx?page=1&position={pos_id}&type=&city=&region='
            r = cf_requests.get(url, impersonate='chrome124', timeout=15)
            soup = BeautifulSoup(r.content.decode('utf-8', errors='replace'), 'html.parser')
            boxes = soup.find_all('div', id=re.compile(r'^job-box-container'))
            for box in boxes:
                job_id = box.get('id', '').replace('job-box-container', '')
                if not job_id or job_id in seen:
                    continue
                seen.add(job_id)
                company_a = box.find('a', href=re.compile(r'cid='))
                company = company_a.get_text(strip=True) if company_a else ''
                title = ''
                h2 = box.find('h2')
                if h2:
                    title = h2.get_text(' ', strip=True)
                if not title:
                    hl = box.select_one('.job-content-top-title-highlight')
                    if hl:
                        raw = hl.get_text(' ', strip=True)
                        company_txt = company_a.get_text(strip=True) if company_a else ''
                        title = raw.replace(company_txt, '').strip()
                if not title:
                    title = role
                jobs.append({
                    'title': title[:120], 'company': company, 'date': '',
                    'url': f'{base}/Search/UploadSingle.aspx?JobID={job_id}',
                    'source': 'AllJobs', 'location': 'Israel',
                })
        except Exception as e:
            print(f'  [AllJobs] pos={pos_id} error: {e}')
    return jobs[:50]


# ── Drushim ───────────────────────────────────────────────────────────────────
_DRUSHIM_GENERIC = {'manager','director','head','lead','senior','sr','junior','jr',
                    'of','the','and','at','in','for','a','an'}
_DRUSHIM_HE_MAP  = {
    'qa':          ['qa','בדיקות','איכות','אוטומציה','qc'],
    'quality':     ['איכות','qa','qc','בדיקות'],
    'test':        ['בדיקות','qa','test','אוטומציה'],
    'automation':  ['אוטומציה','automation','בדיקות'],
    'devops':      ['devops','דבאופס','תשתיות','ci'],
    'cyber':       ['סייבר','cyber','אבטחת מידע'],
    'data':        ['data','דאטה','bi','נתונים'],
    'backend':     ['backend','back-end','server','node','python','java'],
    'frontend':    ['frontend','front-end','react','angular','vue'],
    'fullstack':   ['fullstack','full-stack','full stack'],
    'mobile':      ['mobile','ios','android','flutter'],
    'cloud':       ['cloud','ענן','aws','azure','gcp'],
    'project':     ['project','פרויקט','pm','תוכנית','ניהול פרויקט'],
    'program':     ['program','programme','תוכנית','פרוגרם','pmo','פרויקט'],
    'product':     ['product','מוצר','פרודקט'],
}

def _drushim_keywords(role):
    words = [w.lower() for w in role.split()]
    specific = [w for w in words if w not in _DRUSHIM_GENERIC]
    if not specific:
        specific = words
    kws = set(specific)
    for w in specific:
        for key, he_list in _DRUSHIM_HE_MAP.items():
            if key in w or w in key:
                kws.update(he_list)
    return kws

# Seniority words the Drushim search does not reward. Its API matches the whole
# phrase, so "QA Director", "QA Team Leader" and "Release Manager" each returned
# nothing at all — no posting is titled exactly that. Querying the role stripped
# of these as well is the same trick that took Experis from 0 hits to 13.
_DRUSHIM_STRIP = {'manager', 'director', 'head', 'of', 'team', 'leader', 'lead',
                  'senior', 'sr', 'vp', 'chief'}


def _drushim_terms(role):
    terms = [role]
    reduced = ' '.join(w for w in role.split()
                       if w.lower() not in _DRUSHIM_STRIP)
    if reduced and reduced.lower() != role.lower():
        terms.append(reduced)
    return terms


def search_drushim(role, time_filter='20h'):
    if not CURL_CFFI_OK:
        return []
    base = 'https://www.drushim.co.il'
    try:
        result_list, seen_links = [], set()
        for term in _drushim_terms(role):
            url = f'{base}/api/jobs/search?searchterm={quote(term)}'
            r = cf_requests.get(url, impersonate='chrome124', timeout=15,
                                headers={'Referer': base + '/'})
            for job in (r.json().get('ResultList') or []):
                link = (job.get('JobInfo') or {}).get('Link', '')
                if link and link not in seen_links:
                    seen_links.add(link)
                    result_list.append(job)
            # The full phrase is the precise one; only widen when it found
            # nothing, so a role that already works keeps its narrower results.
            if result_list:
                break
        keywords = _drushim_keywords(role)
        jobs = []
        for job in result_list:
            info = job.get('JobInfo', {})
            content = job.get('JobContent', {})
            company_info = job.get('Company', {})
            title = content.get('Name', '') or content.get('FullName', '')
            link = info.get('Link', '')
            if not title or not link:
                continue
            title_lower = title.lower()
            if not any(kw in title_lower for kw in keywords):
                continue
            jobs.append({
                'title': title[:120],
                'company': company_info.get('CompanyDisplayName', ''),
                'date': info.get('JumpDate', '')[:10],
                'url': base + link,
                'source': 'Drushim',
                'location': 'Israel',
            })
        return jobs[:50]
    except Exception as e:
        print(f'  [Drushim] API error: {e}')
        return []


# ── GotFriends ────────────────────────────────────────────────────────────────
# Keyed by the exact lowercased role, and search_gotfriends returns nothing for
# a role that is missing — so every entry of SCHEDULED_ROLES has to appear here.
# 'QA Director', 'QA Team Leader' and 'Delivery Manager' did not, which is three
# of the nine roles silently scraping nothing at all.
GOTFRIENDS_ROLE_URLS = {
    'head of qa':               '/jobslobby/qa/head-of-qa-team/',
    'qa manager':               '/jobslobby/qa/qa-team-leader/',
    'qa director':              '/jobslobby/qa/',
    'qa team leader':           '/jobslobby/qa/qa-team-leader/',
    'delivery manager':         '/jobslobby/executive-position/development-manager-jobs/',
    'director of qa':           '/jobslobby/qa/',
    'r&d program manager':      '/jobslobby/executive-position/development-manager-jobs/',
    'technical program manager':'/jobslobby/executive-position/development-manager-jobs/',
    'program manager':          '/jobslobby/executive-position/development-manager-jobs/',
    'project manager':          '/jobslobby/executive-position/development-manager-jobs/',
    'pmo manager':              '/jobslobby/executive-position/development-manager-jobs/',
    'release manager':          '/jobslobby/executive-position/development-manager-jobs/',
    'professional services manager': '/jobslobby/executive-position/development-manager-jobs/',
}

def _gotfriends_scrape_url(url, role):
    base = 'https://www.gotfriends.co.il'
    try:
        html = pw_get_html(base + url, wait_selector='a[class^="position"]', wait_ms=4000)
    except Exception as e:
        print(f'  [GotFriends] Playwright error: {e}')
        return []
    soup = BeautifulSoup(html, 'html.parser')
    jobs = []
    for card in soup.select('a[class^="position"]'):
        href = card.get('href', '')
        if not href:
            continue
        num_el = card.select_one('.career_num')
        num_text = num_el.get_text(strip=True) if num_el else ''
        title = card.get_text(strip=True).replace(num_text, '').strip()
        if len(title) < 4:
            continue
        jobs.append({
            'title': title[:120],
            'company': 'GotFriends',
            'date': '',
            'url': base + href if not href.startswith('http') else href,
            'source': 'GotFriends',
            'location': 'Israel',
        })
    seen, unique = set(), []
    for j in jobs:
        if j['url'] not in seen:
            seen.add(j['url'])
            unique.append(j)
    return unique[:50]

def search_gotfriends(role, time_filter='20h'):
    if not PLAYWRIGHT_OK:
        return []
    path = GOTFRIENDS_ROLE_URLS.get(role.lower())
    if not path:
        return []
    return _gotfriends_scrape_url(path, role)


# ── Experis ───────────────────────────────────────────────────────────────────
_EXPERIS_GQL   = 'https://experiscontent.experis.co.il/graphql'
_EXPERIS_QUERY = ('query SearchByFilter($where: RootQueryToJobConnectionWhereArgs) {'
                  '  allJob(where: $where) { nodes { title slug } } }')


_EXPERIS_STOPWORDS = {'head', 'of', 'director', 'manager', 'senior', 'vp', 'lead', 'the', 'and'}


def _experis_query(term):
    payload = {
        'operationName': 'SearchByFilter',
        'variables': {'where': {
            'offsetPagination': {'offset': 0, 'size': 50},
            'search': term,
            'taxQuery': {'relation': 'AND', 'taxArray': [
                {'field': 'NAME', 'taxonomy': 'JOBSTATUS', 'terms': 'published'}]},
        }},
        'query': _EXPERIS_QUERY,
    }
    r = requests.post(_EXPERIS_GQL, json=payload,
                      headers={'User-Agent': HEADERS['User-Agent']}, timeout=25)
    r.raise_for_status()
    data = r.json()
    if data.get('errors'):
        raise RuntimeError(str(data['errors'])[:200])
    return ((data.get('data') or {}).get('allJob') or {}).get('nodes') or []


def search_experis(role, time_filter='20h'):
    """Query Experis' GraphQL backend directly.

    Scraping /search?q=<role> returns the same generic listing for every role —
    the site's own page never forwards q into the GraphQL `search` variable, so
    it always asks for "". Calling the endpoint ourselves makes the role count,
    and skips a Playwright launch that took ~5 minutes under load.

    The backend ANDs every word, so "Head of QA" matches nothing. We also query
    the role stripped of seniority words ("QA") and merge — that alone takes
    Head of QA from 0 hits to 13.
    """
    terms = [role]
    reduced = ' '.join(w for w in role.split() if w.lower() not in _EXPERIS_STOPWORDS)
    if reduced and reduced != role:
        terms.append(reduced)

    jobs, seen = [], set()
    for term in terms:
        try:
            nodes = _experis_query(term)
        except Exception as e:
            print(f'  [Experis] GraphQL error for {term!r}: {e}')
            continue
        for n in nodes:
            title = (n.get('title') or '').strip()
            slug  = (n.get('slug') or '').strip()
            if len(title) < 4 or not slug or slug in seen:
                continue
            seen.add(slug)
            jobs.append({
                'title': title[:120], 'company': 'Experis', 'date': '',
                'url': f'https://experis.co.il/job/{slug}',
                'source': 'Experis', 'location': 'Israel',
            })
    return jobs[:50]


# ── Dialog ────────────────────────────────────────────────────────────────────
_DIALOG_CACHE = {}   # {url: (ts, jobs)}

def search_dialog(role, time_filter='20h'):
    if not PLAYWRIGHT_OK:
        return []
    import json as _json
    role_lower = role.lower()
    # /high-tech/jobs/project-management, which this used for every management
    # role, is not a category Dialog has — it answered with the generic index,
    # which is why the source never produced a single on-target job. Measured
    # 19/08/2026: the real pages carry 17 and 12 matches respectively, Delivery
    # Manager among them.
    if any(k in role_lower for k in ['qa', 'quality', 'test']):
        urls = ['https://www.dialog.co.il/high-tech/jobs/qa']
    elif any(k in role_lower for k in ['program', 'project', 'release', 'delivery', 'pmo']):
        urls = ['https://www.dialog.co.il/high-tech/jobs/software/pm',
                'https://www.dialog.co.il/high-tech/jobs/data/project-manager']
    else:
        urls = ['https://www.dialog.co.il/high-tech/jobs']

    if len(urls) > 1:
        merged, seen_urls = [], set()
        for u in urls:
            for j in _dialog_scrape(u):
                if j['url'] not in seen_urls:
                    seen_urls.add(j['url'])
                    merged.append(j)
        return merged[:50]
    return _dialog_scrape(urls[0])


def _dialog_scrape(url):
    import json as _json
    cached = _DIALOG_CACHE.get(url)
    if cached and time.time() - cached[0] < 300:
        print(f'  [Dialog] cached result ({len(cached[1])} jobs)')
        return cached[1]
    try:
        html = pw_get_html(url, wait_selector='div.item_job', wait_ms=5000)
    except Exception as e:
        print(f'  [Dialog] Playwright error: {e}')
        return []
    soup = BeautifulSoup(html, 'html.parser')

    # JSON-LD contains structured data for the first 20 jobs
    for s in soup.find_all('script', type='application/ld+json'):
        try:
            data = _json.loads(s.string)
            if data.get('@type') == 'ItemList':
                jobs = []
                for item in data.get('itemListElement', []):
                    job = item.get('item', {})
                    title = job.get('title', '').strip()
                    job_url = job.get('url', '')
                    if title and job_url:
                        jobs.append({
                            'title': title[:120], 'company': 'Dialog', 'date': '',
                            'url': job_url, 'source': 'Dialog', 'location': 'Israel',
                        })
                if jobs:
                    return jobs[:50]
        except Exception:
            pass

    # Fallback: scrape div.item_job cards
    base = 'https://www.dialog.co.il'
    jobs = []
    for card in soup.select('div.item_job'):
        link = card.select_one('a[href*="positionId"]')
        if not link:
            continue
        href = link.get('href', '')
        if href and not href.startswith('http'):
            href = base + href
        title = link.get_text(strip=True)
        if len(title) < 4:
            continue
        jobs.append({
            'title': title[:120], 'company': 'Dialog', 'date': '',
            'url': href, 'source': 'Dialog', 'location': 'Israel',
        })
    seen, unique = set(), []
    for j in jobs:
        if j['url'] not in seen:
            seen.add(j['url'])
            unique.append(j)
    result = unique[:50]
    _DIALOG_CACHE[url] = (time.time(), result)
    return result


# ── SQLink ────────────────────────────────────────────────────────────────────
def search_sqlink(role, time_filter='20h'):
    """SQLink has no working free-text search — every query parameter tried
    (?s= ?q= ?search= ?keyword=) returns the same page, and the site's only
    forms are CV uploads. It does have curated categories, so point the QA
    roles at the testing one instead of the generic hi-tech index the scraper
    used for everything."""
    role_lower = role.lower()
    if any(k in role_lower for k in ['qa', 'quality', 'test', 'sqa', 'qc']):
        url = 'https://www.sqlink.com/career/db/'          # בדיקות ואוטומציה
    else:
        url = 'https://www.sqlink.com/career/dba/'         # מערכות מידע ותמיכה
    return pw_scrape(
        url=url, source='SQLink', base_url='https://www.sqlink.com',
        selectors=['article', '.job-item', '[class*="job"]', 'li.wpjb-loop-row'],
        title_sel='h2, h3, [class*="title"]',
        link_sel='a',
        wait_sel='a',
    )


# ── SecretJobs ────────────────────────────────────────────────────────────────
# Aggregates the career pages of ~9,000 Israeli companies, which is the one
# thing LinkedIn and the agency boards do not cover — jobs posted only on a
# company's own site.
#
# It is a paid product, but the job pages themselves are public and advertised
# in a sitemap for search engines; robots.txt disallows only /api/, /auth/ and
# /settings/, none of which is touched here. The sitemap is the intended way in.
#
# Two sitemaps answer everything, so there is no per-job request at all: the
# job slug carries the title, and the trailing tokens of that slug are the
# company's own slug, which the companies sitemap lists. Matching the longest
# trailing run resolved the company for 229 of 229 candidates when measured.
_SJ_BASE = 'https://www.secretjobs.ai'
_SJ_CACHE = {}          # {'jobs': (ts, [urls]), 'companies': (ts, {slugs})}
_SJ_TTL = 3600          # one fetch serves a whole scan; the file is ~9 MB
# Seconds to wait after each failed attempt; the last entry is 0 because there
# is nothing after it. Total patience is about two minutes, against a 900s scan
# budget, and every other source runs in parallel while this waits.
_SJ_BACKOFF = [20, 45, 60, 0]

# Their sitemap has no dates, and measuring 25 of the jobs it produced gave a
# median age of 49 days: only 3 in 25 were within a fortnight and half were over
# two months old. Shaul clicked one and LinkedIn said it had closed a month ago.
# Each job page does carry "datePosted", so freshness is checkable - it just
# costs a request per posting, which is why the dates are cached forever below.
# Shaul, 26/08: at most two days back from the day of the scan. A week-old
# posting is of no interest, and measuring this source gave a median age of 49
# days, so without this gate it is mostly a graveyard.
_SJ_MAX_AGE_DAYS = _MAX_JOB_AGE_DAYS
# Date lookups per scan. Each job is fetched once ever and remembered, so this
# only paces the initial fill; at 16 scans a day the candidate set dates itself
# within a day. Anything unchecked waits for the next scan rather than being
# guessed at.
_SJ_DATE_BUDGET = 120

_SJ_ROLE_KEYWORDS = {
    'qa':      ['qa', 'quality', 'test', 'sqa', 'qc'],
    'project': ['project', 'program', 'programme', 'pmo', 'delivery',
                'release', 'professional services'],
}


# Their sitemap comes down reliably from Israel and 504s from the Actions
# region, so the last good copy is kept in the repo. It is committed by the
# workflow like seen_jobs.json, which means a run that cannot reach them still
# has a job list to work from - a few hours stale at worst.
_SJ_SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'secretjobs_snapshot.json')


def _sj_load_snapshot(which):
    try:
        with open(_SJ_SNAPSHOT, encoding='utf-8') as f:
            data = json.load(f)
        got = data.get(which) or []
        return set(got) if which == 'companies' else got
    except Exception:
        return None


def _sj_save_snapshot(which, locs):
    try:
        try:
            with open(_SJ_SNAPSHOT, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data[which] = sorted(locs)
        data[which + '_fetched'] = _now_il().isoformat(timespec='seconds')
        with open(_SJ_SNAPSHOT, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception as e:
        print(f'  [SecretJobs] could not store {which} snapshot: {e}')


def _sj_sitemap(which):
    hit = _SJ_CACHE.get(which)
    if hit and time.time() - hit[0] < _SJ_TTL:
        return hit[1]
    url = f'{_SJ_BASE}/{which}-sitemap.xml'
    # Served by Vercel and generated on demand. From an Israeli address the
    # edge has it cached (X-Vercel-Cache: HIT, 0.33 MB brotli on the wire) and
    # it lands in under a second; from the Actions runner in the US the edge
    # misses, Vercel regenerates, and the gateway times out at 504.
    #
    # A failed request still starts that regeneration, so the fix is patience
    # rather than force: wait long enough for the cache to warm and ask again.
    # Backoff is in tens of seconds, not the 5s that was plainly too short.
    #
    # If it still fails the exception propagates. A source that returns [] on
    # error gets reported as "ran fine, 0 results", which is the exact disguise
    # four broken scrapers hid behind for weeks.
    last = None
    for attempt, wait in enumerate(_SJ_BACKOFF):
        try:
            r = requests.get(url, headers=HEADERS, timeout=90)
            r.raise_for_status()
            if attempt:
                print(f'  [SecretJobs] {which} recovered on attempt {attempt + 1}')
            break
        except Exception as e:
            last = e
            print(f'  [SecretJobs] {which} attempt {attempt + 1}'
                  f'/{len(_SJ_BACKOFF)}: {str(e)[:70]}')
            if wait:
                time.sleep(wait)
    else:
        # Their edge will not serve this from the Actions region, however long
        # we wait. Fall back to the last copy that did come down: a job list a
        # few hours stale still surfaces jobs, and seen_jobs stops repeats.
        stale = _sj_load_snapshot(which)
        if stale:
            print(f'  [SecretJobs] {which} unreachable — using the stored copy '
                  f'({len(stale)} entries)')
            _SJ_CACHE[which] = (time.time(), stale)
            return stale
        raise RuntimeError(
            f'{which} sitemap unreachable after {len(_SJ_BACKOFF)} tries and no '
            f'stored copy exists (Vercel cache miss from this region): {last}')
    locs = [u for u in re.findall(r'<loc>([^<]+)</loc>', r.text) if '/he/' not in u]
    if which == 'companies':
        locs = {u.rsplit('/', 1)[-1] for u in locs if '/companies/' in u}
    print(f'  [SecretJobs] {which} sitemap: {len(locs)} entries')
    _sj_save_snapshot(which, locs)
    _SJ_CACHE[which] = (time.time(), locs)
    return locs


def _sj_split(slug_url, companies):
    """Job title and company out of the slug, no extra request."""
    s = slug_url.rsplit('/', 1)[-1]
    s = re.sub(r'-[0-9a-f]{6}$', '', s)     # trailing content hash
    s = re.sub(r'^\d+-', '', s)             # leading listing number
    parts = s.split('-')
    for i in range(len(parts)):
        cand = '-'.join(parts[i:])
        if cand in companies:
            title = ' '.join(parts[:i]).strip()
            return title.title(), cand.replace('-', ' ').title()
    return s.replace('-', ' ').title(), ''



def _sj_dates():
    try:
        with open(_SJ_SNAPSHOT, encoding='utf-8') as f:
            return json.load(f).get('dates') or {}
    except Exception:
        return {}


def _sj_store_dates(dates):
    try:
        try:
            with open(_SJ_SNAPSHOT, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        data['dates'] = dates
        with open(_SJ_SNAPSHOT, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception as e:
        print(f'  [SecretJobs] could not store dates: {e}')


def _sj_posted(url, dates):
    """datePosted off the job page. Cached forever - a posting's date never
    changes, so each job is fetched at most once ever."""
    if url in dates:
        return dates[url]
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        m = re.search(r'"datePosted"\s*:\s*"(\d{4}-\d{2}-\d{2})', r.text)
        dates[url] = m.group(1) if m else ''
    except Exception:
        dates[url] = ''
    return dates[url]


def _sj_search_link(title, company):
    from urllib.parse import quote_plus
    q = f'"{title}" "{company}"' if company and company != 'SecretJobs' else f'"{title}"'
    return f'https://www.google.com/search?q={quote_plus(q)}'


def search_secretjobs(role, time_filter='20h'):
    """The sitemap carries no lastmod, so time_filter cannot be honoured —
    every listing looks equally fresh. seen_jobs is what stops repeats, which
    means the first scan after this ships reports a backlog and later ones only
    report genuinely new postings."""
    # Deliberately not caught. fetch() in _run_notify_job records the exception
    # and the Telegram status line then says "שגיאה" instead of "רץ תקין, 0
    # תוצאות" - the difference between knowing a source is broken and believing
    # the market was quiet.
    jobs_urls = _sj_sitemap('jobs')
    companies = _sj_sitemap('companies')

    role_lower = role.lower()
    key = 'qa' if any(k in role_lower for k in _SJ_ROLE_KEYWORDS['qa']) else 'project'
    domain = _SJ_ROLE_KEYWORDS[key]
    mgmt = ['manager', 'director', 'head-of', 'team-lead', 'group-lead', 'lead']

    candidates = []
    for u in jobs_urls:
        low = u.lower()
        if not any(k in low for k in mgmt):
            continue
        if not any(k in low for k in domain):
            continue
        title, company = _sj_split(u, companies)
        if len(title) < 4:
            continue
        candidates.append((u, title, company))

    # Age gate. Without it this source is mostly a graveyard: measured median
    # age 49 days, 48% over two months. Dates are cached forever, so the cost
    # is one request per posting ever, and the budget stops a cold start from
    # firing hundreds at once - anything unchecked simply waits for the next scan.
    dates = _sj_dates()
    spent, before = 0, len(dates)
    cutoff = (_now_il().date() - timedelta(days=_SJ_MAX_AGE_DAYS)).isoformat()
    jobs, stale, unknown = [], 0, 0
    for u, title, company in candidates:
        posted = dates.get(u)
        if posted is None:
            if spent >= _SJ_DATE_BUDGET:
                unknown += 1
                continue
            posted = _sj_posted(u, dates)
            spent += 1
        if not posted:
            unknown += 1
            continue
        if posted < cutoff:
            stale += 1
            continue
        jobs.append({
            'title': title[:120],
            'company': company or 'SecretJobs',
            'date': posted,
            'url': u,
            # Their page is a paywall and carries no link to the employer -
            # verified on both the job and company pages, neither has a single
            # outbound link. Title and company are exact, though, so a scoped
            # search lands on the company's own posting in one click.
            'link': _sj_search_link(title, company),
            'source': 'SecretJobs',
            'location': 'Israel',
        })
    if len(dates) != before:
        _sj_store_dates(dates)
    if stale or unknown:
        print(f'  [SecretJobs] {role}: {len(jobs)} fresh, {stale} older than '
              f'{_SJ_MAX_AGE_DAYS}d, {unknown} undated ({spent} lookups)')
    # Higher than the [:50] every other source uses. That cap exists to bound
    # per-job requests, and this source makes none - the whole answer comes out
    # of two sitemaps - so truncating here only loses jobs for nothing.
    return jobs[:200]


# ── Nisha ─────────────────────────────────────────────────────────────────────
_NISHA_ROLE_URLS = {
    'qa': ['https://www.nisha.co.il/positions/qa-team-leader/',
           'https://www.nisha.co.il/job-high-tech-qa/'],
    'mgmt': ['https://www.nisha.co.il/job_cat/seniors/'],
}


def search_nisha(role, time_filter='20h'):
    """?s= is WordPress' generic site search and it answered "QA Manager" with
    an economist, an accountant and a biochemistry research assistant — nothing
    it returned had ever survived the title gates. Nisha's job content lives in
    curated category pages instead; /positions/qa-team-leader/ alone carries six
    matches (measured 19/08/2026)."""
    role_lower = role.lower()
    key = 'qa' if any(k in role_lower for k in
                      ['qa', 'quality', 'test', 'sqa', 'qc']) else 'mgmt'
    merged, seen_urls = [], set()
    for url in _NISHA_ROLE_URLS[key]:
        for j in pw_scrape(
                url=url, source='Nisha', base_url='https://www.nisha.co.il',
                selectors=['article.type-job', '.job_listings li',
                           '[class*="job"]', 'article'],
                title_sel='h2 a, h3 a, [class*="title"] a, .job-title a, h2, h3',
                link_sel='a[href*="nisha.co.il"]',
                date_sel='time, [class*="date"]',
                wait_sel='a'):
            if j.get('url') and j['url'] not in seen_urls:
                seen_urls.add(j['url'])
                merged.append(j)
    return merged[:50]


# ── Jobmaster ─────────────────────────────────────────────────────────────────
def search_jobmaster(role, time_filter='20h'):
    url = f'https://www.jobmaster.co.il/jobs/?q={quote(role)}'
    return pw_scrape(
        url=url, source='Jobmaster', base_url='https://www.jobmaster.co.il',
        selectors=['.job-listing', '[class*="job-item"]', '.job_row', 'li.job'],
        title_sel='h2, h3, h4, [class*="title"]',
        link_sel='a',
        wait_sel='[class*="job"]',
    )


# ── Indeed Israel ─────────────────────────────────────────────────────────────
def search_indeed(role, time_filter='20h'):
    fromage = {'20h': '1', '36h': '2', '72h': '3', 'week': '7', 'month': '30'}.get(time_filter, '1')
    url = f'https://il.indeed.com/jobs?q={quote(role)}&l=Israel&fromage={fromage}&sort=date'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        jobs = []
        for card in soup.select('[class*="job_seen_beacon"], .slider_item, [data-jk]'):
            title_el   = card.select_one('[class*="jobTitle"] a, h2 a')
            company_el = card.select_one('[data-testid="company-name"], .companyName')
            loc_el     = card.select_one('[data-testid="text-location"], .companyLocation')
            date_el    = card.select_one('[data-testid="myJobsStateDate"], .date')
            link_el    = card.select_one('a[href*="/rc/clk"], a[id*="job_"]')
            if not title_el: continue
            href = link_el.get('href','') if link_el else ''
            if href and not href.startswith('http'):
                href = 'https://il.indeed.com' + href
            jobs.append({
                'title':    title_el.get_text(strip=True)[:120],
                'company':  company_el.get_text(strip=True) if company_el else '',
                'date':     date_el.get_text(strip=True) if date_el else '',
                'url':      href,
                'source':   'Indeed',
                'location': loc_el.get_text(strip=True) if loc_el else 'Israel',
            })
        if jobs: return jobs[:50]
        print('  [Indeed] page parsed but no job cards matched')
        return []
    except requests.HTTPError as e:
        # Indeed fronts il.indeed.com with Cloudflare and answers 403 + CAPTCHA to
        # anything scripted. Headless Chromium is blocked too and takes ~8 minutes
        # to find that out, so there is no fallback worth attempting.
        print(f'  [Indeed] blocked: {e}')
        return []
    except Exception as e:
        print(f'  [Indeed] error: {type(e).__name__}: {e}')
        return []


# ── Malam Team ────────────────────────────────────────────────────────────────
def search_malamteam(role, time_filter='20h'):
    if not PLAYWRIGHT_OK:
        return []
    url = 'https://career.malamteam.com/%D7%A8%D7%A9%D7%99%D7%9E%D7%AA-%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/'
    try:
        html = pw_get_html(url, wait_selector='div.job-item-container', wait_ms=3000)
    except Exception as e:
        print(f'  [MalamTeam] Playwright error: {e}')
        return []
    soup = BeautifulSoup(html, 'html.parser')
    keywords = [w.lower() for w in role.split() if len(w) > 2]
    jobs = []
    for card in soup.select('div.job-item-container'):
        top = card.select_one('.job-item-top')
        meta = card.select_one('.job-meta')
        link = card.select_one('a[href*="malamteam"]')
        if not top or not link:
            continue
        meta_text = meta.get_text(strip=True) if meta else ''
        title = top.get_text(strip=True).replace(meta_text, '').strip()
        if len(title) < 4:
            continue
        if not any(kw in title.lower() for kw in keywords):
            continue
        jobs.append({
            'title': title[:120],
            'company': 'Malam Team',
            'date': '',
            'url': link.get('href', ''),
            'source': 'Malam Team',
            'location': 'Israel',
        })
    seen, unique = set(), []
    for j in jobs:
        if j['url'] not in seen:
            seen.add(j['url'])
            unique.append(j)
    return unique[:50]


# ── Maof ──────────────────────────────────────────────────────────────────────
_MAOF_QA_KEYWORDS = ['qa', 'בדיקות', 'איכות', 'אוטומציה', 'test', 'quality']

def search_maof(role, time_filter='20h'):
    if not PLAYWRIGHT_OK:
        return []
    base = 'https://www.maof-hr.co.il'
    try:
        html = pw_get_html(f'{base}/%d7%9e%d7%a9%d7%a8%d7%95%d7%aa/', wait_ms=5000)
    except Exception as e:
        print(f'  [Maof] Playwright error: {e}')
        return []
    soup = BeautifulSoup(html, 'html.parser')
    # Build filter words from role + known QA Hebrew terms
    role_lower = role.lower()
    filter_words = [w.lower() for w in role.split() if len(w) > 2]
    if any(k in role_lower for k in ['qa', 'quality', 'test', 'בדיקות', 'איכות']):
        filter_words = _MAOF_QA_KEYWORDS
    jobs, seen = [], set()
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if '/job/' not in href:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        url = href if href.startswith('http') else base + href
        if url in seen:
            continue
        title_l = title.lower()
        if filter_words and not any(kw in title_l for kw in filter_words):
            continue
        seen.add(url)
        jobs.append({
            'title': title[:120], 'company': 'מעוף', 'date': '',
            'url': url, 'source': 'Maof', 'location': 'Israel',
        })
    return jobs[:50]


# ── Sela ──────────────────────────────────────────────────────────────────────
def search_sela(role, time_filter='20h'):
    if not PLAYWRIGHT_OK:
        return []
    base = 'https://selacloud.com'
    try:
        html = pw_get_html(f'{base}/careers', wait_ms=5000)
    except Exception as e:
        print(f'  [Sela] Playwright error: {e}')
        return []
    soup = BeautifulSoup(html, 'html.parser')
    keywords = [w.lower() for w in role.split() if len(w) > 2]
    jobs, seen = [], set()
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if '/career/' not in href:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 4:
            continue
        url = href if href.startswith('http') else base + href
        if url in seen:
            continue
        if keywords and not any(kw in title.lower() for kw in keywords):
            continue
        seen.add(url)
        jobs.append({
            'title': title[:120], 'company': 'Sela', 'date': '',
            'url': url, 'source': 'Sela', 'location': 'Israel',
        })
    return jobs[:50]


# ── One1 ──────────────────────────────────────────────────────────────────────
_ONE1_CATEGORY_IDS = {
    'qa': 258, 'test': 258, 'automation': 258, 'quality': 258,
    'project': 12, 'program': 12, 'manager': 258,
    'devops': 261, 'cloud': 261, 'cyber': 260, 'sap': 259,
}

def search_one1(role, time_filter='20h'):
    if not CURL_CFFI_OK:
        return []
    r = role.lower()
    cat_id = 258  # default: Testing & Automation
    for key, cid in _ONE1_CATEGORY_IDS.items():
        if key in r:
            cat_id = cid
            break
    base = 'https://www.one1.co.il'
    try:
        post_data = (
            f'action=oneglobal_search_job_ajax&catid={cat_id}'
            f'&searchtype=catsearch&career_page_link={quote(base + "/careers/")}'
        )
        r_resp = cf_requests.post(
            f'{base}/wp-admin/admin-ajax.php?lang=he',
            data=post_data,
            impersonate='chrome124', timeout=15,
            headers={
                'Referer': f'{base}/careers/',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
        )
        html = r_resp.json().get('html', '')
        soup = BeautifulSoup(html, 'html.parser')
        jobs, seen = [], set()
        for item in soup.find_all('div', class_='accordion_item'):
            job_id = item.get('data-id', '')
            title_el = item.find('span', class_='job_title')
            if not job_id or not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 4:
                continue
            url = f'{base}/?p={job_id}'
            if url in seen:
                continue
            seen.add(url)
            jobs.append({
                'title': title[:120], 'company': 'One1', 'date': '',
                'url': url, 'source': 'One1', 'location': 'Israel',
            })
        return jobs[:50]
    except Exception as e:
        print(f'  [One1] error: {e}')
        return []


# ── Comeet company registry (Wayback Machine CDX export + known Israeli cos) ──
COMEET_COMPANIES = {
    '10_marketing':'56.00A','365scores':'B3.006','44ventures':'18.001',
    '4dco':'B4.009','4Manalytics':'B6.00F','500tech':'47.000','6over6':'73.00A',
    '888jobs':'E2.001','ABInBev':'54.004','abra':'12.003','abra_rnd':'15.007',
    'accedo':'95.00B','accessfintech':'76.00A','accessibe':'D5.00B',
    'acrocharge':'36.001','acropolis':'37.008','ACS':'14.000',
    'activefence':'D5.005','aeronautics':'72.002','affogata':'37.005',
    'Afimilk':'B3.00A','agmatix':'16.003','agora':'08.007','AGT':'82.004',
    'ai21':'E6.001','aidoc':'B4.007','aiola':'77.002','airwayz':'79.009',
    'akeyless':'27.006','aleph-farms':'97.00F','algosec':'71.006',
    'allot':'C4.009','altair-semi':'88.003','amimon':'50.00C','anagog':'C6.00C',
    'anchorfintech':'87.00D','anecdotes':'F9.00B','anyclip':'91.00D',
    'anyword':'30.00B','appdome':'E6.005','applicaster':'82.000',
    'appnext':'42.003','appsforce':'09.00C','appstock':'DA.003',
    'aquant':'16.007','aquasec':'91.001','armis':'94.00C','artlist':'85.003',
    'atera':'63.00B','audiocodes':'85.004','augmedics':'26.00C',
    'authomize':'57.00E','autobrains':'57.004','autodesk':'70.00D',
    'avanan':'43.00B','avo':'C5.00B','balance':'67.008','beamr':'A9.00B',
    'biocatch':'03.00E','bizzabo':'A5.000','blinkops':'C7.004',
    'blockaid':'69.00B','bluesnap':'73.002','bluewhite':'D5.00D',
    'bond':'D2.00B','brandshield':'13.002','brightdata':'88.007',
    'britannica':'95.00D','buildots':'36.004','buyme':'B2.008',
    'caesarstone':'25.000','candivore':'48.00F','cardinalops':'66.005',
    'catonetworks':'D2.00C','Cellebrite':'C3.00F','centrical':'C1.00A',
    'ceva':'76.005','chainreaction':'A6.00D','chargeafter':'C5.004',
    'checkmarx':'C0.008','cheq':'65.005','civalue':'83.00D',
    'Claroty':'F2.004','classiq':'F7.008','clinch':'42.007',
    'codevalue':'81.009','cognyte':'F2.009','coinmama':'92.00E',
    'comeet':'30.005','comm-it':'76.008','spark-hire':'30.005','coralogix':'06.004','coro':'08.00A',
    'crazylabs':'32.00E','ctera':'A0.003','cybereason':'48.005',
    'cyberark':'79.005','datagen':'1A.00F','deloitte-il':'56.008',
    'deploy':'A0.00A','detectrx':'F7.00E','ditto':'98.00A',
    'doctorlink':'E9.005','doit-intl':'BA.005','drs':'C5.009',
    'duda':'79.001','dynamic-yield':'37.001','elasticpath':'93.001',
    'elbit-systems':'86.00E','elephants':'14.004','elmo':'E6.009',
    'emerse':'D3.003','employer-il':'D8.001','empoweredlearn':'79.00E',
    'endace':'E4.003','envoy':'30.002','epsagon':'47.007',
    'era':'A3.003','ermetic':'12.00F','escalate':'26.00A',
    'etoro':'88.00C','eviation':'B2.001','exlibrisgroup':'81.002',
    'explorium':'E3.001','f2pool':'D7.001','fairfly':'86.002',
    'fenestrate':'76.00F','finastra':'46.003','firebolt':'47.001',
    'fiverr':'68.003','flashpoint':'43.003','flox':'C7.002',
    'foresight-auto':'38.00C','fortinet':'59.002','genie':'50.007',
    'genie-energy':'24.001','gett':'48.00B','glimpse':'67.003',
    'globant':'90.009','glowtouch':'99.001','goldbugs':'26.009',
    'granulate':'48.008','guardknox':'26.00B','guesty':'02.00E',
    'gwi':'30.00E','harman':'25.009','healbe':'05.00B','hexadite':'13.005',
    'highhome':'B5.006','hippo':'A3.004','hiro':'91.00F','homepoint':'9E.003',
    'hoopo':'D5.00E','hoory':'D9.004','howden':'24.007','hp-il':'D4.009',
    'hyp':'E7.003','hypertouch':'A4.001','ibm-il':'A4.006',
    'iguazio':'57.003','iltechworks':'58.003','imagine-communications':'90.002',
    'immigram':'47.00D','impel':'72.001','imperva':'64.003',
    'indoek':'01.001','inex':'C1.004','infinidat':'49.003',
    'infosys-bpm':'64.00E','inneractive':'06.003','innplay':'43.001',
    'insightcyber':'55.009','instacart-il':'3A.003','intel-il':'50.003',
    'intelligent-med':'A1.006','intercom-il':'97.001','intrinsec':'A6.001',
    'intuit-il':'22.001','invision':'50.002','ion-group':'34.003',
    'ironnet':'A6.009','israel-innovation':'14.009','isracard':'10.001',
    'iterait':'1A.001','j5-create':'F2.005','jayride':'76.003',
    'jit':'E3.006','jobwise':'E5.004','juicemobile':'A7.005',
    'jumpconsulting':'62.005','jumpsec':'63.004','jumptechnologies':'E4.001',
    'k8s':'3A.00C','kaltura':'C5.005','karma':'40.002','karmacheck':'BA.003',
    'khr':'B4.004','klarna-il':'C0.003','kms-lighthouse':'64.002',
    'kora':'35.00C','kryon':'53.009','l3harris':'87.001','lamda-guard':'A9.007',
    'landsmann':'E8.00C','lasso':'D0.004','latana':'77.00C',
    'legalpad':'D5.007','lendbuzz':'E9.001','lifebit':'35.003',
    'lightricks':'C5.006','linnovate':'62.003','luminoah':'43.007',
    'luyten3d':'14.008','lyrid':'B4.006','maker-technologies':'76.002',
    'mango':'D0.001','marketaxess':'90.001','markets-il':'46.001',
    'matomy':'A3.001','mayarobotics':'35.001','mcafee-il':'27.004',
    'medazur':'DA.00B','medici':'A0.007','medis':'34.001',
    'medigus':'97.008','mend':'77.009','mercury':'60.009',
    'merantix':'82.00B','mesh':'46.009','metric-system':'95.007',
    'millet':'13.008','mindspace':'C2.001','mirror-computing':'64.005',
    'mirriad':'33.005','mixpanel-il':'B2.007','mobi':'38.008',
    'mobilion':'D1.00C','moneta':'C4.002','moon-active':'43.00B',
    'moxian':'35.008','mparticle-il':'72.007','mplicity':'F5.00C',
    'mvi':'F9.00A','mycorona':'25.007','myheritage':'47.005',
    'mystays':'9A.001','napier-hospital':'A3.00D','narvar':'F6.001',
    'nasscom':'2A.001','national-instruments':'63.003','nayax':'24.003',
    'ndvr':'37.003','nectar-com':'07.008','nessun-dorma':'EA.007',
    'netscout':'93.004','netsol':'53.002','network-3':'12.001',
    'nexar':'87.006','nice-actimize':'99.002','nilus':'A5.002',
    'nimax':'F7.00A','northbit':'36.008','nostra':'C4.001',
    'notch':'C4.003','notifia':'3A.001','novatek':'4B.001',
    'nuvoton':'DA.001','objectify':'B0.003','oden':'09.002',
    'oden-technologies':'09.002','oktopost':'56.001','omni':'3A.004',
    'omt-il':'64.001','on':'C9.001','online-il':'88.005',
    'ontelo':'63.001','oqton':'A0.009','optibus':'A2.001',
    'orb-intelligence':'12.002','orbs':'68.001','origami-energy':'EA.001',
    'os':'F5.003','osem-nestlé':'E3.00E','osher':'34.007',
    'otorio':'12.005','otter-pr':'04.002','outrider':'78.00F',
    'owkin':'B1.003','oxefit':'AA.001','oxylabs':'3E.00A',
    'pagaya':'65.003','palantir-il':'A6.007','panaya':'33.002',
    'parasut':'01.00E','parseq-lab':'18.00B','patchwork':'E7.001',
    'pathlock':'17.006','pax8':'83.001','payoneer':'A4.004',
    'payop':'37.00A','pentera':'49.001','percepto':'41.001',
    'perimeterx':'57.001','perfectmile':'93.006','personetics':'48.00A',
    'pharmbio':'61.001','pilotfisherlab':'1A.005','pixis':'89.001',
    'planet':'C1.001','plantt':'F5.001','platforms':'C5.001',
    'playwing':'E5.006','plexure':'48.001','point-security':'A3.007',
    'polar-analytics':'08.00D','polaris':'54.001','pomelotech':'53.001',
    'pontera':'12.00B','poseidon-il':'44.001','postindustria':'73.001',
    'powerschool':'92.003','profero':'09.001','prometheustech':'3A.002',
    'propel':'48.00C','protego':'54.00D','proteus':'B4.001',
    'provider':'C0.001','ps-global':'54.008','pyur':'18.003',
    'qsee':'35.00B','quadcode':'88.009','qualitest':'54.003',
    'quantum':'36.001','quartix':'81.001','questex':'3A.006',
    'quotient':'93.001','radvision':'48.006','rapid7-il':'84.001',
    'rdvision':'B5.003','reco':'05.00C','recombinetics':'B5.001',
    'reef':'65.007','reicubig':'48.002','remobi':'97.00A',
    'replicated':'17.007','researchgate':'16.009','resonance':'3A.00B',
    'revuze':'81.005','rightnow':'A2.003','rivus':'1A.006',
    'roper-technologies':'70.009','rubrik-il':'C7.005','runai':'28.004',
    'saas-group':'4A.003','sasa-il':'61.002','savvycal':'1A.003',
    'sbs-israel':'16.001','schematics':'43.005','schola':'1A.007',
    'scytale':'53.00A','sealsq':'16.007','secdo':'55.001',
    'sector3':'39.001','securithings':'62.001','seemplicity':'F7.006',
    'seismic-il':'72.009','semarchy':'F6.005','semrush-il':'E8.009',
    'sensitech':'A5.005','sention':'D7.007','sensorix':'3A.008',
    'sentinelone-il':'61.009','seraphic':'1A.00A','setapp':'A6.003',
    'sevensense':'43.006','shl-medical':'63.009','shopic':'60.001',
    'siemplify':'79.00F','signifai':'39.00A','siliconmindtech':'A0.005',
    'simetric':'03.009','simplex':'D0.003','sixth-street':'60.003',
    'skims':'92.001','sky-mavis':'9E.001','slang':'E8.003',
    'soax':'A0.00A','socure':'B2.006','solaredge':'A3.009',
    'solarflare':'D3.00B','solidus':'05.005','somo':'C9.006',
    'sponga':'44.004','squaredance':'5A.001','stackpulse':'35.009',
    'stagil':'35.005','startapp':'69.001','stealth-mode':'36.009',
    'stellarchain':'1A.009','storecove':'1A.008','storewale':'1A.00B',
    'styler':'D7.003','stylitics':'1A.004','syte':'E5.001',
    'taboola':'23.001','talkspace':'19.001','tata-il':'42.001',
    'tcg':'42.006','tdp':'E5.005','teamviewer-il':'A0.004',
    'teridion':'D6.001','test-io':'42.004','testsigma':'1A.00D',
    'tgtg':'55.00E','thales-il':'6A.001','theator':'28.003',
    'theinformation':'62.009','theta-lake':'67.00B','thinQ':'60.005',
    'thoughtspot-il':'8E.001','tickr':'43.004','tinyml':'35.006',
    'tipalti':'88.001','tipico':'68.001','titanium-il':'3A.009',
    'tokenist':'1A.002','tomia':'A1.001','topaz-labs':'E6.006',
    'torchmd':'54.005','touchstream':'99.005','tracelink':'82.001',
    'trakncare':'F7.005','transcend':'C5.002','transformedia':'67.00A',
    'transifex':'97.009','travolution':'B2.005','trax':'25.003',
    'trendmicro-il':'74.001','trinetx':'A7.001','tripactions-il':'49.005',
    'truecoach':'56.005','truora':'44.003','ttec':'3A.005',
    'tufin':'71.001','turboboost':'A7.004','two-hat':'97.005',
    'unico':'47.00C','unitronics':'57.006','unsupervised':'C1.005',
    'upsolver':'A4.007','upwave':'38.001','uscreen':'A0.00C',
    'useriq':'02.004','userline':'35.007','vayyar':'C2.007',
    'verbit':'F8.001','viber-il':'07.001','vidyo':'73.005',
    'vigtech':'E0.003','vizard':'75.007','vizbee':'62.007',
    'volterra':'35.00A','voyantis':'D7.005','vroom-il':'B3.001',
    'waabi':'E4.007','walkme':'C3.005','wallix':'52.001',
    'wasabi':'D3.005','watchout':'79.007','waterfall-security':'86.001',
    'weka':'61.007','wellbeing':'36.003','westat':'D8.005',
    'wevo':'25.008','whoknows':'B1.009','wideo':'14.005',
    'wiliot':'43.009','windward':'55.008','wiz':'A7.003',
    'wiz-il':'A7.003','wix':'10.006','wonga-il':'36.006',
    'xm-cyber':'B4.005','ycd-multimedia':'A1.004','yembo':'99.007',
    'yigdal':'40.001','yokneam':'31.001','yotpo':'E5.003',
    'ypsilon':'D6.003','zeek':'64.00A','zendesk-il':'34.009',
    'zerto':'68.004','zigu':'5A.003','zimperium-il':'D5.003',
    'zoomin':'44.005','zoominfo-il':'79.003','zooz':'71.004',
    'zscaler-il':'99.003','zuva':'47.008',
}


# ── Comeet (direct scrape via curl_cffi — bypasses Incapsula) ─────────────────
_COMEET_CACHE = {}   # {(frozenset(role_specific), time_filter): (ts, jobs)}

def search_comeet(role, time_filter='20h'):
    """Scrape Israeli Comeet company boards directly using curl_cffi TLS impersonation."""
    try:
        from curl_cffi import requests as cf_req
    except ImportError:
        print('  [Comeet] curl_cffi not installed — run: pip install curl_cffi')
        return []

    import re, json, concurrent.futures
    from datetime import datetime, timezone, timedelta

    TIME_DELTAS = {'20h': timedelta(hours=20), '36h': timedelta(hours=36), '72h': timedelta(hours=72), 'week': timedelta(days=7), 'month': timedelta(days=30)}
    cutoff = datetime.now(timezone.utc) - TIME_DELTAS.get(time_filter, timedelta(hours=20))

    # Build a smarter role matcher: strip generic words so "PMO Manager" only
    # matches jobs that contain "pmo", not any job with "manager".
    _GENERIC = {'manager','director','head','lead','senior','sr','junior','jr',
                'of','the','and','at','in','for','a','an','r&d'}
    role_words_all = set(role.lower().split())
    role_specific  = role_words_all - _GENERIC
    if not role_specific:          # e.g. role = "Manager" → fall back to all words
        role_specific = role_words_all

    cache_key = (frozenset(role_specific), time_filter)
    cached = _COMEET_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        print(f'  [Comeet] cached result ({len(cached[1])} jobs)')
        return cached[1]

    CF_HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    def _fetch_company(slug_code):
        slug, code = slug_code
        url = f'https://www.comeet.com/jobs/{slug}/{code}'
        try:
            r = cf_req.get(url, impersonate='chrome124', headers=CF_HEADERS, timeout=10)
            if r.status_code != 200:
                return []
            m = re.search(r'COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\])\s*;', r.text, re.DOTALL)
            if not m:
                return []
            positions = json.loads(m.group(1))
            jobs = []
            for p in positions:
                loc = p.get('location', {})
                if isinstance(loc, dict) and loc.get('country', '') != 'IL':
                    continue
                title = p.get('name', '').strip()
                if not title:
                    continue
                title_lower = title.lower()
                # Require at least one SPECIFIC (non-generic) role word in the title
                if not any(w in title_lower for w in role_specific):
                    continue
                # Time filter — use time_updated as proxy for posting date
                t_upd = p.get('time_updated', '')
                if t_upd:
                    try:
                        upd = datetime.fromisoformat(t_upd.replace('Z', '+00:00'))
                        if upd < cutoff:
                            continue
                    except Exception:
                        pass
                url_job = (p.get('url_comeet_hosted_page') or
                           p.get('url_recruit_hosted_page') or
                           p.get('url_active_page') or '')
                company_name = (p.get('company_name') or slug.replace('-', ' ').title())
                city = loc.get('city', 'Israel') if isinstance(loc, dict) else 'Israel'

                recruiter_name = ''
                recruiter_url  = ''
                for rkey in ('recruiter', 'contact', 'hr_contact', 'hiring_manager'):
                    rdata = p.get(rkey)
                    if isinstance(rdata, dict):
                        fn = rdata.get('first_name', '')
                        ln = rdata.get('last_name', '')
                        recruiter_name = (rdata.get('name') or rdata.get('full_name') or
                                          f'{fn} {ln}').strip()
                        recruiter_url  = (rdata.get('linkedin_url') or rdata.get('url') or
                                          rdata.get('profile_url') or '')
                        if recruiter_name:
                            break
                    elif isinstance(rdata, str) and rdata:
                        recruiter_name = rdata
                        break

                jobs.append({
                    'title':          title[:120],
                    'company':        company_name,
                    'date':           t_upd[:10],
                    'url':            url_job,
                    'source':         'Comeet',
                    'location':       city,
                    'recruiter_name': recruiter_name,
                    'recruiter_url':  recruiter_url,
                })
            return jobs
        except Exception:
            return []

    jobs = []
    seen = set()
    items = list(COMEET_COMPANIES.items())
    deadline = time.time() + 45   # hard wall-clock limit

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=15)
    try:
        futures = {ex.submit(_fetch_company, item): item for item in items}
        for future in concurrent.futures.as_completed(futures, timeout=47):
            if time.time() > deadline:
                break
            try:
                for job in future.result():
                    if job['url'] and job['url'] not in seen:
                        seen.add(job['url'])
                        jobs.append(job)
            except Exception:
                pass
    except concurrent.futures.TimeoutError:
        pass
    finally:
        ex.shutdown(wait=False)   # don't block — let background threads die on their own

    print(f'  [Comeet] direct scrape -> {len(jobs)} jobs across {len(items)} boards')
    result = jobs[:50]
    _COMEET_CACHE[cache_key] = (time.time(), result)
    return result


# ── Google Jobs ───────────────────────────────────────────────────────────────
def search_google_jobs(role, time_filter='20h'):
    if not PLAYWRIGHT_OK:
        return []
    chips = {'20h': 'today', 'week': 'week', 'month': 'month'}
    url = f'https://www.google.com/search?q={quote(role + " Israel jobs")}&ibp=htl;jobs'
    try:
        html = pw_get_html(url, wait_selector='[data-ved]', wait_ms=4000)
        soup = BeautifulSoup(html, 'html.parser')
        jobs = []
        for card in soup.select('[class*="pE8vnd"], [jscontroller], [data-hveid]'):
            title_el   = card.select_one('[class*="BjJfJf"], [class*="sH3zFd"], h3')
            company_el = card.select_one('[class*="vNEEBe"], [class*="YhE3Ld"]')
            loc_el     = card.select_one('[class*="Qk80Jf"]')
            link_el    = card.select_one('a[href]')
            if not title_el or not link_el: continue
            href = link_el.get('href', '')
            if not href.startswith('http'): continue
            jobs.append({
                'title':    title_el.get_text(strip=True)[:120],
                'company':  company_el.get_text(strip=True) if company_el else '',
                'date':     '',
                'url':      href,
                'source':   'Google Jobs',
                'location': loc_el.get_text(strip=True) if loc_el else 'Israel',
            })
        return jobs[:50]
    except Exception as e:
        print(f'  [Google Jobs] error: {e}')
        return []


# ── Source registry ───────────────────────────────────────────────────────────
SCRAPERS = {
    'linkedin':    search_linkedin,
    'indeed':      search_indeed,
    'alljobs':     search_alljobs,
    'drushim':     search_drushim,
    'gotfriends':  search_gotfriends,
    'experis':     search_experis,
    'dialog':      search_dialog,
    'sqlink':      search_sqlink,
    'nisha':       search_nisha,
    'malamteam':   search_malamteam,
    'maof':        search_maof,
    'sela':        search_sela,
    'one1':        search_one1,
    'comeet':      search_comeet,
    'googlejobs':  search_google_jobs,
    'jobmaster':   search_jobmaster,
    'secretjobs':  search_secretjobs,
}


# ── Scheduled WhatsApp notifications ─────────────────────────────────────────
SCHEDULED_ROLES = [
    'QA Manager', 'QA Director', 'Head of QA', 'QA Team Leader',
    'Release Manager', 'Program Manager', 'Project Manager',
    'Professional Services Manager',
    # Same target as Release Manager and answered with the same CV; the two are
    # one job under two names depending on the company.
    'Delivery Manager',
]

# How far back each source is asked to look. The scan runs hourly, so this is
# almost entirely overlap that seen_jobs throws away — the point is the outage
# case. At 20h a run of failures longer than that lost those postings for good,
# with no catch-up anywhere; 36h roughly doubles the tolerance. It costs nothing
# in notifications, and little in time: every source caps its own result list,
# so a wider window mostly returns things already seen.
_SCAN_WINDOW = '36h'

# Announce the start of a scan in Telegram. Doubles the daily message count to
# 32, which is why it is a switch: set False and the scan goes back to
# reporting only its results.
_SCAN_START_PING = True

# Whole-scan budget. The workflow allows 25 minutes; leave room for setup,
# Chromium install and the commit/push that follows.
_SCAN_BUDGET_SEC = 900

_SOURCE_LABELS = {
    'linkedin': 'LinkedIn', 'indeed': 'Indeed', 'alljobs': 'AllJobs',
    'drushim': 'Drushim', 'comeet': 'Comeet', 'gotfriends': 'GotFriends',
    'experis': 'Experis', 'dialog': 'Dialog', 'sqlink': 'SQLink',
    'nisha': 'Nisha', 'malamteam': 'MalamTeam', 'maof': 'Maof', 'sela': 'Sela',
    'one1': 'One1', 'googlejobs': 'GoogleJobs', 'jobmaster': 'Jobmaster',
    'secretjobs': 'SecretJobs',
}

# Known SaaS companies (Israeli + global names common in the Israeli market).
# Static and necessarily incomplete — no live company-classification source
# (e.g. Crunchbase) is wired in, so this only flags companies recognized by
# name. Newer or smaller SaaS companies won't be tagged; add names as they
# come up.
_SAAS_COMPANIES = {
    'monday.com', 'monday', 'wix', 'fiverr', 'walkme', 'riskified',
    'similarweb', 'yotpo', 'gong', 'hibob', 'papaya global', 'melio',
    'verbit', 'snyk', 'jfrog', 'wiz', 'rapyd', 'lightricks', 'payoneer',
    'kaltura', 'sentinelone', 'cyberark', 'armis', 'axonius',
    'cato networks', 'aqua security', 'tipalti', 'fundbox', 'forter',
    'namogoo', 'optimove', 'personetics', 'sisense', 'thetaray', 'anodot',
    'explorium', 'panorays', 'noname security', 'torq', 'global-e',
    'appsflyer', 'ironsource', 'taboola', 'outbrain', 'zoominfo',
    'salto', 'firebolt', 'redis', 'fireblocks', 'dynamic yield', 'bringg',
    'datorama', 'nayax', 'innovid', 'sapiens', 'priority software',
    'panaya', 'syte', 'cybereason', 'guardicore', 'perimeter 81',
    'perimeter81', 'hiredscore', 'zesty', 'spot.io', 'firefly',
    'salesforce', 'hubspot', 'zendesk', 'atlassian', 'servicenow',
    'workday', 'adobe', 'slack', 'shopify', 'datadog', 'snowflake',
    'mongodb', 'twilio', 'okta', 'zoom', 'docusign', 'dropbox', 'box',
    'gitlab', 'github', 'circleci', 'splunk', 'new relic', 'pagerduty',
    'asana', 'notion', 'miro', 'figma', 'canva', 'coupa', 'freshworks',
    'genesys', 'five9', 'ringcentral', 'netsuite', 'intuit', 'nice',
    'amdocs', 'checkmarx', 'cyera', 'orca security', 'wing security',
    'island', 'gomomento', 'akeyless',
}


def _is_saas_company(company: str) -> bool:
    c = (company or '').strip().lower()
    if not c:
        return False
    return any(name in c for name in _SAAS_COMPANIES)


# LinkedIn's job detail page (fetched anyway for recruiter info, see
# _linkedin_fetch_recruiter) carries the full description — for companies not
# in the static list, this catches self-described SaaS businesses directly.
_SAAS_DESC_RE = re.compile(
    r'\bsaas\b|software[\s-]as[\s-]a[\s-]service|cloud-based\s+platform'
    r'|subscription-based\s+(platform|software)|b2b\s+saas|multi-tenant\s+saas',
    re.IGNORECASE,
)


def _is_saas(job) -> bool:
    if _is_saas_company(job.get('company')):
        return True
    return bool(_SAAS_DESC_RE.search(job.get('li_description') or ''))


# Every board answers a query with fuzzy matches — searching "QA Team Leader" on
# LinkedIn returns "VLSI DFT Team Leader" and "Data Engineering Team Lead". This
# gate runs on all sources and demands the title actually be about QA, release,
# program/project or professional-services management, which is what
# SCHEDULED_ROLES asks for.
_RELEVANT_TITLE_RE = re.compile(
    # 'automation' is deliberately absent. On its own it qualified titles like
    # "Head of Automation" and "Automation Team Leader" — automation-owning
    # roles, which Shaul is not looking for. A genuine QA post always carries
    # qa/quality/test as well, so "QA Automation Manager" still passes on those.
    r'\b(qa|qc|sqa|quality|test|tester|testing|release|releases|pmo'
    r'|program\s+manager|programme\s+manager|program\s+management'
    r'|project\s+manager|project\s+management'
    # Deliberately the two-word forms, not a bare "delivery": on the Israeli
    # boards that word alone is mostly couriers and food delivery.
    r'|delivery\s+manager|delivery\s+management|delivery\s+lead'
    r'|professional\s+services)\b'
    # Israeli boards write these roles in transliteration as often as in
    # Hebrew. "דליברי" is the software sense; food delivery is "משלוחים",
    # which stays out.
    r'|בדיקות|בודק|איכות|שחרור|שחרורים|תוכנית|תוכניות|פרויקט|פרויקטים'
    r'|דליברי|דליוורי|ריליס|ריליז|שירותים\s+מקצועיים',
    re.IGNORECASE,
)

# 'indeed' is deliberately absent: il.indeed.com sits behind Cloudflare and
# answers 403 + CAPTCHA to every scripted request. It stays in SCRAPERS for
# manual searches, but on a schedule it only ever contributed latency.
# 'malamteam' was registered in SCRAPERS but never scheduled, so it had never
# run. Audited 19/08/2026 it returns 39 rows and 6 survive every filter — more
# than gotfriends, sqlink or nisha. The other five unscheduled scrapers were
# audited at the same time and are dead: jobmaster, maof, sela and googlejobs
# return no rows at all, one1 returns two and neither passes.
SCHEDULED_SOURCES = [
    'linkedin', 'alljobs', 'drushim',
    'comeet', 'gotfriends', 'experis', 'dialog', 'sqlink', 'nisha',
    'malamteam', 'secretjobs',
]

# For scheduled notifications — fast sources only (no Playwright serialization)
SCHEDULED_SOURCES_FAST = ['linkedin', 'comeet', 'experis']

# Raised from 5000. At ~60 new urls a day the old cap was reached every couple
# of days, and every prune produced a wave of duplicate notifications. One url
# is ~110 bytes, so even a full file is a few megabytes, written one url per
# sorted line so git still merges it cleanly.
_SEEN_JOBS_CAP = 40000

_seen_jobs_memory: set = set()
_LOCAL_SEEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seen_jobs.json')
_SEEN_JOBS_FILE = '/data/seen_jobs.json' if os.path.isdir('/data') else _LOCAL_SEEN


def _load_seen_jobs():
    global _seen_jobs_memory
    if _SEEN_JOBS_FILE:
        try:
            with open(_SEEN_JOBS_FILE) as f:
                _seen_jobs_memory = set(json.load(f).get('urls', []))
        except Exception:
            pass
    return _seen_jobs_memory


def _save_seen_jobs(urls: set):
    global _seen_jobs_memory
    _seen_jobs_memory = urls
    if _SEEN_JOBS_FILE:
        try:
            # One URL per line (sorted) rather than a single-line blob: local
            # and cloud runs both write this file, and a one-line JSON diffs
            # as a single all-or-nothing hunk, so any two concurrent runs
            # always conflict. Spread across sorted lines, most concurrent
            # additions land at different lines and merge on their own; the
            # merge=union rule in .gitattributes covers what's left.
            with open(_SEEN_JOBS_FILE, 'w') as f:
                json.dump({'urls': sorted(urls)}, f, indent=2)
        except Exception as e:
            print(f'  [notify] save seen_jobs failed: {e}')


# ── Job records ──────────────────────────────────────────────────────────────
# seen_jobs.json answers one question — have I reported this url — and answers
# it well, so it stays as it is. It cannot answer "what was that job", which is
# what a button in the Telegram message needs: press it an hour later and the
# only thing coming back is a callback id.
#
# Deliberately not stored here: how to apply. The spec assumed each record
# would carry an apply_type decided during the scan, and that turned out to be
# impossible — LinkedIn's guest endpoint hides the apply method from a
# logged-out caller (ten sampled postings, all inconclusive), and LinkedIn is
# 58% of everything collected. Working it out at apply time is also less waste:
# most of these are never pressed.
#
# JSONL, one record per line, sorted by id. Cloud and local runs both write it,
# and line-oriented is the only shape the merge=union rule in .gitattributes
# can resolve without corrupting the file — a pretty-printed JSON object would
# merge into mismatched braces.
_LOCAL_JOBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobs.jsonl')
_JOBS_FILE = '/data/jobs.jsonl' if os.path.isdir('/data') else _LOCAL_JOBS

# A posting older than this is almost certainly filled, and a button on it is
# worse than no button.
_JOBS_RETENTION_DAYS = 30


def _job_id(url: str) -> str:
    """Short stable id for a posting. Telegram caps callback_data at 64 bytes,
    so the url itself will not fit. 10 hex chars over a few tens of thousands
    of records makes a collision vanishingly unlikely."""
    return hashlib.sha1((url or '').encode('utf-8')).hexdigest()[:10]


def _load_jobs() -> dict:
    """id -> record. Later lines win, so a union merge that duplicates a record
    resolves to the newer copy instead of failing."""
    jobs = {}
    try:
        with open(_JOBS_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue          # a torn line must not lose the whole file
                if rec.get('id'):
                    jobs[rec['id']] = rec
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f'  [jobs] load failed: {e}')
    return jobs


def _save_jobs(jobs: dict):
    try:
        with open(_JOBS_FILE, 'w', encoding='utf-8') as f:
            for jid in sorted(jobs):
                f.write(json.dumps(jobs[jid], ensure_ascii=False,
                                   sort_keys=True) + '\n')
    except Exception as e:
        print(f'  [jobs] save failed: {e}')


def _record_jobs(new_jobs: list) -> list:
    """Store the jobs that were actually reported, and stamp each with its id.
    Only reported jobs: those are the ones a button can appear on, and keeping
    every scraped posting would grow the file by hundreds per scan."""
    jobs = _load_jobs()
    now = _now_il()
    stamped = 0
    for j in new_jobs:
        url = j.get('url')
        if not url:
            continue
        jid = _job_id(url)
        j['id'] = jid                          # so the caller can build buttons
        if jid in jobs:
            jobs[jid]['last_seen'] = now.isoformat(timespec='seconds')
            continue
        jobs[jid] = {
            'id':             jid,
            'title':          (j.get('title') or '').strip(),
            'company':        (j.get('company') or '').strip(),
            'source':         (j.get('source') or '').strip(),
            'url':            url,
            'posted':         j.get('date') or '',
            'location':       j.get('location') or '',
            'saas':           bool(_is_saas(j)),
            'recruiter_name': j.get('recruiter_name') or '',
            'recruiter_url':  j.get('recruiter_url') or '',
            'first_seen':     now.isoformat(timespec='seconds'),
            'last_seen':      now.isoformat(timespec='seconds'),
            'status':         'new',
        }
        stamped += 1

    cutoff = (now - timedelta(days=_JOBS_RETENTION_DAYS)).isoformat()
    # Anything acted on is kept regardless of age — that is the application
    # history, and applications.json only holds what was actually submitted.
    keep = {k: v for k, v in jobs.items()
            if v.get('status') != 'new' or v.get('first_seen', '') >= cutoff}
    dropped = len(jobs) - len(keep)
    _save_jobs(keep)
    print(f'[jobs] {stamped} recorded, {len(keep)} held'
          + (f', {dropped} aged out' if dropped else ''))
    return new_jobs


def _send_notification(message: str, parse_mode: str = 'HTML'):
    import urllib.request, json as _json
    token   = os.getenv('TELEGRAM_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat_id:
        print('  [notify] TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set — skipping')
        return
    url     = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = _json.dumps({
        'chat_id':                  chat_id,
        'text':                     message,
        'parse_mode':               parse_mode,
        'disable_web_page_preview': True,
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f'  [notify] Telegram sent (HTTP {r.status})')
    except Exception as e:
        print(f'  [notify] Telegram error: {e}')


def _esc(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


_TG_LIMIT = 4096


def _job_line(j) -> str:
    title   = _esc((j.get('title') or '').strip()) or '(ללא כותרת)'
    company = _esc((j.get('company') or '').strip())
    source  = _esc((j.get('source') or '').strip())
    # 'link' is where the reader should be sent, 'url' is the job's identity for
    # seen_jobs. They differ only for SecretJobs, whose own page is a paywall -
    # changing 'url' instead would make every one of its jobs look new again.
    url     = _esc((j.get('link') or j.get('url') or '').strip())
    tag     = '🟢 SaaS · ' if _is_saas(j) else ''
    line = f'• <a href="{url}">{title}</a>' if url else f'• {title}'
    meta = ' · '.join(x for x in (company, f'<i>{source}</i>' if source else '') if x)
    if meta:
        line += f'\n  {tag}{meta}'
    return line


def _send_sectioned(header: str, sections: list, footer: str = ''):
    """Send headed sections inline, splitting at Telegram's 4096-char limit.

    sections is [(heading, [line, ...])]. The jobs travel inside the message
    itself so they can never disagree with the count in the header — unlike a
    link to a page that is published later. When a section spills into another
    message its heading is repeated, so a split section still reads correctly.
    """
    budget = _TG_LIMIT - 300          # room for header, part marker and footer
    msgs, cur = [], ''

    def flush():
        nonlocal cur
        if cur.strip():
            msgs.append(cur)
        cur = ''

    for heading, lines in sections:
        if not lines:
            continue
        block = f'<b>{heading}</b>\n\n'
        if cur and len(cur) + len(block) > budget:
            flush()
        cur += block
        for line in lines:
            piece = line[:budget] + '\n\n'
            if len(cur) + len(piece) > budget:
                flush()
                cur = f'<b>{heading}</b> (המשך)\n\n'
            cur += piece
    flush()

    total = len(msgs) or 1
    for i, body in enumerate(msgs, 1):
        part = f' ({i}/{total})' if total > 1 else ''
        msg  = f'{header}{part}\n\n{body}'
        if i == total:
            msg += footer
        _send_notification(msg)


def _run_notify_job(status_cb=None, sources=None, always_notify=False, scope=''):
    """Scan `sources` and push anything new to Telegram.

    always_notify sends a message even when nothing new turned up — silence is
    ambiguous on a schedule (no jobs? or scraper broken?).
    scope labels the run in the message, e.g. ' בלינקדאין'.
    """
    sources = sources or SCHEDULED_SOURCES_FAST

    def _status(msg):
        print(msg, end='')
        if status_cb:
            status_cb(msg)
    _status(f'[notify] Starting — {_now_il():%Y-%m-%d %H:%M} IL — sources={",".join(sources)}\n')

    # Shaul asked for a ping when a scan starts. It doubles the daily traffic to
    # 32 messages, so it says something useful rather than just "started": which
    # sources are being asked, and when the answer is due. Flip to False to stop
    # it without touching anything else.
    if _SCAN_START_PING and not status_cb:
        _send_notification(
            f'🔄 <b>סריקה התחילה</b> — {_now_il():%H:%M}\n'
            f'{len(sources)} מקורות · {len(SCHEDULED_ROLES)} תפקידים\n'
            f'<i>התוצאות בעוד 5-8 דקות</i>'
        )

    seen  = _load_seen_jobs()
    results = []
    lock    = threading.Lock()
    # Per-source outcome, so a silent source can be reported as broken/timed-out
    # rather than looking the same as a source that simply had nothing new.
    stats = {src: {'raw': 0, 'done': 0, 'errors': []} for src in sources}

    def fetch(source, role):
        scraper = SCRAPERS.get(source)
        if not scraper:
            with lock:
                stats[source]['done'] += 1
                stats[source]['errors'].append('scraper not registered')
            return
        try:
            jobs = scraper(role, _SCAN_WINDOW)
            raw_n = len(jobs)
            _NOISY = {'experis', 'dialog', 'sqlink', 'malamteam', 'nisha', 'gotfriends', 'jobmaster'}
            if source in _NOISY:
                role_l = role.lower()
                if any(k in role_l for k in ['qa', 'quality', 'test', 'automation', 'sqa', 'qc']):
                    kws = {'qa', 'quality', 'בדיקות', 'test', 'automation', 'אוטומציה', 'איכות', 'qc', 'sqa'}
                elif any(k in role_l for k in ['project', 'program', 'pmo', 'delivery', 'release', 'scrum',
                                                'professional services', 'release']):
                    kws = {'project', 'program', 'פרויקט', 'pm', 'pmo', 'תוכנית', 'programme',
                           'delivery', 'release', 'scrum', 'agile', 'ניהול פרויקט', 'מנהל פרויקט',
                           'professional services', 'services'}
                else:
                    kws = _drushim_keywords(role)
                # Deliberately domain-based, not seniority-based: matching on bare
                # "manager"/"head of" pulled in Head of Engineering and מנהל מוצר,
                # which are senior but off-target.
                jobs = [j for j in jobs
                        if any(kw in (j.get('title', '') + ' ' + j.get('company', '')).lower()
                               for kw in kws)]
            with lock:
                stats[source]['raw'] += raw_n
                stats[source]['done'] += 1
                results.extend(jobs)
        except Exception as e:
            with lock:
                stats[source]['done'] += 1
                stats[source]['errors'].append(f'{type(e).__name__}: {e}')
            print(f'  [notify] {source}/{role} error: {e}')

    threads = [
        threading.Thread(target=fetch, args=(src, role), daemon=True)
        for role in SCHEDULED_ROLES
        for src in sources
    ]
    for t in threads:
        t.start()
    # One budget for the whole fan-out rather than 60s per thread: the browser
    # sources are slow and joining them serially made the real limit unknowable.
    deadline = time.time() + _SCAN_BUDGET_SEC
    for t in threads:
        t.join(timeout=max(0.0, deadline - time.time()))

    with lock:
        collected = list(results)   # stable snapshot; abandoned threads may still append
    for src in sources:
        stats[src]['timed_out'] = len(SCHEDULED_ROLES) - stats[src]['done']

    # Deduplicate by URL
    seen_now, all_jobs = set(), []
    for job in collected:
        url = job.get('url', '')
        if url and url not in seen_now:
            seen_now.add(url)
            all_jobs.append(job)

    new_jobs = [j for j in all_jobs if j.get('url') and j['url'] not in seen]
    # Split "already reported" from "rejected by the filters" — from the outside
    # both look like a silent source, but only the second means the source is
    # returning things that never match what is being searched for.
    unseen_by_label = collections.Counter(j.get('source') for j in new_jobs)

    # Keep only management-level jobs. Team leads are included — "QA Team Leader"
    # is one of the roles being searched for.
    def _is_mgmt(title):
        t = title.lower()
        return any(kw in t for kw in [
            'מנהל', 'manager', 'director', 'head of', 'vp', 'vice president',
            'ראש צוות', 'team lead', 'group leader', 'טים ליד',
            # "QA Lead" is the same job as "QA Team Leader" and was being
            # dropped. Spelled out per domain rather than a bare 'lead', which
            # would also let in "Lead Engineer" and "Tech Lead". The domain word
            # has to come first, so "Lead QA Engineer" still reads as an IC.
            'qa lead', 'test lead', 'delivery lead', 'release lead',
            'program lead', 'project lead', 'pmo lead',
        ]) or ('ראש' in t and 'צוות' not in t)

    # Exclude irrelevant job types (hardware/electronics/materials/defense engineering)
    _BAD_TITLE_KW = [
        # Shaul is not an automation person and does not want to run automation.
        # This rejects the whole family, "QA Automation Manager" included — his
        # explicit call on 19/08/2026, accepting that a "QA Manager (Manual &
        # Automation)" style title goes with it.
        'automation', 'אוטומציה',
        # Quality management outside software. A month-wide sweep surfaced
        # "Head of Quality Assurance (Construction)", "Director Sterile
        # Operational Quality Assurance" and "Global Quality & Sustainability
        # Manager" — all of which clear the topic gate on the word quality.
        # The company list only knew בנייה and קבלן, in Hebrew, so nothing
        # written in English was caught. Title-level, so a software QA post at
        # a pharma company is still fine.
        'construction', 'קבלנ', 'sterile', 'pharmaceutical', 'gmp',
        'regulatory affairs', 'quality systems', 'sustainability',
        'תוכנית עסקית', 'פרויקטים הנדסיים',
        # AllJobs files software QA and factory-floor quality control under the
        # same category (824, "מנהל איכות | מנהל QA"), so opening it up brought
        # in a piping company, a food plant and an industrial manufacturer.
        # These mark the factory sense; 'תעשייה ביטחונית' deliberately is not
        # here, since defence-tech postings at Elbit and IAI are on target.
        'צנרת', 'מפעל', 'תעשייתי', 'מכון התקנים',
        'v&v', 'validation', 'verification',
        'אלקטרוניקה', 'electronics', 'ייצור', 'manufacturing',
        'composite', 'חומרים', 'materials',
        'hardware', 'חומרה', 'מכונות', 'mechanical',
        'עיצוב', 'design engineer',
        'business development',
        'sales', 'מכירות',
        'procurement', 'רכש',
    ]
    def _is_relevant_title(title):
        t = title.lower()
        return not any(kw in t for kw in _BAD_TITLE_KW)

    before_mgmt = len(new_jobs)
    new_jobs = [j for j in new_jobs if _is_mgmt(j.get('title', '') or '')]
    new_jobs = [j for j in new_jobs if _is_relevant_title(j.get('title', '') or '')]
    # On-topic gate: applies to every source, including the ones that are trusted
    # to honour the search query (LinkedIn, AllJobs, Drushim) but do not.
    before_topic = len(new_jobs)
    new_jobs = [j for j in new_jobs if _RELEVANT_TITLE_RE.search(j.get('title', '') or '')]
    dropped = before_topic - len(new_jobs)

    # Keep only hi-tech / tech-adjacent companies
    _NONTECH = [
        'cnc', 'renewable energy', 'אנרגיה מתחדשת', 'אנרגיה ירוקה',
        'שמירה ואבטחה', 'מוקד שמירה', 'שרותי שמירה', 'אבטחה פיזית',
        'בנייה', 'קבלן', 'שיפוצים', 'ניקיון',
        'קמעונאות', 'סופרמרקט', 'supermarket',
        # Stems, not whole words: the list said 'מסעדה' and 'מאפייה', which miss
        # 'מסעדת מזון מהיר' and 'מאפיית X' — and a food company advertising
        # מנהל בקרת איכות clears the topic gate on איכות.
        'מזון ומשקאות', 'מאפי', 'מסעד', 'קייטרינג',
        'חקלאות', 'כרייה', 'נדל"ן', 'real estate',
        'הובלה', 'לוגיסטיקה', 'שינוע',
        'בית חולים', 'hospital', 'מרפאה', 'clinic',
        # The insurers used to be listed here — הפניקס, מגדל, כלל, ביטוח ישיר.
        # They all run large in-house R&D arms and hire exactly these titles, so
        # blocking them by name threw away real jobs. The title gates above
        # already require a QA / release / project / delivery management role,
        # which is what actually keeps an insurance-sales post out.
    ]
    def _is_hitech(job):
        text = ((job.get('title') or '') + ' ' + (job.get('company') or '')).lower()
        return not any(kw in text for kw in _NONTECH)
    new_jobs = [j for j in new_jobs if _is_hitech(j)]

    # Age gate. Sources that state a date get held to Shaul's two-day rule; the
    # ones that state none pass here and are bounded by _SCAN_WINDOW instead.
    # SecretJobs made the case for this: its listings had a median age of 49
    # days and he clicked one that had closed a month earlier.
    _cutoff = (_now_il().date() - timedelta(days=_MAX_JOB_AGE_DAYS)).isoformat()
    _before_age = len(new_jobs)
    new_jobs = [j for j in new_jobs
                if not (j.get('date') or '') or (j['date'][:10] >= _cutoff)]
    _aged_out = _before_age - len(new_jobs)
    if _aged_out:
        print(f'[notify] {_aged_out} dropped as older than {_MAX_JOB_AGE_DAYS} days')

    # Drop anything already dealt with.
    #
    # applications.json is the record Shaul keeps by hand, and in the cloud it
    # does nothing: the file is gitignored — correctly, it names where he
    # applied and this repo is public — so it is never checked out on a runner,
    # _load_apps() returns [] and the filter passes everything through. It only
    # ever worked on his own machine.
    #
    # jobs.jsonl is committed, so a status set there does survive a run. Marking
    # from Telegram was reverted on 19/08/2026, so nothing sets one today, but
    # reading it is what makes that possible again without this trap returning.
    acted = {rec.get('url') for rec in _load_jobs().values()
             if rec.get('status') in ('applied', 'skipped') and rec.get('url')}
    acted |= {a['url'] for a in _load_apps() if a.get('url')}
    new_jobs = [j for j in new_jobs if j.get('url') not in acted]
    print(f'[notify] {len(all_jobs)} total, {before_mgmt} new, {len(new_jobs)} after filters '
          f'({dropped} dropped as off-topic)')

    # Keep a full record of everything about to be reported, and stamp each job
    # with its id. Nothing downstream reads this yet — it is what a Telegram
    # button will resolve against once there is something listening for the
    # press. Purely additive: the message below is built exactly as before.
    new_jobs = _record_jobs(new_jobs)

    # This used to be `set(list(updated_seen)[-4000:])` once past 5000, which
    # reads as "keep the newest 4000" but is not: a set has no order, so the
    # slice kept an arbitrary 4000 and threw away ~1000 at random. Anything
    # dropped that was still listed came back as new the next hour, which is
    # where the duplicate notifications on 17-18/08/2026 came from.
    #
    # Two changes: the cap is high enough that pruning is rare, and when it does
    # happen the urls seen in this very scan are kept first. Those are the only
    # ones that can cause a duplicate — a posting nobody lists any more cannot
    # be re-found, so forgetting it is free.
    live = {j['url'] for j in all_jobs if j.get('url')}
    updated_seen = seen | live
    if len(updated_seen) > _SEEN_JOBS_CAP:
        keep = set(live)
        for url in sorted(updated_seen - live):
            if len(keep) >= _SEEN_JOBS_CAP:
                break
            keep.add(url)
        print(f'[notify] seen_jobs pruned {len(updated_seen) - len(keep)} old urls '
              f'({len(live)} from this scan kept)')
        updated_seen = keep
    _save_seen_jobs(updated_seen)

    now  = _now_il()
    hour = f'{now:%H:%M}'
    date = f'{now:%Y-%m-%d}'

    # Why each empty-handed source came back empty. "Nothing new" and "the
    # scraper crashed" look identical from the outside, so spell out which it was.
    delivered = collections.Counter(j.get('source') for j in new_jobs)
    problems = []
    for src in sources:
        label = _SOURCE_LABELS.get(src, src)
        if delivered.get(label):
            continue
        st = stats[src]
        if st['errors']:
            err = st['errors'][0]
            extra = f' (ועוד {len(st["errors"]) - 1})' if len(st['errors']) > 1 else ''
            reason = f'שגיאה — {_esc(err[:90])}{extra}'
        elif st['timed_out']:
            reason = f'timeout — {st["timed_out"]}/{len(SCHEDULED_ROLES)} חיפושים לא הסתיימו'
        elif st['raw'] == 0:
            reason = 'רץ תקין, 0 תוצאות'
        elif not unseen_by_label.get(label):
            # Said "already sent" for a year, which was never true: these were
            # scraped and filtered out, not sent. The wording hid the fact that
            # Dialog, Nisha and SQLink had never produced a single on-target job
            # — it read like healthy deduplication instead of a broken scraper.
            reason = f'{st["raw"]} נסרקו, כולן כבר נראו בסריקה קודמת'
        else:
            reason = (f'{unseen_by_label[label]} חדשות מתוך {st["raw"]}, '
                      f'כולן נפסלו כלא רלוונטיות')
        problems.append(f'• <b>{_esc(label)}</b> — {reason}')
    if problems:
        print('[notify] sources with no results:')
        for p in problems:
            print(f'    {re.sub("<[^>]+>", "", p)}')

    if not new_jobs:
        print('[notify] No new jobs')
        if not always_notify:
            print('[notify] skipping Telegram')
            return
        header = f'🔍 <b>אין משרות חדשות{scope}</b> — {hour}'
        if problems:
            _send_sectioned(header, [('⚠️ מקורות ללא תוצאות', problems)])
        else:
            _send_notification(header)
        return

    # LinkedIn is tracked separately from the Israeli boards
    li_jobs    = [j for j in new_jobs if (j.get('source') or '').lower() == 'linkedin']
    other_jobs = [j for j in new_jobs if (j.get('source') or '').lower() != 'linkedin']
    groups = [
        (f'💼 משרות לינקדאין ({len(li_jobs)})',  li_jobs),
        (f'📋 כל השאר ({len(other_jobs)})',      other_jobs),
    ]

    # Generate HTML file for GitHub Pages
    jobs_html = ''
    for heading, group in groups:
        if not group:
            continue
        jobs_html += f'\n        <h2>{heading}</h2>'
        for j in group:
            title   = (j.get('title') or '').replace('<', '&lt;').replace('>', '&gt;')
            company = (j.get('company') or '').replace('<', '&lt;').replace('>', '&gt;')
            url     = j.get('url', '')
            source  = (j.get('source') or '').replace('<', '&lt;')
            jobs_html += f'''
        <div class="job">
          <a href="{url}" target="_blank">{title}</a>
          <div class="company">{company}</div>
          <div class="source">{source}</div>
        </div>'''

    html = f'''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>משרות חדשות — {date}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, Arial, sans-serif; background: #f0f2f5; padding: 16px; }}
  h1 {{ font-size: 17px; color: #333; margin-bottom: 14px; padding: 12px 16px;
        background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  .job {{ background: white; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px;
          box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  .job a {{ color: #0a7cff; text-decoration: none; font-size: 15px; font-weight: 600;
             display: block; margin-bottom: 5px; line-height: 1.3; }}
  .company {{ color: #555; font-size: 13px; margin-bottom: 3px; }}
  .source {{ color: #aaa; font-size: 11px; }}
  h2 {{ font-size: 14px; color: #444; margin: 18px 4px 8px; }}
</style>
</head>
<body>
<h1>🔍 {len(new_jobs)} משרות חדשות &nbsp;·&nbsp; {date} {hour}</h1>
{jobs_html}
</body>
</html>'''

    # Save HTML: a per-run snapshot (so an old message's link keeps showing *its*
    # jobs) plus jobs.html as the always-latest copy.
    snapshot = f'jobs-{now:%Y%m%d-%H%M}.html'
    try:
        os.makedirs('docs', exist_ok=True)
        for name in (snapshot, 'jobs.html'):
            with open(os.path.join('docs', name), 'w', encoding='utf-8') as f:
                f.write(html)
        print(f'[notify] HTML saved to docs/{snapshot} (+ jobs.html)')
        # A snapshot per run that finds something, hourly, piles up over months.
        old = sorted(g for g in os.listdir('docs')
                     if g.startswith('jobs-') and g.endswith('.html'))[:-200]
        for name in old:
            os.remove(os.path.join('docs', name))
        if old:
            print(f'[notify] pruned {len(old)} old snapshots')
    except Exception as e:
        print(f'[notify] HTML save failed: {e}')

    # Send Telegram: the jobs themselves, inline. The header count and the list
    # come from the same new_jobs, so they can never disagree.
    sections = [(heading, [_job_line(j) for j in group]) for heading, group in groups]
    if problems:
        sections.append(('⚠️ מקורות ללא תוצאות', problems))

    # Link only when this run also publishes the snapshot; locally nothing is
    # pushed, so a link would just serve the previous run's page.
    footer = ''
    if os.getenv('GITHUB_ACTIONS'):
        pages_url = f'https://shaulmano.github.io/shaul-job-search/{snapshot}'
        footer = f'\n<a href="{pages_url}">📋 פתח כדף</a>'

    _send_sectioned(f'🔍 <b>{len(new_jobs)} משרות חדשות{scope}</b> — {hour}', sections, footer)


_load_seen_jobs()   # pre-load at startup

# ── Application tracker ───────────────────────────────────────────────────────
import uuid as _uuid_mod

_APPS_FILE = '/data/applications.json' if os.path.isdir('/data') else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'applications.json')


def _load_apps():
    try:
        with open(_APPS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_apps(apps):
    try:
        with open(_APPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(apps, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'  [apps] save error: {e}')


# ── HTTP Server ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/health':
            self._json({'status': 'ok', 'playwright': PLAYWRIGHT_OK})
            return

        if parsed.path == '/stream':
            self._handle_stream(parse_qs(parsed.query))
            return

        if parsed.path == '/notify':
            # SSE: keeps HTTP connection alive during search → machine doesn't auto-stop
            try:
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-Accel-Buffering', 'no')
                self.end_headers()
            except Exception:
                return
            done = [False]
            def _do():
                _run_notify_job()
                done[0] = True
            threading.Thread(target=_do, daemon=True).start()
            while not done[0]:
                try:
                    self.wfile.write(b': k\n\n')
                    self.wfile.flush()
                    time.sleep(10)
                except Exception:
                    break
            try:
                self.wfile.write(b'data: done\n\n')
                self.wfile.flush()
            except Exception:
                pass
            return

        if parsed.path == '/applications':
            self._json(_load_apps())
            return

        if parsed.path == '/daily':
            _df = '/data/daily.json' if os.path.isdir('/data') else os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'daily.json')
            try:
                with open(_df, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {'time': '', 'jobs': []}
            jobs = data.get('jobs', [])
            run_time = data.get('time', '')
            from collections import defaultdict as _dd
            by_src = _dd(list)
            for j in jobs:
                by_src[j.get('source','אחר')].append(j)
            SOURCE_COLORS = {
                'LinkedIn':'#0077b5','Indeed':'#003a9b','AllJobs':'#7b2d8b',
                'Drushim':'#1a7a40','Comeet':'#2d6a4f','GotFriends':'#e67e00',
                'Experis':'#b71c1c','Dialog':'#0d5c9e','SQLink':'#1b5e20',
                'Nisha':'#6a1b9a',
            }
            import html as _hm
            cards = ''
            for src, sjobs in sorted(by_src.items(), key=lambda x: -len(x[1])):
                color = SOURCE_COLORS.get(src, '#555')
                cards += f'<div class="src-header" style="border-color:{color};color:{color}">{_hm.escape(src)} — {len(sjobs)} משרות</div>'
                for j in sjobs:
                    title   = _hm.escape((j.get('title','') or '')[:70])
                    company = _hm.escape((j.get('company','') or '')[:40])
                    url     = j.get('url','') or ''
                    apply_url = (f'https://shaul-job-search.fly.dev/apply'
                                 f'?url={quote(url)}&title={quote(j.get("title",""))}'
                                 f'&company={quote(j.get("company",""))}&source={quote(src)}') if url else ''
                    cards += f'''<div class="card">
  <div class="title">{f'<a href="{_hm.escape(url)}">{title}</a>' if url else title}</div>
  <div class="company">{company} · <span style="color:{color}">{_hm.escape(src)}</span></div>
  {f'<a href="{_hm.escape(apply_url)}" class="apply-btn">✅ הגשתי</a>' if apply_url else ''}
</div>'''
            html_page = f'''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>משרות חדשות — {run_time}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;background:#f1f5f9;padding:12px;direction:rtl}}
h1{{font-size:1.1em;font-weight:800;color:#1e293b;margin-bottom:4px}}
.sub{{color:#64748b;font-size:.82em;margin-bottom:16px}}
.src-header{{font-weight:700;font-size:.88em;border-right:4px solid;padding:6px 10px;
             background:white;border-radius:8px 8px 0 0;margin-top:14px;margin-bottom:1px}}
.card{{background:white;padding:12px;margin-bottom:2px;border-right:1px solid #e2e8f0}}
.card:last-of-type{{border-radius:0 0 8px 8px;margin-bottom:0}}
.title{{font-weight:700;font-size:.95em;margin-bottom:3px}}
.title a{{color:#1e293b;text-decoration:none}}
.company{{color:#64748b;font-size:.82em;margin-bottom:6px}}
.apply-btn{{display:inline-block;background:#16a34a;color:white;padding:6px 14px;
            border-radius:7px;font-size:.8em;font-weight:700;text-decoration:none}}
</style></head>
<body>
<h1>🔍 {len(jobs)} משרות חדשות</h1>
<div class="sub">{run_time}</div>
{cards}
</body></html>'''
            body = html_page.encode('utf-8')
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == '/apply':
            # GET → confirmation page only (do NOT record yet — Telegram crawls this URL)
            qs      = parse_qs(parsed.query)
            job_url = qs.get('url',     [''])[0]
            title   = qs.get('title',   [''])[0]
            company = qs.get('company', [''])[0]
            source  = qs.get('source',  [''])[0]
            import html as _html_mod
            safe_url     = _html_mod.escape(job_url)
            safe_title   = _html_mod.escape(title)
            safe_company = _html_mod.escape(company)
            safe_source  = _html_mod.escape(source)
            html_page = f'''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>אישור הגשה</title>
<style>
  body{{font-family:Arial,sans-serif;text-align:center;padding:40px;background:#f8fafc;margin:0}}
  .card{{background:white;border-radius:16px;padding:30px;max-width:420px;margin:0 auto;box-shadow:0 2px 20px rgba(0,0,0,.1)}}
  .jt{{font-weight:700;font-size:1.1em;margin:12px 0 4px}} .jc{{color:#64748b;margin-bottom:20px}}
  .btn{{background:#16a34a;color:white;border:none;padding:14px 28px;border-radius:10px;font-size:1em;font-weight:700;cursor:pointer;width:100%;margin-top:8px}}
  .btn:hover{{background:#15803d}}
  .link{{color:#6366f1;font-size:.85em;display:block;margin-top:14px}}
</style></head>
<body><div class="card">
  <div style="font-size:2.5em">📋</div>
  <h2 style="margin:8px 0">לסמן כ"הגשתי"?</h2>
  <div class="jt">{safe_title}</div>
  <div class="jc">{safe_company} · {safe_source}</div>
  <form method="POST" action="/apply-confirm">
    <input type="hidden" name="url"     value="{safe_url}">
    <input type="hidden" name="title"   value="{safe_title}">
    <input type="hidden" name="company" value="{safe_company}">
    <input type="hidden" name="source"  value="{safe_source}">
    <button class="btn" type="submit">✅ כן, הגשתי</button>
  </form>
  <a class="link" href="{safe_url}" target="_blank">פתח המשרה המקורית ↗</a>
</div></body></html>'''
            body = html_page.encode('utf-8')
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path != '/search':
            self.send_response(404)
            self.end_headers()
            return

        params      = parse_qs(parsed.query)
        roles_raw   = params.get('roles',   ['QA Manager'])[0]
        time_filter = params.get('time',    ['20h'])[0]
        sources_raw = params.get('sources', ['linkedin'])[0]

        roles   = [r.strip() for r in roles_raw.split(',')   if r.strip()]
        sources = [s.strip() for s in sources_raw.split(',') if s.strip()]

        results = []
        errors  = {}
        lock    = threading.Lock()
        threads = []

        def fetch(source, role):
            scraper = SCRAPERS.get(source)
            if not scraper:
                return
            try:
                t0   = time.time()
                jobs = scraper(role, time_filter)
                elapsed = round(time.time() - t0, 1)
                print(f'  [{source}] "{role}" → {len(jobs)} jobs ({elapsed}s)')
                with lock:
                    results.extend(jobs)
            except Exception as e:
                print(f'  [{source}] "{role}" ERROR: {e}')
                with lock:
                    errors[f'{source}/{role}'] = str(e)

        # LinkedIn runs first (fast, no Playwright)
        linkedin_threads = []
        other_threads    = []
        for src in sources:
            for role in roles:
                t = threading.Thread(target=fetch, args=(src, role), daemon=True)
                (linkedin_threads if src == 'linkedin' else other_threads).append(t)

        for t in linkedin_threads:
            t.start()
        li_deadline = time.time() + 12
        for t in linkedin_threads:
            t.join(timeout=max(0, li_deadline - time.time()))

        for t in other_threads:
            t.start()
        # 18s budget — stay well under any proxy timeout
        other_deadline = time.time() + 18
        for t in other_threads:
            t.join(timeout=max(0.1, other_deadline - time.time()))

        # Deduplicate by URL
        seen, unique = set(), []
        for job in results:
            key = job['url']
            if key and key not in seen:
                seen.add(key)
                unique.append(job)

        print(f'  ✓ Total unique: {len(unique)}  Errors: {len(errors)}')
        self._json({'jobs': unique, 'errors': errors})

    def _handle_stream(self, params):
        roles_raw   = params.get('roles',   ['QA Manager'])[0]
        time_filter = params.get('time',    ['20h'])[0]
        sources_raw = params.get('sources', ['linkedin'])[0]
        roles   = [r.strip() for r in roles_raw.split(',') if r.strip()]
        sources = [s.strip() for s in sources_raw.split(',') if s.strip()]

        try:
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
        except Exception:
            return

        write_lock = threading.Lock()
        seen_urls  = set()
        alive      = [True]

        def send_event(data):
            if not alive[0]:
                return
            try:
                payload = 'data: ' + json.dumps(data, ensure_ascii=False) + '\n\n'
                with write_lock:
                    self.wfile.write(payload.encode('utf-8'))
                    self.wfile.flush()
            except (ConnectionAbortedError, BrokenPipeError, OSError):
                alive[0] = False

        def run_scraper(source, role):
            scraper = SCRAPERS.get(source)
            if not scraper:
                return
            try:
                t0   = time.time()
                jobs = scraper(role, time_filter)
                # Generic role-relevance filter for sources known to return noisy results
                _NOISY_SOURCES = {'experis', 'dialog', 'sqlink', 'malamteam', 'nisha', 'gotfriends', 'jobmaster'}
                if source in _NOISY_SOURCES:
                    role_l = role.lower()
                    if any(k in role_l for k in ['qa', 'quality', 'test', 'automation', 'sqa', 'qc']):
                        keywords = {'qa', 'quality', 'בדיקות', 'test', 'automation', 'אוטומציה', 'איכות', 'qc', 'sqa'}
                    elif any(k in role_l for k in ['project', 'program', 'pmo', 'delivery', 'release', 'scrum']):
                        keywords = {'project', 'program', 'פרויקט', 'pm', 'pmo', 'תוכנית', 'programme',
                                    'delivery', 'release', 'scrum', 'agile', 'ניהול פרויקט', 'מנהל פרויקט'}
                    else:
                        keywords = _drushim_keywords(role)
                    before = len(jobs)
                    jobs = [j for j in jobs
                            if any(kw in (j.get('title','') + ' ' + j.get('company','')).lower()
                                   for kw in keywords)]
                    if before != len(jobs):
                        print(f'  [{source}] filtered {before-len(jobs)} irrelevant jobs')
                elapsed = round(time.time() - t0, 1)
                print(f'  [{source}] "{role}" -> {len(jobs)} jobs ({elapsed}s)')
                if not jobs or not alive[0]:
                    return
                with write_lock:
                    new_jobs = [j for j in jobs if j.get('url') and j['url'] not in seen_urls]
                    for j in new_jobs:
                        seen_urls.add(j['url'])
                if new_jobs:
                    send_event({'jobs': new_jobs, 'source': source})
            except Exception as e:
                print(f'  [{source}] "{role}" ERROR: {e}')

        import concurrent.futures
        tasks = [(src, role) for src in sources for role in roles]
        deadline = time.time() + 90

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(run_scraper, src, role) for src, role in tasks]
            for f in concurrent.futures.as_completed(futures, timeout=max(1, deadline - time.time())):
                try:
                    f.result()
                except Exception:
                    pass

        send_event({'done': True})

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/daily-update':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            _df = '/data/daily.json' if os.path.isdir('/data') else os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'daily.json')
            try:
                with open(_df, 'wb') as f:
                    f.write(body)
            except Exception:
                pass
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        if parsed.path == '/apply-confirm':
            # Actual recording — only triggered by user pressing the button
            length   = int(self.headers.get('Content-Length', 0))
            raw      = self.rfile.read(length).decode('utf-8')
            from urllib.parse import parse_qs as _pqs, unquote_plus as _uqp
            fields   = {k: v[0] for k, v in _pqs(raw).items()}
            job_url  = fields.get('url', '')
            title    = fields.get('title', '')
            company  = fields.get('company', '')
            source   = fields.get('source', '')
            already  = False
            if job_url:
                apps = _load_apps()
                already = any(a.get('url') == job_url for a in apps)
                if not already:
                    apps.append({
                        'id':           str(_uuid_mod.uuid4()),
                        'title':        title,
                        'company':      company,
                        'source':       source,
                        'url':          job_url,
                        'date_applied': time.strftime('%Y-%m-%d'),
                        'status':       'נשלח',
                        'notes':        'הוגש מטלגרם',
                    })
                    _save_apps(apps)
            import html as _hm
            msg = 'כבר רשומה' if already else 'נרשמה!'
            html_done = f'''<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>הגשה נרשמה</title>
<style>body{{font-family:Arial,sans-serif;text-align:center;padding:40px;background:#f0fdf4;margin:0}}
.card{{background:white;border-radius:16px;padding:30px;max-width:420px;margin:0 auto;box-shadow:0 2px 20px rgba(0,0,0,.1)}}
a{{color:#6366f1;font-weight:700;text-decoration:none;display:block;margin-top:16px}}</style></head>
<body><div class="card">
  <div style="font-size:2.8em">✅</div>
  <h2 style="color:#16a34a">הגשה {_hm.escape(msg)}</h2>
  <div style="font-weight:700">{_hm.escape(title)}</div>
  <div style="color:#64748b">{_hm.escape(company)}</div>
  <a href="https://job-search-cloud.vercel.app/">📋 פתח מרכז חיפוש</a>
</div></body></html>'''.encode('utf-8')
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(html_done)))
            self.end_headers()
            self.wfile.write(html_done)
            return

        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        if parsed.path == '/applications':
            length = int(self.headers.get('Content-Length', 0))
            body   = json.loads(self.rfile.read(length))
            apps   = _load_apps()
            new    = {
                'id':           str(_uuid_mod.uuid4()),
                'title':        body.get('title', ''),
                'company':      body.get('company', ''),
                'url':          body.get('url', ''),
                'source':       body.get('source', ''),
                'date_applied': body.get('date_applied', time.strftime('%Y-%m-%d')),
                'status':       body.get('status', 'נשלח'),
                'notes':        body.get('notes', ''),
            }
            apps.append(new)
            _save_apps(apps)
            self.wfile.write(json.dumps(new, ensure_ascii=False).encode('utf-8'))

    def do_PUT(self):
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        parsed = urlparse(self.path)
        if parsed.path.startswith('/applications/'):
            app_id = parsed.path.rsplit('/', 1)[-1]
            length = int(self.headers.get('Content-Length', 0))
            body   = json.loads(self.rfile.read(length))
            apps   = _load_apps()
            for a in apps:
                if a['id'] == app_id:
                    a.update({k: v for k, v in body.items() if k != 'id'})
                    break
            _save_apps(apps)
            self.wfile.write(b'{"ok":true}')

    def do_DELETE(self):
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        parsed = urlparse(self.path)
        if parsed.path.startswith('/applications/'):
            app_id = parsed.path.rsplit('/', 1)[-1]
            apps   = [a for a in _load_apps() if a['id'] != app_id]
            _save_apps(apps)
        self.wfile.write(b'{"ok":true}')

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        try:
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, OSError):
            pass  # client disconnected before we finished — ignore

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    print(f'\nJob Search Server -> http://localhost:{PORT}')
    print(f'Playwright: {"ready" if PLAYWRIGHT_OK else "NOT installed"}')
    if not PLAYWRIGHT_OK:
        print('Run: pip install playwright && playwright install chromium')
    print('Press Ctrl+C to stop\n')
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
