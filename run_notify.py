"""Entry point for the scheduled Telegram notifications.

    python run_notify.py            # every source (what the hourly workflow runs)
    python run_notify.py linkedin   # LinkedIn only, for a quick manual check
"""
import os, sys

# Load credentials from config.py when running locally (file is gitignored)
try:
    import config as _cfg
    os.environ.setdefault('TELEGRAM_TOKEN', getattr(_cfg, 'TELEGRAM_TOKEN', ''))
    os.environ.setdefault('TELEGRAM_CHAT_ID', getattr(_cfg, 'TELEGRAM_CHAT_ID', ''))
except ImportError:
    pass  # GitHub Actions: credentials come from repository secrets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_server
import foreign_filter
foreign_filter.install(job_server)   # drop foreign companies before anything is recorded

mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'full'

if mode == 'sample':
    # מדפיס מה מקור מחזיר באמת, לפני כל שער. נולד ב-8.11.2026, כשהתברר
    # ש-GotFriends ו-Nisha מחזירים שורות וכל אחת מהן נופלת בשער התחום, ולכן
    # הם לא תרמו אף משרה מעולם בזמן שהם נראים כמו מקור שעובד.
    src = sys.argv[2] if len(sys.argv) > 2 else 'gotfriends'
    # join: התפקיד הוא שתי מילים ויותר, והוא מגיע מהוורקפלו בלי מרכאות.
    role = ' '.join(sys.argv[3:]) or 'Project Manager'
    scraper = job_server.SCRAPERS.get(src)
    if not scraper:
        raise SystemExit(f'unknown source: {src}. known: {", ".join(sorted(job_server.SCRAPERS))}')
    rows = scraper(role) or []
    print(f'[sample] {src} / "{role}" returned {len(rows)} rows')
    for r in rows[:25]:
        print(f"  title={r.get('title','')!r}")
        print(f"     company={r.get('company','')!r}  url={(r.get('url') or '')[:90]}")
elif mode == 'gates':
    # מריץ את שערי הסינון על מה שמקור מחזיר, בלי מסד, בלי seen_jobs, בלי
    # הודעות, ומדפיס מי פסל מה. נולד ב-9.11.2026: דרושים החזיר חמישים משרות
    # חדשות, כולן נפסלו, ולא היה שום מקום לשאול מי פסל אותן.
    #
    #   python run_notify.py gates drushim
    import collections

    src = sys.argv[2] if len(sys.argv) > 2 else 'drushim'
    scraper = job_server.SCRAPERS.get(src)
    if not scraper:
        raise SystemExit(f'unknown source: {src}')

    rows, seen_urls = [], set()
    for role in job_server.SCHEDULED_ROLES:
        got = scraper(role) or []
        fresh = [r for r in got if r.get('url') and r['url'] not in seen_urls]
        for r in fresh:
            seen_urls.add(r['url'])
        rows += fresh
        print(f'  {role:<32} {len(got):>3} rows, {len(fresh):>3} not already counted')
    print(f'\n[gates] {src}: {len(rows)} distinct rows scraped\n')

    GATES = [
        ('mgmt',     lambda j: job_server._is_mgmt(j.get('title') or '')),
        ('badtitle', lambda j: job_server._is_relevant_title(j.get('title') or '')),
        ('topic',    lambda j: bool(job_server._RELEVANT_TITLE_RE.search(
                                    j.get('title') or ''))),
        ('nontech',  lambda j: job_server._is_hitech(j)),
        ('domain',   lambda j: not job_server._off_domain(j)),
        ('age',      job_server._within_age),
    ]
    alive = rows
    for name, keep in GATES:
        gone = [j for j in alive if not keep(j)]
        alive = [j for j in alive if keep(j)]
        print(f'[{name:<8}] dropped {len(gone):>3}, {len(alive):>3} left')
        for j in gone[:10]:
            print(f'      {(j.get("title") or "")[:62]:<62} @ {(j.get("company") or "")[:24]}')
    print(f'\n[gates] {len(alive)} of {len(rows)} survive every gate')
    for j in alive[:30]:
        print(f'  KEEP  {(j.get("title") or "")[:62]:<62} @ {(j.get("company") or "")[:24]}')
elif mode == 'unsee':
    # מוציא מ-seen_jobs משרות של מקור אחד שנסרקו, נפסלו, ולא דווחו מעולם.
    #
    # 9.11.2026: הסריקה רושמת ב-seen_jobs כל כתובת שנסרקה, גם אחת שנפסלה
    # בשער. המשמעות היא ששינוי במסנן לא חל לאחור: אחרי שחלון הגיל של דרושים
    # נפתח ל-14 יום, 892 משרות שנפסלו קודם נשארו מסומנות כנראו ולא היו
    # מגיעות לשאול לעולם.
    #
    # מה שכן דווח נשאר ב-seen_jobs, ולכן אין פה סיכון להתראה כפולה.
    #
    #   python run_notify.py unsee drushim.co.il
    import json

    needle = sys.argv[2] if len(sys.argv) > 2 else ''
    if not needle:
        raise SystemExit('usage: run_notify.py unsee <substring of the url>')

    seen = json.load(open('seen_jobs.json', encoding='utf-8'))
    if isinstance(seen, dict):
        seen = list(seen.get('urls') or seen.keys())

    reported = set()
    with open('jobs.jsonl', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            url = rec.get('url') or (rec.get('job') or {}).get('url')
            if url:
                reported.add(url)

    drop = {u for u in seen if needle in u and u not in reported}
    kept = [u for u in seen if u not in drop]
    print(f'[unsee] {len(seen)} seen, {len(drop)} matching "{needle}" were never '
          f'reported and go back into play, {len(kept)} kept')
    for u in sorted(drop)[:5]:
        print(f'  {u}')
    with open('seen_jobs.json', 'w', encoding='utf-8') as fh:
        json.dump(sorted(kept), fh, ensure_ascii=False)
    print('[unsee] seen_jobs.json rewritten')
elif mode == 'backfill':
    # משלים תיאור למשרות ששמורות כבר ואין להן אחד. האיסוף בזמן הסריקה חל רק
    # על משרות חדשות, ולכן בלי זה המסך נראה בדיוק כמו קודם.
    job_server.backfill_descriptions(int(sys.argv[2]) if len(sys.argv) > 2 else 25)
elif mode == 'linkedin':
    job_server._run_notify_job(
        sources=['linkedin'], always_notify=True, scope=' בלינקדאין')
else:
    # Runs hourly. Silence would be ambiguous — a quiet hour and a broken scraper
    # look identical — so this always reports back, even with nothing new.
    job_server._run_notify_job(
        sources=job_server.SCHEDULED_SOURCES, always_notify=True)
