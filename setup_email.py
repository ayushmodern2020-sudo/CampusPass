from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def read_env_lines():
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8").splitlines()
    return []


def set_env(lines, key, value):
    prefix = key + "="
    updated = False
    result = []
    for line in lines:
        if line.startswith(prefix):
            result.append(f"{key}={value}")
            updated = True
        else:
            result.append(line)
    if not updated:
        result.append(f"{key}={value}")
    return result


if not ENV_PATH.exists():
    raise SystemExit(".env was not found. Run setup.py first, then run setup_email.py.")

print("CampusPass Resend email setup")
print("Leave the current SECRET_KEY and admin settings unchanged.")
print()

api_key = input("Resend API key: ").strip()
if not api_key.startswith("re_"):
    raise SystemExit("That does not look like a Resend API key. It should start with re_.")

mail_from = input(
    "Verified sender email [tickets@your-verified-domain.com]: "
).strip()
if not mail_from:
    mail_from = "tickets@your-verified-domain.com"

reply_to = input("Reply-to email (optional): ").strip()

lines = read_env_lines()
lines = set_env(lines, "MAIL_MODE", "resend")
lines = set_env(lines, "RESEND_API_KEY", api_key)
lines = set_env(lines, "MAIL_FROM", mail_from)

if reply_to:
    lines = set_env(lines, "MAIL_REPLY_TO", reply_to)
else:
    lines = set_env(lines, "MAIL_REPLY_TO", "")

ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

print()
print("Email configuration saved to .env")
print("MAIL_MODE=resend")
print(f"MAIL_FROM={mail_from}")
print()
print("Next: run `python send_test_email.py your-email@example.com` to verify delivery.")
