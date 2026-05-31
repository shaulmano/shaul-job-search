import sys
sys.stdout.reconfigure(encoding='utf-8')

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from config import (
    GMAIL_ADDRESS, GMAIL_APP_PASSWORD, SENDER_NAME,
    SENDER_PHONE, SENDER_LINKEDIN, PDF_ATTACHMENT
)

EMAIL_SUBJECT = "Experienced QA & Program Manager - Open to New Opportunities"

EMAIL_BODY = """\
Hi {first_name},

I'm Shaul Mano, a Senior Program Manager and QA Leader with 25+ years of experience at companies like RSA and Symantec.

In my most recent role at Qmarkets, I reduced post-release production defects by 35% and managed end-to-end release cycles across all products. I've attached a short summary of that impact for your reference.

I'd love a 15-minute conversation if there's anything relevant at {company}.

Best,
Shaul Mano
{phone}
{linkedin}
"""

def send_test():
    to_address = GMAIL_ADDRESS
    first_name = "Shaul"
    company = "TEST COMPANY"

    msg = MIMEMultipart()
    msg["From"] = f"{SENDER_NAME} <{GMAIL_ADDRESS}>"
    msg["To"] = to_address
    msg["Subject"] = f"[TEST] {EMAIL_SUBJECT}"

    body = EMAIL_BODY.format(
        first_name=first_name,
        company=company,
        phone=SENDER_PHONE,
        linkedin=SENDER_LINKEDIN,
    )
    msg.attach(MIMEText(body, "plain"))

    if os.path.exists(PDF_ATTACHMENT):
        with open(PDF_ATTACHMENT, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(PDF_ATTACHMENT)}"',
        )
        msg.attach(part)
        print(f"Attachment: {os.path.basename(PDF_ATTACHMENT)}")
    else:
        print(f"WARNING: PDF not found at {PDF_ATTACHMENT}")

    print(f"Sending test email to {to_address}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, to_address, msg.as_string())

    print("Done! Check your inbox.")

if __name__ == "__main__":
    send_test()
