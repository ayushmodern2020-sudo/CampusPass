# CampusPass — Secure Campus Event Ticketing System

CampusPass is a Flask + SQLite event ticketing platform with separate student and organizer authentication, capacity-aware registration, signed QR tickets, protected ticket access, webcam check-in, and an organizer audit dashboard.

## Core flow

```text
/ 
|
+--> Student Login
|      |
|      +--> Create account
|      |
|      +--> Events
|             |
|             +--> Event details
|                    |
|                    +--> Reserve ticket
|                           |
|                           +--> Signed ticket token
|                           +--> QR code
|                           +--> Email preview / Resend
|                           +--> My Tickets
|
+--> Organizer Login
       |
       +--> Organizer Dashboard
              |
              +--> QR scanner
              +--> Manual token verification
              +--> Event statistics
              +--> Attendance CSV export
              +--> Security audit log
              +--> Create event
```

## Security model

Students cannot browse events or register before authenticating.

Student passwords are stored using Werkzeug password hashing. Login failures are throttled in-process to reduce repeated guessing.

Student and organizer sessions are separate. Session cookies are HttpOnly and SameSite=Lax, with Secure cookies available through `COOKIE_SECURE=true`.

POST, PUT, PATCH, and DELETE requests require a CSRF token. The organizer JSON check-in API accepts the CSRF token through `X-CSRF-Token`.

Organizer check-in is protected by the admin session. The old organizer PIN flow has been removed from the browser.

Ticket QR access is private. A student can access only their own ticket; an authenticated organizer can access tickets through organizer routes.

Ticket tokens are signed with `itsdangerous`, expire according to `TICKET_MAX_AGE_SECONDS`, and are also stored in the database as SHA-256 hashes rather than raw tokens.

Check-in is single-use. The ticket status update is atomic, and successful/duplicate/invalid scans are added to the audit log with the organizer username.

The project still accepts legacy `campus-ticket-v1` tokens so tickets created by the previous version can continue to be checked, provided the same `SECRET_KEY` is retained.

Email HTML escapes user/event fields before rendering to reduce HTML injection risk.

## Local setup

### 1. Create a virtual environment

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### 2. Create secure local configuration

The repository intentionally does not contain a real `.env`.

Run:

```powershell
python setup.py
```

Enter an organizer username and password when prompted. The script generates a random Flask `SECRET_KEY` and stores an `ADMIN_PASSWORD_HASH`.

For a manual setup, copy `.env.example` to `.env` and configure the same variables.

### 3. Start the app

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

The root route redirects unauthenticated users to Student Login.

## Demo workflow

### Student

1. Create a student account.
2. Sign in.
3. Browse the protected event dashboard.
4. Open an event.
5. Reserve a ticket.
6. Open the generated QR ticket.
7. Use My Tickets to reopen the QR later.
8. Test the protected email preview.

The default database seeds three demo events on first startup when the database is empty.

### Organizer

Open:

```text
http://127.0.0.1:5000/admin/login
```

Sign in with the organizer credentials created by `setup.py`.

From the organizer dashboard you can:

- Start the webcam QR scanner.
- Paste a ticket token for manual testing.
- See total students, tickets, check-ins, and events.
- Refresh live statistics for an event.
- Export event attendance as CSV.
- Review the latest security audit entries.
- Create new events.

### Check-in behavior

A valid token produces:

```text
CHECKED-IN
```

Scanning the same ticket again produces:

```text
ALREADY USED
```

Forged, malformed, mismatched, or expired tickets are rejected.

## Email

The default is:

```text
MAIL_MODE=demo
```

This creates a local HTML preview containing the QR image, so the project can be demonstrated without a mail provider.

For Resend, configure:

```text
MAIL_MODE=resend
RESEND_API_KEY=re_xxxxxxxxx
MAIL_FROM=your-verified-sender@example.com
```

## Database

SQLite is used for local reproducibility.

Tables:

- `events`
- `participants`
- `tickets`
- `checkin_audit`

The application automatically migrates the previous `participants`, `tickets`, and `checkin_audit` tables when the older database is present.

Generated QR images are stored under:

```text
data/qr/
```

Local email previews are stored under:

```text
.tmp/emails/
```

These generated/local files are excluded from Git.

## Testing

Install dependencies and run:

```powershell
pytest -q
```

The included tests cover:

- Root authentication gate.
- Student account registration.
- Protected event pages.
- Duplicate registration prevention.
- Admin authentication.
- CSRF-protected check-in.
- First check-in.
- Duplicate check-in.
- Forged token rejection.
- Private ticket QR access.

## Repository hygiene

Do not commit:

```text
.env
.venv/
data/app.db
data/qr/
.tmp/
```

A public repository should contain source code, templates, static files, tests, requirements, README, and `.env.example`, but never real credentials or a populated local database.

## Project structure

```text
WEB04_Event_Ticketing_System/
├── app.py
├── setup.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── run.ps1
├── run.bat
├── services/
│   ├── __init__.py
│   └── email_service.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── student_login.html
│   ├── student_register.html
│   ├── admin_login.html
│   ├── organizer.html
│   ├── create_event.html
│   ├── register.html
│   ├── my_tickets.html
│   ├── ticket.html
│   ├── success.html
│   └── error.html
├── static/
│   ├── style.css
│   ├── organizer.js
│   └── qr_placeholder.svg
├── tests/
│   └── test_app.py
└── data/
    └── .gitkeep
```

## UI direction

The frontend uses a campus-editorial visual language rather than a generic SaaS dashboard. Warm paper tones, dark ink, coral accents, serif display type, hard borders, ticket-stub details, asymmetric event cards, and a simple organizer control center keep the interface closer to a student event desk than a template-heavy admin panel.

See `FIGMA_DESIGN_GUIDE.md` for the visual tokens, layouts, components, and screen structure used for the redesign.
