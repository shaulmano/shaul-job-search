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

if mode == 'atsreport':
    # כמה משרות יש בכל לוח ATS וכמה מהן בישראל. מפריד בין טוקן שגוי לבין לוח
    # ריק, שתי תקלות שנראות זהות דרך הסורק כי שתיהן מחזירות אפס שורות.
    job_server.ats_report()
    raise SystemExit(0)

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
    # 14.11.2026: אותו תיקון כמו ב-gates. הכלי קרא לסורק בברירת המחדל של 20
    # שעות בזמן שהסריקה שואלת לפי _SCAN_WINDOW_BY_SOURCE, ולכן הוא החזיר אפס
    # על מקור שמחזיר שמונים שורות בסריקה אמיתית.
    window = job_server._SCAN_WINDOW_BY_SOURCE.get(src, job_server._SCAN_WINDOW)
    rows = scraper(role, window) or []
    print(f'[sample] {src} / "{role}" window={window} returned {len(rows)} rows')
    for r in rows[:40]:
        print(f"  {r.get('company','')} | {r.get('title','')} | {r.get('date','')}")
        print(f"     {r.get('url') or ''}")
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

    # 14.11.2026: החלון חייב להיות זה שהסריקה האמיתית משתמשת בו.
    #
    # עד כאן הכלי קרא לסורק בלי חלון, כלומר בברירת המחדל של 20 שעות, בזמן
    # שהסריקה שואלת כל מקור לפי _SCAN_WINDOW_BY_SOURCE. ב-Greenhouse זה
    # ההבדל בין חודש לבין 20 שעות, ולכן הכלי החזיר "0 distinct rows
    # scraped" על מקור שמחזיר מאה שורות בסריקה אמיתית, ונראה כאילו הוא ענה.
    # **כלי אבחון שמריץ תנאים אחרים מהמערכת גרוע מכלי שחסר.**
    window = job_server._SCAN_WINDOW_BY_SOURCE.get(src, job_server._SCAN_WINDOW)
    print(f'[gates] {src} asked with window {window}\n')

    rows, seen_urls = [], set()
    for role in job_server.SCHEDULED_ROLES:
        got = scraper(role, window) or []
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
    #
    # 14.11.2026, בבקשת שאול: "אתה צריך לעשות את הסריקה שם פעם ביום לא יותר
    # מזה, זה יוריד נפח".
    #
    # לוחות ה-ATS הם קטלוגים ולא פידים. עשרים ושבעה לוחות כפול ארבעה עשר
    # תפקידים, בשביל רשימה שזזה פעם בכמה ימים, בסריקה שכבר מוציאה חמש עשרה
    # מעשרים וחמש הדקות שלה. ומודעה שם יושבת פתוחה שבועות, ולכן עיכוב של עד
    # יממה אינו עולה כלום.
    #
    # הגבלת שעה ולא תדירות נפרדת: הסריקה מופעלת מבחוץ כל שעה, ואין לה מקום
    # לשמור מתי רצה לאחרונה.
    from datetime import datetime, timedelta, timezone
    hour = datetime.now(timezone(timedelta(hours=2))).hour
    # 24.11.2026: חלון של שעתיים ולא שעה אחת. הסריקה מופעלת מהמשימה
    # המתוזמנת כל כ-80 דקות, והריצות נחתו ב-06:30 וב-08:00 שעון ישראל, כלומר
    # אף אחת לא נפלה בשעה 7. המעבר היומי לא רץ מאז 16.11, ו-jobify (אינדיד,
    # ג'וב קרוב) שתק תשעה ימים עד שחדר המצב התריע. seen_jobs מונע כפילות
    # אם שתי ריצות נפלות בחלון.
    in_daily = job_server.DAILY_HOUR <= hour <= job_server.DAILY_HOUR + 1
    srcs = [s for s in job_server.SCHEDULED_SOURCES
            if s not in job_server.DAILY_SOURCES or in_daily]
    if in_daily:
        print(f'[notify] daily pass: {", ".join(job_server.DAILY_SOURCES)} included')

    job_server._run_notify_job(sources=srcs, always_notify=True)
