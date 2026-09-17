"""Drop foreign companies that post under an Israeli location.

LinkedIn tags plenty of postings "Tel Aviv District, Israel" that belong to
companies with no one in Israel (Renvada, 17/09/2026). The location field is
no help: all 1,143 stored jobs carried an Israeli one. Two layers instead:
  1. blocked_companies.json, a hand-kept list of company names, any case.
  2. Signals in the description that only a US employer writes. Only jobs
     that were enriched carry a description, so layer 1 is the backstop.

Installed from run_notify.py by wrapping every scraper in job_server.SCRAPERS,
so a blocked job is dropped before it is deduped, recorded or sent.
"""
import json
import os
import re

_BLOCKED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'blocked_companies.json')


def _load_blocked_companies():
    try:
        with open(_BLOCKED_FILE, encoding='utf-8') as f:
            return {str(n).strip().lower() for n in json.load(f) if str(n).strip()}
    except Exception:
        return set()


# One of these is enough: nobody hiring in Israel asks for them.
_FOREIGN_STRONG_RE = re.compile(
    r'authori[sz]ed to work in the (u\.?s\.?|united states)'
    r'|\bw-?2\b|\b401\s?\(?k\)?|\bus citizen|\bgreen card'
    r'|security clearance.{0,20}\b(u\.?s\.?|dod)\b'
    r'|\b(u\.?s\.?|us)[\s-]based (role|position|candidates?)',
    re.IGNORECASE,
)
# Each of these alone happens at Israeli companies too, so it takes two.
_FOREIGN_WEAK_RE = re.compile(
    r'\$\s?\d{2,3}(,\d{3}|k)'
    r'|\busd\b|\b(est|pst|cst|mst|et|pt)\b(?=[^a-z]{0,3}(time|zone|hours|\)))'
    r'|eastern time|pacific time|central time'
    r'|remote\W{1,3}(u\.?s\.?|united states)|\bmedical, dental\b|\bpto\b',
    re.IGNORECASE,
)


def _is_foreign(job, blocked=None):
    company = (job.get('company') or '').strip().lower()
    if company and blocked and company in blocked:
        return True
    desc = job.get('li_description') or ''
    if not desc:
        return False
    if _FOREIGN_STRONG_RE.search(desc):
        return True
    weak = {m.group(0).lower() for m in _FOREIGN_WEAK_RE.finditer(desc)}
    return len(weak) >= 2


def install(job_server):
    """Wrap each scraper so its results pass through _is_foreign."""
    def wrap(name, fn):
        def filtered(*args, **kwargs):
            jobs = fn(*args, **kwargs) or []
            blocked = _load_blocked_companies()
            kept = [j for j in jobs if not _is_foreign(j, blocked)]
            if len(kept) != len(jobs):
                print(f'  [{name}] {len(jobs) - len(kept)} dropped as foreign companies')
            return kept
        return filtered
    for name, fn in list(job_server.SCRAPERS.items()):
        job_server.SCRAPERS[name] = wrap(name, fn)
