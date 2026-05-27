#!/usr/bin/env python3
"""
Job Search Server — backend for job-search-hub.html
Uses Playwright (headless Chrome) for JS-rendered Israeli sites.
Run via start_jobs.bat
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
import requests
from bs4 import BeautifulSoup

import os
PORT = int(os.environ.get('PORT', 8765))
PW_SEMAPHORE = threading.Semaphore(2)   # max 2 Chromium instances at once

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'he-IL,he;q=0.9,en-US;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

TIME_MAP = {'20h': 'r72000', 'week': 'r604800', 'month': 'r2592000'}

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
    """Fetch recruiter name+URL from LinkedIn job detail page (guest API)."""
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
    except Exception:
        pass
    return job


def search_linkedin(role, time_filter):
    import concurrent.futures
    tpr = TIME_MAP.get(time_filter, 'r72000')
    url = (
        'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search'
        f'?keywords={quote(role)}&location=Israel&f_TPR={tpr}&start=0&count=50'
    )
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, 'html.parser')
    jobs = []
    for card in soup.find_all('li'):
        title_el   = card.find('h3', class_='base-search-card__title')
        company_el = card.find('h4', class_='base-search-card__subtitle')
        link_el    = card.find('a', class_='base-card__full-link')
        time_el    = card.find('time')
        loc_el     = card.find('span', class_='job-search-card__location')

        if not (title_el and company_el and link_el):
            continue

        href = link_el.get('href', '').split('?')[0]
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

    # Enrich with recruiter info in parallel (best-effort, 15s budget)
    if jobs:
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                jobs = list(ex.map(_linkedin_fetch_recruiter, jobs, timeout=15))
        except Exception:
            pass

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
def search_alljobs(role, time_filter='20h'):
    url = f'https://www.alljobs.co.il/SearchResultsPage.aspx?position={quote(role)}'
    return pw_scrape(
        url=url, source='AllJobs', base_url='https://www.alljobs.co.il',
        selectors=['.cJobItem', '.job-content', '[class*="job-item"]', 'article.job'],
        title_sel='h2, h3, .job-title, [class*="title"]',
        link_sel='a[href*="/Job/"]',
        company_sel='[class*="company"]',
        date_sel='[class*="date"], time',
        wait_sel='.cJobItem',
    )


# ── Drushim ───────────────────────────────────────────────────────────────────
def search_drushim(role, time_filter='20h'):
    url = f'https://www.drushim.co.il/jobs/searchjobs/?q={quote(role)}'
    return pw_scrape(
        url=url, source='Drushim', base_url='https://www.drushim.co.il',
        selectors=['.job_', '[class^="job_"]', '.jobs-list li', 'article[class*="job"]'],
        title_sel='h2, h3, [class*="title"], a',
        link_sel='a[href*="/job/"]',
        company_sel='[class*="company"], [class*="employer"]',
        date_sel='time, [class*="date"]',
        wait_sel='[class^="job_"]',
    )


# ── GotFriends ────────────────────────────────────────────────────────────────
def search_gotfriends(role, time_filter='20h'):
    url = f'https://www.gotfriends.co.il/jobs/?q={quote(role)}'
    return pw_scrape(
        url=url, source='GotFriends', base_url='https://www.gotfriends.co.il',
        selectors=['.job-item', '.position-item', '[class*="job-card"]', 'li[class*="job"]'],
        title_sel='h2, h3, h4, [class*="title"]',
        link_sel='a',
        company_sel='[class*="company"]',
        wait_sel='.job-item, .position-item',
    )


# ── Experis ───────────────────────────────────────────────────────────────────
def search_experis(role, time_filter='20h'):
    url = f'https://www.experis.co.il/jobs?q={quote(role)}'
    return pw_scrape(
        url=url, source='Experis', base_url='https://www.experis.co.il',
        selectors=['[class*="job-card"]', '[class*="position"]', 'article', '.job'],
        title_sel='h2, h3, h4, [class*="title"]',
        link_sel='a',
        wait_sel='[class*="job-card"], [class*="position"]',
    )


# ── Dialog ────────────────────────────────────────────────────────────────────
def search_dialog(role, time_filter='20h'):
    role_lower = role.lower()
    if any(k in role_lower for k in ['qa', 'quality', 'test']):
        url = 'https://www.dialog.co.il/high-tech/jobs/qa'
    elif any(k in role_lower for k in ['program', 'project', 'release', 'delivery']):
        url = 'https://www.dialog.co.il/high-tech/jobs/project-management'
    else:
        url = 'https://www.dialog.co.il/high-tech/jobs'

    return pw_scrape(
        url=url, source='Dialog', base_url='https://www.dialog.co.il',
        selectors=['article.type-job', '.wpjb-loop-row', '.job-listing', 'article'],
        title_sel='h2, h3, .wpjb-col-title, [class*="title"]',
        link_sel='a[href*="dialog.co.il"]',
        date_sel='time, [class*="date"]',
        wait_sel='article',
    )


# ── SQLink ────────────────────────────────────────────────────────────────────
def search_sqlink(role, time_filter='20h'):
    url = 'https://www.sqlink.com/%D7%9E%D7%A9%D7%A8%D7%95%D7%AA-%D7%91%D7%94%D7%99%D7%99%D7%98%D7%A7/'
    return pw_scrape(
        url=url, source='SQLink', base_url='https://www.sqlink.com',
        selectors=['article', '.job-item', '[class*="job"]', 'li.wpjb-loop-row'],
        title_sel='h2, h3, [class*="title"]',
        link_sel='a',
        wait_sel='article',
    )


# ── Nisha ─────────────────────────────────────────────────────────────────────
def search_nisha(role, time_filter='20h'):
    url = f'https://www.nisha.co.il/job_cat/high-tech/?s={quote(role)}'
    return pw_scrape(
        url=url, source='Nisha', base_url='https://www.nisha.co.il',
        selectors=['article.type-job', '.job_listings li', '[class*="job"]', 'article'],
        title_sel='h2, h3, [class*="title"], .job-title',
        link_sel='a[href*="nisha.co.il"]',
        date_sel='time, [class*="date"]',
        wait_sel='article',
    )


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
    import xml.etree.ElementTree as ET
    fromage = {'20h': '1', 'week': '7', 'month': '30'}.get(time_filter, '1')
    url = f'https://il.indeed.com/rss?q={quote(role)}&l=Israel&fromage={fromage}&sort=date'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        jobs = []
        for item in root.findall('./channel/item'):
            title   = item.findtext('title', '').strip()[:120]
            company = item.findtext('{http://www.indeed.com/about/legal}employer', '') or \
                      item.findtext('author', '').strip()
            date    = item.findtext('pubDate', '').strip()
            link    = item.findtext('link', '').strip()
            loc     = item.findtext('{http://www.indeed.com/about/legal}city', 'Israel').strip()
            if not title:
                continue
            jobs.append({
                'title':    title,
                'company':  company,
                'date':     date,
                'url':      link,
                'source':   'Indeed',
                'location': loc,
            })
        return jobs[:20]
    except Exception:
        return []


# ── Malam Team ────────────────────────────────────────────────────────────────
def search_malamteam(role, time_filter='20h'):
    url = 'https://career.malamteam.com/%D7%A8%D7%A9%D7%99%D7%9E%D7%AA-%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/'
    return pw_scrape(
        url=url, source='Malam Team', base_url='https://career.malamteam.com',
        selectors=['article', '.job-listing', '[class*="job"]', 'li.wpjb-loop-row'],
        title_sel='h2, h3, [class*="title"], a',
        link_sel='a[href*="malamteam"]',
        date_sel='time, [class*="date"]',
        wait_sel='article, [class*="job"]',
    )


# ── Maof ──────────────────────────────────────────────────────────────────────
def search_maof(role, time_filter='20h'):
    url = f'https://www.maof-hr.co.il/%D7%9E%D7%A9%D7%A8%D7%95%D7%AA/?s={quote(role)}'
    return pw_scrape(
        url=url, source='Maof', base_url='https://www.maof-hr.co.il',
        selectors=['article', '.job-listing', '[class*="job"]', '.position'],
        title_sel='h2, h3, [class*="title"]',
        link_sel='a[href*="maof-hr.co.il"]',
        date_sel='time, [class*="date"]',
        wait_sel='article',
    )


# ── Sela ──────────────────────────────────────────────────────────────────────
def search_sela(role, time_filter='20h'):
    url = 'https://blog.sela.co.il/Jobs'
    return pw_scrape(
        url=url, source='Sela', base_url='https://blog.sela.co.il',
        selectors=['article', '.job', '[class*="job"]', 'li'],
        title_sel='h2, h3, [class*="title"], a',
        link_sel='a[href*="sela"]',
        wait_sel='article, [class*="job"]',
    )


# ── One1 ──────────────────────────────────────────────────────────────────────
def search_one1(role, time_filter='20h'):
    url = 'https://www.one1.co.il/careers/'
    return pw_scrape(
        url=url, source='One1', base_url='https://www.one1.co.il',
        selectors=['.position', '[class*="job"]', '[class*="career"]', 'article'],
        title_sel='h2, h3, h4, [class*="title"]',
        link_sel='a[href*="one1.co.il"]',
        wait_sel='.position, [class*="job"], article',
    )


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
def search_comeet(role, time_filter='20h'):
    """Scrape Israeli Comeet company boards directly using curl_cffi TLS impersonation."""
    try:
        from curl_cffi import requests as cf_req
    except ImportError:
        print('  [Comeet] curl_cffi not installed — run: pip install curl_cffi')
        return []

    import re, json, concurrent.futures
    from datetime import datetime, timezone, timedelta

    TIME_DELTAS = {'20h': timedelta(hours=20), 'week': timedelta(days=7), 'month': timedelta(days=30)}
    cutoff = datetime.now(timezone.utc) - TIME_DELTAS.get(time_filter, timedelta(hours=20))

    # Build a smarter role matcher: strip generic words so "PMO Manager" only
    # matches jobs that contain "pmo", not any job with "manager".
    _GENERIC = {'manager','director','head','lead','senior','sr','junior','jr',
                'of','the','and','at','in','for','a','an','r&d'}
    role_words_all = set(role.lower().split())
    role_specific  = role_words_all - _GENERIC
    if not role_specific:          # e.g. role = "Manager" → fall back to all words
        role_specific = role_words_all

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

    print(f'  [Comeet] direct scrape → {len(jobs)} jobs across {len(items)} boards')
    return jobs[:50]


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
}


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
        li_deadline = time.time() + 15
        for t in linkedin_threads:
            t.join(timeout=max(0, li_deadline - time.time()))

        for t in other_threads:
            t.start()
        # Global 65-second budget for ALL other sources combined
        other_deadline = time.time() + 65
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
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()

