"""מוצא לוחות ATS של חברות ישראליות שאינם ברשימות שלנו.

‏14.11.2026. שאול שלח קישור למשרת Technical Project Manager ב-Alteva RCM
ושאל למה לא מצאנו אותה. התשובה: `altevarcm` לא היה ברשימת הלוחות, ולכן
מעולם לא הסתכלנו שם. אחר כך אמר "אני בטוח שיש עוד", וצדק.

‏**ההיסטוריה שבקוד מסבירה למה.** הערת הקוד ליד GREENHOUSE_BOARDS אומרת
שב-9.9.2026 נוסו 96 שמות של חברות ישראליות מול ה-API ו-25 ענו. זאת כל
השיטה שהייתה כאן אי פעם, והיא נעצרה אחרי 96 ניסיונות. יש מאות חברות
ישראליות על Greenhouse.

**מה שמאפשר את זה: בדיקת טוקן היא קריאה אחת זולה.** טוקן שגוי מחזיר 404
מיד, ולכן אפשר לנסות מאות מועמדים בדקות. זה לא גירוד ולא עקיפה של שום
דבר, אלה אותם עמודי קריירה ציבוריים שהמערכת כבר קוראת.

    python discover_ats.py                  # כל המועמדים שבקובץ
    python discover_ats.py acme foo bar     # שמות נוספים מהשורה

הפלט מדפיס רק את מי שענה, עם כמה משרות יש לו וכמה מהן בישראל, ובסוף שורה
מוכנה להדבקה לתוך GREENHOUSE_BOARDS. **מה שלא ענה לא מודפס**, כי רשימה של
ארבע מאות כישלונות אינה מידע.
"""
import concurrent.futures
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ISRAEL = ('israel', 'tel aviv', 'tel-aviv', 'herzliya', 'raanana', "ra'anana",
          'haifa', 'jerusalem', 'netanya', 'petah', 'rehovot', 'beer sheva',
          'yokneam', 'caesarea', 'ramat gan', 'hod hasharon', 'kfar saba',
          'remote')


