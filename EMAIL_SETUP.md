# CampusPass actual email setup

CampusPass already calls the email service automatically after a successful ticket booking. The default `MAIL_MODE=demo` creates a local preview. To send real email, switch the app to Resend mode.

## 1. Create a Resend API key

Create a Resend account and an API key from the Resend dashboard. Keep the key private; it belongs in `.env`, which is excluded from Git.

Resend's Python SDK uses `resend.api_key` and `resend.Emails.send(...)` for sending email. Resend also supports inline images using CID attachments, which CampusPass uses for the QR code.

## 2. Verify a sender domain

For real student recipients, configure a sender address on a domain verified in Resend, for example:

```text
CampusPass <tickets@example.com>
```

The `onboarding@resend.dev` sender shown in Resend's quickstart is suitable for testing; use a verified sender for normal application delivery.

## 3. Configure CampusPass automatically

From the project folder run:

```powershell
python setup_email.py
```

Enter the API key and the verified sender address. The script updates only these email settings in `.env` and preserves your existing secret key, admin credentials, and database settings.

## 4. Test email delivery before booking

```powershell
python send_test_email.py your-email@example.com
```

A successful response means Resend accepted the email request. Check the recipient inbox and the Resend dashboard logs.

## 5. Run CampusPass

```powershell
python app.py
```

Now the normal booking flow sends the ticket email automatically:

```text
Student Login
    -> Event
    -> Reserve Ticket
    -> Ticket + QR generated
    -> Resend
    -> Student inbox
```

The QR is embedded in the HTML email and is also attached as an inline image. The existing local email preview remains available for development.

## Important

Never commit `.env` or expose `RESEND_API_KEY` in GitHub, screenshots, README files, or frontend JavaScript.
