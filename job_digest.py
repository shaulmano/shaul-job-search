import requests
import smtplib
import time
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

sys.path.insert(0, r'C:\Users\Shaul\Documents\job-search')
from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD

# ===== שנה כאן לפי הצורך =====
import os
APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '')
APIFY_ACTOR = "apify~rag-web-browser"

AREAS = ["תל אביב", "רמת גן", "חולון", "הוד השרון", "הרצליה", "כפר סבא"]
MIN_SCORE = 7
MAX_JOBS = 10
# ==============================

TITLE_KEYWORDS = [
    "program manager", "programme manager",
    "release manager", "release management",
    "delivery manager", "head of delivery",
    "project manager", "project management",
    "it manager", "operations manager",
    "מנהל פרויקטים", "מנהל תוכנית", "מנהל שחרורים", "מנהל delivery",
]

SKILLS_KEYWORDS = [
    "jira", "agile", "scrum", "monday.com", "monday",
    "jenkins", "ci/cd", "github", "okr", "kpi",
    "release", "delivery", "sprint", "roadmap",
    "python", "r&d", "stakeholder", "cross-functional",
    "eazybi", "svn", "azure",
]

NEGATIVE_KEYWORDS = [
    "junior", "entry level", "graduate", "intern", "student",
    "sales", "account manager", "marketing",
    "ג'וניור", "התמחות", "סטודנט", "מכירות",
]

AREAS_EN = ["tel aviv", "ramat gan", "holon", "herzliya", "kfar saba", "hod hasharon", "israel"]
AREAS_HE = ["תל אביב", "רמת גן", "חולון", "הרצליה", "כפר סבא", "הוד השרון"]


def build_queries():
    return [
        '"Program Manager" Israel "Tel Aviv" OR "Ramat Gan" OR "Herzliya" site:linkedin.com/jobs',
        '"Release Manager" Israel "Tel Aviv" OR "Herzliya" site:linkedin.com/jobs',
        '"Delivery Manager" OR "Head of Delivery" Israel Agile Jira site:linkedin.com/jobs',
        '"Project Manager" software R&D Israel "Tel Aviv" site:linkedin.com/jobs',
        '"מנהל פרויקטים" OR "מנהל תוכנית" "תל אביב" OR "רמת גן" OR "הרצליה" site:drushim.co.il',
        '"Program Manager" OR "Release Manager" OR "מנהל פרויקטים" site:alljobs.co.il',
    ]


def score_job(title, description):
    title_l = title.lower()
    desc_l = (description or "").lower()
    combined = title_l + " " + desc_l
    score = 0

    # Title match (up to 5 points)
    for kw in TITLE_KEYWORDS:
        if kw in title_l:
            score += 5
            break

    # Skills from CV (up to 3 points)
    hits = sum(1 for k in SKILLS_KEYWORDS if k in combined)
    score += min(hits, 3)

    # Location match (+1)
    if any(a in combined for a in AREAS_EN + [a.lower() for a in AREAS_HE]):
        score += 1

    # Seniority bonus (+1)
    if any(k in combined for k in ["senior", "head", "director", "vp", "lead", "בכיר"]):
        score += 1

    # Negative penalty
    if any(k in combined for k in NEGATIVE_KEYWORDS):
        score -= 3

    return max(0, min(score, 10))


def clean_url(url):
    return url.split("?")[0] if "linkedin.com" in url else url


def parse_title_and_company(title, url):
    # Common formats: "Job Title - Company - Location" or "Job Title | Company"
    for sep in [" - ", " | ", " – "]:
        parts = title.split(sep)
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
    return title.strip(), "—"


def run_apify_query(query):
    r = requests.post(
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/runs",
        headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
        json={"query": query, "maxResults": 5, "outputFormats": ["markdown"]},
        timeout=30,
    )
    r.raise_for_status()
    run_id = r.json()["data"]["id"]

    for _ in range(60):
        time.sleep(10)
        s = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
            timeout=30,
        ).json()["data"]
        if s["status"] == "SUCCEEDED":
            break
        if s["status"] in ("FAILED", "ABORTED", "TIMED-OUT"):
            return []

    items = requests.get(
        f"https://api.apify.com/v2/datasets/{s['defaultDatasetId']}/items",
        headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
        timeout=30,
    ).json()
    return items