def get(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'situation-room/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def _il(rows, loc_of):
    return sum(1 for r in rows if any(c in (loc_of(r) or '').lower() for c in ISRAEL))


def try_greenhouse(tok):
    rows = get(f'https://boards-api.greenhouse.io/v1/boards/{tok}/jobs').get('jobs') or []
    return len(rows), _il(rows, lambda r: (r.get('location') or {}).get('name'))


def try_lever(tok):
    rows = get(f'https://api.lever.co/v0/postings/{tok}?mode=json')
    if not isinstance(rows, list):
        raise ValueError('not a list')
    return len(rows), _il(rows, lambda r: (r.get('categories') or {}).get('location'))


def try_ashby(tok):
    rows = get(f'https://api.ashbyhq.com/posting-api/job-board/{tok}').get('jobs') or []
    return len(rows), _il(rows, lambda r: r.get('location'))


def try_smartrecruiters(tok):
    rows = get(
        f'https://api.smartrecruiters.com/v1/companies/{tok}/postings?limit=100'
    ).get('content') or []
    return len(rows), _il(rows, lambda r: '%s %s' % ((r.get('location') or {}).get('city', ''),
                                                     (r.get('location') or {}).get('country', '')))


PLATFORMS = [('greenhouse', try_greenhouse), ('lever', try_lever),
             ('ashby', try_ashby), ('smartrecruiters', try_smartrecruiters)]


def slugs(name):
    """צורות הכתיב שחברה עשויה להשתמש בהן כטוקן.

    הטוקן אינו שם החברה, וזה מה שהכשיל שלושים ניחושים ב-14.11: רוב החברות
    כותבות את השם בלי רווחים ובלי מקפים, אבל לא כולן. שלוש צורות לכל שם
    עולות שלוש קריאות ומכסות כמעט את הכל.
    """
    base = re.sub(r'[^a-z0-9 ]', '', name.lower()).strip()
    if not base:
        return []
    flat = base.replace(' ', '')
    dash = base.replace(' ', '-')
    out = [flat]
    if dash != flat:
        out.append(dash)
    first = base.split()[0]
    if first != flat:
        out.append(first)
    return out


# מועמדים: חברות הייטק ישראליות. השם נכתב כאן כמו שמדברים עליו, ו-slugs
# מייצר ממנו את צורות הטוקן. מה שכבר ברשימות של job_server אינו צריך להיות
# כאן, אבל גם לא מזיק: הסקריפט מסמן אותו כידוע.
CANDIDATES = """
Wiz Snyk Gong WalkMe Claroty HiBob Rapyd Verbit Placer Next Insurance Tipalti
Kaltura Cellebrite Playtika Aqua Security Checkmarx CyberArk Pentera Coralogix
Logz Vast Data Run AI Papaya Global At Bay Silverfort Cyera Upwind Guardio
Monday Fiverr Wix Lemonade Hippo Honeybook Moon Active Finout Armis Perion
Unity IronSource Outbrain Teads Minute Media Sisense Anodot Bizzabo Trax
Zenity Grip Security Noname Security Salt Security Piiano Granulate Dream
Security Island Datarails Alteva RCM Deel Navan Rivery Explorium Deci
Databand Firebolt Imubit Augury Bringg Riskified BigID Lightricks Lightrun
Cybereason Cato Networks Similarweb NICE JFrog Taboola Payoneer AppsFlyer Via
Fireblocks Transmit Security Forter Melio Axonius Torq Yotpo Cymulate
SafeBreach Orca Security Descope Immunefi Blink Ops Spectral Jit Oligo
Security Apiiro Legit Security Cycode Cyberint Silk Security Seemplicity
Opus Security Sweet Security Miggo Zest Security Tenable Radware Imperva
Varonis Check Point Sentinel One Semperis Illusive Cynet Deep Instinct
Perception Point Votiro Odix Morphisec Guardicore Ermetic Laminar Dig Security
Polar Security Satori Cyber Immuta Velotix BigPanda Logicmonitor Lightspin
Vulcan Cyber Rezilion Scribe Security Chainguard Snyk Labs Codefresh Spot io
Granulate Zesty Finout Anodot Cloudinary Cloudshare Spotinst Salto Rookout
Epsagon Aporia Deepchecks Qwak Superwise Datagen Datomize Synthesis AI Tabnine
Codium Mobileye Innoviz AEye Arbe Valens Autotalks Foretellix Cognata
Upstream Security C2A Security Argus Cyber Karamba Security GuardKnox
Riskified Forter Signifyd Bluevine Fundbox Behalf Credorax Earnix Personetics
Pagaya Lemonade Hippo Next Insurance Vesttoo Kovrr Cytora Novidea Sapiens
Earnix Zoomd AppsFlyer Singular Bidalgo Zoomd Taptica Tremor Digital Turbine
Verve Moburst Playtika Plarium SciPlay Papaya Gaming Huuuge Jelly Button
Crazy Labs Tabtale Zynga Israel Moon Active Candivore Playstudios Lucky Day
Fiverr Upwork Israel Riseup Honeybook Melio Tipalti Trullion Datarails Fyle
Expensify Israel Papaya Global HiBob Hibob Gloat Workey Joonko Comeet
Compete Equitybee Carta Israel Vestd Pave Compensation
"""


def main():
    names = sys.argv[1:] or CANDIDATES.split()
    # שם של שתי מילים נשבר כאן לשתי שורות, ולכן המועמדים נבנים גם מצמדים
    # עוקבים. "Next Insurance" הוא nextinsurance, ו-"Next" לבדו יקבל סיכוי
    # נפרד ממילא.
    cands = set()
    for i, n in enumerate(names):
        cands.update(slugs(n))
        if i + 1 < len(names):
            cands.update(slugs(n + ' ' + names[i + 1]))
    cands = sorted(c for c in cands if len(c) > 2)

    try:
        import job_server
        known = {('greenhouse', t) for t in job_server.GREENHOUSE_BOARDS}
        known |= {('lever', t) for t in job_server.LEVER_BOARDS}
        known |= {('ashby', t) for t in job_server.ASHBY_BOARDS}
        known |= {('smartrecruiters', t) for t in job_server.SMARTRECRUITERS_BOARDS}
    except Exception:
        known = set()

    print(f'trying {len(cands)} tokens on {len(PLATFORMS)} platforms '
          f'= {len(cands) * len(PLATFORMS)} requests\n')

    work = [(p, fn, t) for p, fn in PLATFORMS for t in cands]

    def probe(item):
        platform, fn, tok = item
        try:
            total, il = fn(tok)
        except Exception:
            return None
        return platform, tok, total, il

    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for res in ex.map(probe, work):
            if res:
                found.append(res)

    for platform, _ in PLATFORMS:
        rows = sorted((r for r in found if r[0] == platform),
                      key=lambda r: -r[3])
        new = [r for r in rows if (platform, r[1]) not in known]
        print(f'== {platform}: {len(rows)} answered, {len(new)} of them new ==')
        for _, tok, total, il in rows:
            mark = '      ' if (platform, tok) in known else 'NEW   '
            print(f'  {mark}{tok:<24} {total:>4} postings, {il:>3} in Israel')
        if new:
            # רק מי שיש לו משרות בישראל שווה הוספה. לוח אמיתי בלי משרות פה
            # הוא חברה שאינה מגייסת בישראל, והוא עולה קריאה בכל סריקה.
            worth = [t for _, t, _, il in new if il]
            if worth:
                print(f'\n  להוספה ל-{platform}:')
                print('  ' + ', '.join(f"'{t}'" for t in sorted(worth)))
        print()


if __name__ == '__main__':
    main()
