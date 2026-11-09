"""מוציא מ-seen_jobs משרות של מקור אחד שנסרקו, נפסלו, ולא דווחו מעולם.

‏9.11.2026: הסריקה רושמת ב-seen_jobs כל כתובת שנסרקה, גם אחת שנפסלה בשער.
המשמעות היא ששינוי במסנן לא חל לאחור: אחרי שחלון הגיל של דרושים נפתח
ל-14 יום, 892 משרות שנפסלו קודם נשארו מסומנות כנראו ולא היו מגיעות לשאול
לעולם. 83 הן כל מה שדרושים תרם אי פעם, מול 975 שנסרקו.

מה שכן דווח, כלומר מה שרשום ב-jobs.jsonl, נשאר ב-seen_jobs. לכן אין פה
סיכון להתראה כפולה.

בלי שום תלות חיצונית בכוונה: run_notify.py מייבא את job_server, שדורש
requests, ואין שום סיבה להתקין דפדפן וספריות רשת בשביל עריכה של קובץ JSON.

    python unsee.py drushim.co.il
"""
import json
import sys


def main():
    needle = sys.argv[1] if len(sys.argv) > 1 else ''
    if not needle:
        raise SystemExit('usage: python unsee.py <substring of the url>')

    with open('seen_jobs.json', encoding='utf-8') as fh:
        seen = json.load(fh)
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
    for url in sorted(drop)[:5]:
        print(f'  {url}')
    if not drop:
        return
    with open('seen_jobs.json', 'w', encoding='utf-8') as fh:
        json.dump(sorted(kept), fh, ensure_ascii=False)
    print('[unsee] seen_jobs.json rewritten')


if __name__ == '__main__':
    main()