SKIP_URLS = [
    "linkedin.com/in/", "linkedin.com/pub/",
    "facebook.com", "twitter.com", "instagram.com",
    "wikipedia.org", "glassdoor.com/member",
]


def collect_jobs():
    queries = build_queries()
    seen_urls = set()
    jobs = []

    for i, query in enumerate(queries):
        print(f"Query {i+1}/{len(queries)}")
        for item in run_apify_query(query):
            sr = item.get("searchResult", {})
            raw_title = sr.get("title", "").strip()
            description = sr.get("description", "").strip()
            url = clean_url(sr.get("url", ""))

            if not raw_title or not url:
                continue
            if url in seen_urls:
                continue
            if any(p in url for p in SKIP_URLS):
                continue

            job_title, company = parse_title_and_company(raw_title, url)
            score = score_job(raw_title, description)
            if score < MIN_SCORE:
                continue

            seen_urls.add(url)
            source = (
                "LinkedIn" if "linkedin.com" in url
                else "drushim.co.il" if "drushim" in url
                else "alljobs.co.il" if "alljobs" in url
                else "Google"
            )
            jobs.append({
                "title": job_title,
                "company": company,
                "description": description,
                "url": url,
                "score": score,
                "source": source,
            })

    jobs.sort(key=lambda x: x["score"], reverse=True)
    return jobs[:MAX_JOBS]


def build_email_html(jobs, date_str):
    areas_str = " / ".join(AREAS)

    if not jobs:
        body = "<p>לא נמצאו משרות מתאימות ב-24 השעות האחרונות (ציון 7+).</p>"
    else:
        rows = ""
        for j in jobs:
            desc = j["description"][:120] + "..." if len(j["description"]) > 120 else j["description"]
            score_color = "#27ae60" if j["score"] >= 8 else "#e67e22"
            rows += f"""
            <tr>
              <td><a href="{j['url']}">{j['title']}</a></td>
              <td>{j['company']}</td>
              <td>{j['source']}</td>
              <td style="text-align:center;font-weight:bold;color:{score_color}">{j['score']}/10</td>
              <td style="font-size:12px;color:#666">{desc}</td>
            </tr>"""

        body = f"""
        <table border="0" cellpadding="8" cellspacing="0" width="100%">
          <thead>
            <tr style="background:#2c3e50;color:white;">
              <th>תפקיד</th><th>חברה</th><th>מקור</th><th>ציון</th><th>תיאור קצר</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
  <meta charset="utf-8">
  <style>
    body{{font-family:Arial,sans-serif;direction:rtl;padding:24px;color:#333;max-width:950px;}}
    h2{{color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px;}}
    .meta{{color:#7f8c8d;font-size:13px;margin-bottom:20px;}}
    table{{border-collapse:collapse;width:100%;}}
    th{{padding:10px 12px;text-align:right;}}
    td{{padding:8px 12px;border-bottom:1px solid #eee;vertical-align:top;}}
    tr:nth-child(even){{background:#f9f9f9;}}
    a{{color:#2980b9;text-decoration:none;}}
    a:hover{{text-decoration:underline;}}
  </style>
</head>
<body>
  <h2>משרות Program Manager / Release Manager - {date_str}</h2>
  <p class="meta">אזורים: {areas_str} &nbsp;|&nbsp; 24 שעות אחרונות &nbsp;|&nbsp; נמצאו: {len(jobs)} משרות (ציון {MIN_SCORE}+)</p>
  {body}
</body>
</html>"""


def send_email(html_content, date_str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"PM / Release Manager Jobs - {date_str}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)
    print(f"Email sent to {GMAIL_ADDRESS}")


def send_error_email(error_msg, date_str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Digest ERROR - {date_str}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS
    msg.attach(MIMEText(f"<pre>{error_msg}</pre>", "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def main():
    date_str = datetime.now().strftime("%d/%m/%Y")
    print(f"=== Job Digest {date_str} ===")
    try:
        jobs = collect_jobs()
        print(f"Found {len(jobs)} jobs")
        html = build_email_html(jobs, date_str)
        send_email(html, date_str)
    except Exception as e:
        print(f"Error: {e}")
        try:
            send_error_email(str(e), date_str)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
