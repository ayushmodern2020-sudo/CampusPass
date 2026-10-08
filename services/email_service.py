import base64
import html
import os
import re
from pathlib import Path

import resend


def build_ticket_email(ticket, app_name):
    app_name = html.escape(str(app_name))
    participant_name = html.escape(str(ticket["participant_name"]))
    event_name = html.escape(str(ticket["event_name"]))
    venue = html.escape(str(ticket["venue"]))
    event_date = html.escape(str(ticket["event_date"]))
    ticket_id = int(ticket["id"])

    return f"""
<!doctype html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#172033">
<div style="max-width:620px;margin:30px auto;background:#fff;border-radius:18px;overflow:hidden;border:1px solid #e4e9f1">
<div style="padding:28px;background:#172554;color:#fff"><h1 style="margin:0;font-size:28px">{app_name}</h1><p style="margin:8px 0 0;color:#dbeafe">Your digital event ticket</p></div>
<div style="padding:30px">
<h2 style="margin-top:0">You're registered, {participant_name}!</h2>
<p>Your ticket for <strong>{event_name}</strong> has been confirmed.</p>
<div style="background:#f8fafc;border-radius:14px;padding:20px;margin:24px 0">
<p><strong>Venue:</strong> {venue}</p>
<p><strong>Date:</strong> {event_date}</p>
<p><strong>Ticket ID:</strong> #{ticket_id}</p>
</div>
<p style="text-align:center"><img src="cid:ticket-qr-{ticket_id}" alt="Ticket QR code" width="240" height="240" style="display:inline-block;border:10px solid #fff"></p>
<p style="text-align:center;color:#64748b">Present this QR code at the organizer check-in desk.</p>
</div>
<div style="padding:18px 30px;background:#f8fafc;color:#64748b;font-size:13px">This ticket is cryptographically signed and verified by the organizer portal.</div>
</div>
</body>
</html>
"""


def send_ticket_email(to_email, subject, html_body, qr_path: Path, app_base_url: str, ticket_id: int):
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    mail_from = os.getenv("MAIL_FROM", "").strip()
    reply_to = os.getenv("MAIL_REPLY_TO", "").strip()
    mode = os.getenv("MAIL_MODE", "demo").strip().lower()

    preview_dir = Path(__file__).resolve().parents[1] / ".tmp" / "emails"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"ticket-{ticket_id}.html"

    qr_bytes = qr_path.read_bytes()
    qr_b64 = base64.b64encode(qr_bytes).decode("ascii")
    preview_html = html_body.replace(
        f"cid:ticket-qr-{ticket_id}",
        f"data:image/png;base64,{qr_b64}",
    )
    preview_path.write_text(preview_html, encoding="utf-8")

    if mode == "demo":
        return {
            "mode": "demo",
            "message": "Email preview created locally.",
            "preview_path": str(preview_path),
            "provider": "Demo mode is active.",
        }

    if mode != "resend":
        return {
            "mode": "error",
            "message": "Email delivery is disabled by MAIL_MODE.",
            "provider": "Set MAIL_MODE=resend to enable delivery.",
            "preview_path": str(preview_path),
        }

    if not api_key:
        return {
            "mode": "error",
            "message": "Email could not be sent because RESEND_API_KEY is missing.",
            "provider": "Configure Resend in .env.",
            "preview_path": str(preview_path),
        }

    if not mail_from:
        return {
            "mode": "error",
            "message": "Email could not be sent because MAIL_FROM is missing.",
            "provider": "Set MAIL_FROM to a valid sender address.",
            "preview_path": str(preview_path),
        }

    clean_subject = re.sub(r"[\r\n]+", " ", str(subject)).strip()
    params = {
        "from": mail_from,
        "to": [str(to_email).strip()],
        "subject": clean_subject,
        "html": html_body,
        "text": (
            f"Your ticket for the event is confirmed. Ticket #{ticket_id}. "
            "Present the QR code from this email at the organizer check-in desk."
        ),
        "attachments": [
            {
                "filename": f"ticket-{ticket_id}.png",
                "content": base64.b64encode(qr_bytes).decode("ascii"),
                "content_id": f"ticket-qr-{ticket_id}",
                "content_type": "image/png",
            }
        ],
    }

    if reply_to:
        params["reply_to"] = [reply_to]

    try:
        resend.api_key = api_key
        response = resend.Emails.send(params)
        return {
            "mode": "resend",
            "message": "Ticket email sent successfully.",
            "provider": "Resend",
            "response": str(response),
        }
    except Exception as exc:
        return {
            "mode": "error",
            "message": "Email delivery failed. The local preview is still available.",
            "provider": "Resend",
            "preview_path": str(preview_path),
            "error": str(exc),
        }
