from getpass import getpass
from pathlib import Path
import secrets

from werkzeug.security import generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"

if env_path.exists():
    print(".env already exists.")
    raise SystemExit(0)

username = input("Admin username [admin]: ").strip() or "admin"
password = getpass("Create admin password: ")

if len(password) < 10:
    raise SystemExit("Admin password must be at least 10 characters.")

secret = secrets.token_urlsafe(48)
password_hash = generate_password_hash(password)

env_path.write_text(
    "\n".join(
        [
            f"SECRET_KEY={secret}",
            "APP_NAME=CampusPass",
            "APP_BASE_URL=http://127.0.0.1:5000",
            f"ADMIN_USERNAME={username}",
            f"ADMIN_PASSWORD_HASH={password_hash}",
            "ADMIN_PASSWORD=",
            "TICKET_MAX_AGE_SECONDS=2592000",
            "MAIL_MODE=demo",
            "RESEND_API_KEY=",
            "MAIL_FROM=onboarding@resend.dev",
            "COOKIE_SECURE=false",
            "FLASK_DEBUG=false",
            "HOST=127.0.0.1",
            "PORT=5000",
            "",
        ]
    ),
    encoding="utf-8",
)

print(".env created successfully.")
