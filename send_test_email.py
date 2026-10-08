import html
import os
import sys

import resend
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("RESEND_API_KEY", "").strip()
mail_from = os.getenv("MAIL_FROM", "").strip()
mode = os.getenv("MAIL_MODE", "demo").strip().lower()

if mode != "resend":
    raise SystemExit("MAIL_MODE is not set to resend. Run setup_email.py first.")

if not api_key:
    raise SystemExit("RESEND_API_KEY is missing from .env.")

if not mail_from:
    raise SystemExit("MAIL_FROM is missing from .env.")

recipient = sys.argv[1].strip() if len(sys.argv) > 1 else input("Send test email to: ").strip()
if not recipient or "@" not in recipient:
    raise SystemExit("Enter a valid recipient email address.")

resend.api_key = api_key
safe_recipient = html.escape(recipient)
params = {
    "from": mail_from,
    "to": [recipient],
    "subject": "CampusPass email delivery test",
    "html": f"""
    <!doctype html>
    <html>
    <body style=\"font-family:Arial,sans-serif;background:#f4f7fb;padding:30px\">
      <div style=\"max-width:560px;margin:auto;background:#fff;border-radius:16px;padding:28px;border:1px solid #e5e7eb\">
        <h1 style=\"margin-top:0\">CampusPass</h1>
        <p>Email delivery is working correctly.</p>
        <p>This test message was sent to <strong>{safe_recipient}</strong> using Resend.</p>
        <p style=\"color:#64748b\">You can now book a ticket and the student's ticket email will be sent automatically.</p>
      </div>
    </body>
    </html>
    """,
    "text": "CampusPass email delivery is working correctly. You can now book a ticket and the student's ticket email will be sent automatically.",
}

try:
    response = resend.Emails.send(params)
except Exception as exc:
    raise SystemExit(f"Email send failed: {exc}") from exc

print("Email request accepted by Resend.")
print(response)
