import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

import qrcode
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from services.email_service import build_ticket_email, send_ticket_email

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "app.db"
QR_DIR = BASE_DIR / "data" / "qr"
EVENT_IMAGE_DIR = BASE_DIR / "data" / "event_images"
EMAIL_DIR = BASE_DIR / ".tmp" / "emails"

QR_DIR.mkdir(parents=True, exist_ok=True)
EVENT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
EMAIL_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

secret_key = os.getenv("SECRET_KEY", "").strip()
if not secret_key:
    raise RuntimeError("SECRET_KEY is not configured")

app.config.update(
    SECRET_KEY=secret_key,
    APP_NAME=os.getenv("APP_NAME", "CampusPass").strip() or "CampusPass",
    APP_BASE_URL=os.getenv("APP_BASE_URL", "http://127.0.0.1:5000").strip(),
    TICKET_MAX_AGE_SECONDS=int(os.getenv("TICKET_MAX_AGE_SECONDS", "2592000")),
    ADMIN_USERNAME=os.getenv("ADMIN_USERNAME", "admin").strip() or "admin",
    ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", ""),
    ADMIN_PASSWORD_HASH=os.getenv("ADMIN_PASSWORD_HASH", ""),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

if not app.config["ADMIN_PASSWORD"] and not app.config["ADMIN_PASSWORD_HASH"]:
    raise RuntimeError("ADMIN_PASSWORD or ADMIN_PASSWORD_HASH is not configured")

serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
login_failures = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300

EVENT_IMAGE_BY_ID = {
    1: "https://images.unsplash.com/photo-1540575467063-178a50c2df87?auto=format&fit=crop&w=1200&q=82",
    2: "https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1200&q=82",
    3: "https://images.unsplash.com/photo-1563013544-824ae1b704d3?auto=format&fit=crop&w=1200&q=82",
    4: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1200&q=82",
    5: "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=1200&q=82",
    6: "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=82",
}

EVENT_IMAGE_DEFAULT = "https://images.unsplash.com/photo-1556761175-b413da4baf72?auto=format&fit=crop&w=1200&q=82"
ALLOWED_EVENT_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_EVENT_IMAGE_BYTES = 5 * 1024 * 1024

def valid_event_image_bytes(image):
    header = image.stream.read(16)
    image.stream.seek(0)
    return (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or (header[:4] == b"RIFF" and header[8:12] == b"WEBP")
    )


def event_image_url(name, event_id=None, image_path=None):
    if image_path:
        return url_for("event_image", filename=image_path)
    if event_id in EVENT_IMAGE_BY_ID:
        return EVENT_IMAGE_BY_ID[event_id]
    value = (name or "").lower()
    keyword_images = [
        (("cyber", "security"), "https://images.unsplash.com/photo-1563013544-824ae1b704d3?auto=format&fit=crop&w=1200&q=82"),
        (("robot",), "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?auto=format&fit=crop&w=1200&q=82"),
        (("hackathon", "coding", "programming"), "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=1200&q=82"),
        (("ai", "artificial intelligence"), "https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1200&q=82"),
        (("tech", "technology"), "https://images.unsplash.com/photo-1540575467063-178a50c2df87?auto=format&fit=crop&w=1200&q=82"),
    ]
    for keywords, image in keyword_images:
        if any(keyword in value for keyword in keywords):
            return image
    return EVENT_IMAGE_DEFAULT


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = csrf_token


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self)"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://unpkg.com; "
        "style-src 'self'; "
        "img-src 'self' data: https://images.unsplash.com; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "media-src 'self' blob:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    return response


@app.before_request
def protect_state_changing_requests():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    expected = session.get("_csrf_token", "")
    provided = request.headers.get("X-CSRF-Token", "")

    if request.form:
        provided = request.form.get("_csrf_token", provided)

    if not expected or not provided or not hmac.compare_digest(expected, provided):
        if request.path.startswith("/api/"):
            return jsonify({
                "status": "CSRF FAILED",
                "message": "Security token validation failed."
            }), 400
        return render_template(
            "error.html",
            title="Security check failed",
            message="This form expired or was submitted without a valid security token."
        ), 400

    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("admin_authenticated") is not True:
            if request.path.startswith("/api/"):
                return jsonify({
                    "status": "UNAUTHORIZED",
                    "message": "Organizer authentication required."
                }), 401
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("student_id"):
            return redirect(url_for("student_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def verify_admin_password(password):
    configured_hash = app.config["ADMIN_PASSWORD_HASH"]
    if configured_hash:
        try:
            return check_password_hash(configured_hash, password)
        except ValueError:
            return False
    return hmac.compare_digest(str(password), str(app.config["ADMIN_PASSWORD"]))


def clean_next_url(value):
    value = (value or "").strip()
    if not value:
        return ""

    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return ""

    if not value.startswith("/") or value.startswith("//"):
        return ""

    return value


def login_key(email):
    return f"{request.remote_addr or 'unknown'}|{email}"


def login_limited(key):
    now = time.monotonic()
    attempts = [stamp for stamp in login_failures.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
    login_failures[key] = attempts
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def record_login_failure(key):
    now = time.monotonic()
    attempts = [stamp for stamp in login_failures.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
    attempts.append(now)
    login_failures[key] = attempts


def clear_login_failures(key):
    login_failures.pop(key, None)


def password_is_strong(password):
    return (
        len(password) >= 8
        and bool(re.search(r"[A-Z]", password))
        and bool(re.search(r"[a-z]", password))
        and bool(re.search(r"\d", password))
    )


def valid_email(email):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


def init_db():
    connection = db()

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            venue TEXT NOT NULL,
            event_date TEXT NOT NULL,
            capacity INTEGER NOT NULL CHECK(capacity > 0),
            created_at TEXT NOT NULL,
            image_path TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(name, email)
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            token_created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ISSUED'
                CHECK(status IN ('ISSUED','CHECKED-IN')),
            checked_in_at TEXT,
            checked_in_by TEXT,
            FOREIGN KEY(event_id) REFERENCES events(id),
            FOREIGN KEY(participant_id) REFERENCES participants(id)
        );

        CREATE TABLE IF NOT EXISTS checkin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            event_id INTEGER,
            participant_name TEXT,
            admin_username TEXT,
            scanned_at TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(event_id) REFERENCES events(id)
        );

        CREATE INDEX IF NOT EXISTS idx_tickets_event_id
            ON tickets(event_id);

        CREATE INDEX IF NOT EXISTS idx_tickets_participant_id
            ON tickets(participant_id);

        CREATE INDEX IF NOT EXISTS idx_tickets_token_hash
            ON tickets(token_hash);

        CREATE INDEX IF NOT EXISTS idx_audit_event_id
            ON checkin_audit(event_id);

        CREATE INDEX IF NOT EXISTS idx_audit_scanned_at
            ON checkin_audit(scanned_at);
        """
    )

    participant_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(participants)").fetchall()
    }

    if "password_hash" not in participant_columns:
        connection.execute("ALTER TABLE participants ADD COLUMN password_hash TEXT")

    ticket_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(tickets)").fetchall()
    }

    if "checked_in_by" not in ticket_columns:
        connection.execute("ALTER TABLE tickets ADD COLUMN checked_in_by TEXT")

    audit_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(checkin_audit)").fetchall()
    }

    if "admin_username" not in audit_columns:
        connection.execute("ALTER TABLE checkin_audit ADD COLUMN admin_username TEXT")

    event_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(events)").fetchall()
    }
    if "image_path" not in event_columns:
        connection.execute("ALTER TABLE events ADD COLUMN image_path TEXT")
    if "is_active" not in event_columns:
        connection.execute("ALTER TABLE events ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_email_lower
        ON participants(lower(email))
        """
    )

    count = connection.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]

    if count == 0:
        created = now_iso()
        connection.executemany(
            """
            INSERT INTO events(
                name,
                description,
                venue,
                event_date,
                capacity,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "TechFest 2026",
                    "Campus technology showcase with projects, demos and student talks.",
                    "Technology Block Auditorium",
                    "2026-10-15 10:00 AM",
                    120,
                    created,
                ),
                (
                    "AI & Web Night",
                    "Evening meetup featuring student-built AI and web applications.",
                    "Innovation Lab",
                    "2026-10-18 04:30 PM",
                    80,
                    created,
                ),
                (
                    "Cyber Security Workshop",
                    "Hands-on session on secure coding, authentication and web application security.",
                    "Digital Learning Center",
                    "2026-10-22 02:00 PM",
                    100,
                    created,
                ),
            ],
        )

    connection.commit()
    connection.close()


def capacity_for_event(connection, event_id):
    event = connection.execute(
        "SELECT * FROM events WHERE id = ? AND is_active = 1",
        (event_id,),
    ).fetchone()

    if not event:
        return None, None

    registered = connection.execute(
        "SELECT COUNT(*) AS n FROM tickets WHERE event_id = ?",
        (event_id,),
    ).fetchone()["n"]

    return event, registered


def make_token(ticket_id, event_id):
    return serializer.dumps(
        {
            "ticket_id": ticket_id,
            "event_id": event_id,
            "nonce": secrets.token_urlsafe(24),
        },
        salt="campus-ticket-v2",
    )


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def qr_path(ticket_id, token):
    path = QR_DIR / f"ticket-{ticket_id}.png"
    image = qrcode.make(token)
    image.save(path)
    return path


def verify_ticket_token(token):
    expired = False

    for salt in ("campus-ticket-v2", "campus-ticket-v1"):
        try:
            payload = serializer.loads(
                token,
                salt=salt,
                max_age=app.config["TICKET_MAX_AGE_SECONDS"],
            )

            if (
                not isinstance(payload, dict)
                or not payload.get("ticket_id")
                or not payload.get("event_id")
                or not payload.get("nonce")
            ):
                continue

            return payload, None
        except SignatureExpired:
            expired = True
        except BadSignature:
            continue

    return None, "EXPIRED TICKET" if expired else "INVALID TICKET"


def audit_checkin(
    connection,
    ticket_id,
    event_id,
    participant_name,
    status,
    message,
):
    connection.execute(
        """
        INSERT INTO checkin_audit(
            ticket_id,
            event_id,
            participant_name,
            admin_username,
            scanned_at,
            status,
            message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            event_id,
            participant_name,
            session.get("admin_username", "unknown"),
            now_iso(),
            status,
            message,
        ),
    )


def fetch_student_tickets(connection, student_id):
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT
                t.id,
                t.status,
                t.token_created_at,
                t.checked_in_at,
                t.checked_in_by,
                e.id AS event_id,
                e.name AS event_name,
                e.venue,
                e.event_date
            FROM tickets t
            JOIN events e ON e.id = t.event_id
            WHERE t.participant_id = ?
            ORDER BY e.event_date
            """,
            (student_id,),
        ).fetchall()
    ]


def ticket_accessible(connection, ticket_id):
    row = connection.execute(
        """
        SELECT
            t.id,
            t.participant_id,
            t.event_id,
            t.status,
            t.checked_in_at,
            t.checked_in_by,
            e.name AS event_name,
            e.venue,
            e.event_date,
            p.name AS participant_name,
            p.email
        FROM tickets t
        JOIN events e ON e.id = t.event_id
        JOIN participants p ON p.id = t.participant_id
        WHERE t.id = ?
        """,
        (ticket_id,),
    ).fetchone()

    if not row:
        return None

    if session.get("admin_authenticated") is True:
        return row

    if session.get("student_id") == row["participant_id"]:
        return row

    return None


def app_context():
    return {
        "app_name": app.config["APP_NAME"],
        "student_authenticated": bool(session.get("student_id")),
        "student_name": session.get("student_name", ""),
        "student_email": session.get("student_email", ""),
        "admin_authenticated": bool(session.get("admin_authenticated")),
        "admin_username": session.get("admin_username", ""),
    }


@app.get("/")
def index():
    if not session.get("student_id"):
        return redirect(url_for("student_login"))

    return redirect(url_for("events"))


@app.get("/events")
@student_required
def events():
    connection = db()
    rows = connection.execute(
        "SELECT * FROM events WHERE is_active = 1 ORDER BY event_date"
    ).fetchall()

    event_list = []
    for row in rows:
        registered = connection.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE event_id = ?",
            (row["id"],),
        ).fetchone()["n"]
        item = dict(row)
        item["registered"] = registered
        item["remaining"] = max(row["capacity"] - registered, 0)
        item["image_url"] = event_image_url(row["name"], row["id"], row["image_path"])
        event_list.append(item)

    connection.close()

    context = app_context()
    context["events"] = event_list
    context["title"] = "Events"
    return render_template("index.html", **context)


@app.get("/events/<int:event_id>")
@student_required
def event_page(event_id):
    connection = db()
    event, registered = capacity_for_event(connection, event_id)
    existing = connection.execute(
        """
        SELECT id, status
        FROM tickets
        WHERE event_id = ? AND participant_id = ?
        """,
        (event_id, session["student_id"]),
    ).fetchone()
    connection.close()

    if not event:
        return render_template(
            "error.html",
            **app_context(),
            title="Event not found",
            message="The requested event does not exist.",
        ), 404

    context = app_context()
    event_data = dict(event)
    event_data["image_url"] = event_image_url(event_data["name"], event_data["id"], event_data.get("image_path"))

    context.update(
        event=event_data,
        registered=registered,
        full=registered >= event["capacity"],
        existing_ticket=dict(existing) if existing else None,
        title=event["name"],
    )
    return render_template("register.html", **context)


@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if session.get("student_id"):
        return redirect(url_for("events"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        next_url = clean_next_url(request.form.get("next", ""))

        if len(name) < 2 or len(name) > 80:
            return render_template(
                "student_register.html",
                **app_context(),
                error="Enter a valid full name.",
                next=next_url,
            ), 400

        if not valid_email(email) or len(email) > 160:
            return render_template(
                "student_register.html",
                **app_context(),
                error="Enter a valid email address.",
                next=next_url,
            ), 400

        if not password_is_strong(password):
            return render_template(
                "student_register.html",
                **app_context(),
                error="Password must be at least 8 characters and include uppercase, lowercase, and a number.",
                next=next_url,
            ), 400

        if password != confirm_password:
            return render_template(
                "student_register.html",
                **app_context(),
                error="The passwords do not match.",
                next=next_url,
            ), 400

        connection = db()
        existing = connection.execute(
            "SELECT * FROM participants WHERE lower(email) = ?",
            (email,),
        ).fetchone()

        password_hash = generate_password_hash(password)

        try:
            if existing:
                if existing["password_hash"]:
                    connection.close()
                    return render_template(
                        "student_register.html",
                        **app_context(),
                        error="An account with this email already exists. Please sign in.",
                        next=next_url,
                    ), 409

                connection.execute(
                    """
                    UPDATE participants
                    SET name = ?, password_hash = ?, created_at = ?
                    WHERE id = ?
                    """,
                    (name, password_hash, now_iso(), existing["id"]),
                )
                participant_id = existing["id"]
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO participants(
                        name,
                        email,
                        password_hash,
                        created_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (name, email, password_hash, now_iso()),
                )
                participant_id = cursor.lastrowid

            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            connection.close()
            return render_template(
                "student_register.html",
                **app_context(),
                error="Unable to create the account. Please use a different email.",
                next=next_url,
            ), 409
        finally:
            try:
                connection.close()
            except Exception:
                pass

        session.clear()
        session.permanent = True
        session["student_id"] = participant_id
        session["student_name"] = name
        session["student_email"] = email
        csrf_token()

        return redirect(next_url or url_for("events"))

    return render_template(
        "student_register.html",
        **app_context(),
        error=None,
        next=clean_next_url(request.args.get("next", "")),
        title="Create Student Account",
    )


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if session.get("student_id"):
        return redirect(url_for("events"))

    next_url = clean_next_url(
        request.form.get("next", request.args.get("next", ""))
    )

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        key = login_key(email)

        if login_limited(key):
            return render_template(
                "student_login.html",
                **app_context(),
                error="Too many failed attempts. Please wait a few minutes and try again.",
                next=next_url,
                title="Student Login",
            ), 429

        connection = db()
        participant = connection.execute(
            "SELECT * FROM participants WHERE lower(email) = ?",
            (email,),
        ).fetchone()
        connection.close()

        valid = (
            participant is not None
            and participant["password_hash"]
            and check_password_hash(participant["password_hash"], password)
        )

        if not valid:
            record_login_failure(key)
            return render_template(
                "student_login.html",
                **app_context(),
                error="Invalid email or password.",
                next=next_url,
                title="Student Login",
            ), 401

        clear_login_failures(key)
        session.clear()
        session.permanent = True
        session["student_id"] = participant["id"]
        session["student_name"] = participant["name"]
        session["student_email"] = participant["email"]
        csrf_token()

        return redirect(next_url or url_for("events"))

    return render_template(
        "student_login.html",
        **app_context(),
        error=None,
        next=next_url,
        title="Student Login",
    )


@app.post("/student/logout")
@student_required
def student_logout():
    session.clear()
    return redirect(url_for("student_login"))


@app.get("/my-tickets")
@student_required
def my_tickets():
    connection = db()
    tickets = fetch_student_tickets(connection, session["student_id"])
    connection.close()

    context = app_context()
    context.update(tickets=tickets, title="My Tickets")
    return render_template("my_tickets.html", **context)


@app.post("/register/<int:event_id>")
@student_required
def register(event_id):
    student_id = session["student_id"]

    connection = db()
    try:
        connection.execute("BEGIN IMMEDIATE")

        event, registered = capacity_for_event(connection, event_id)
        if not event:
            connection.rollback()
            return render_template(
                "error.html",
                **app_context(),
                title="Event not found",
                message="The requested event does not exist.",
            ), 404

        if registered >= event["capacity"]:
            connection.rollback()
            return render_template(
                "error.html",
                **app_context(),
                title="Event full",
                message="This event has reached its maximum capacity.",
            ), 409

        existing = connection.execute(
            """
            SELECT id
            FROM tickets
            WHERE event_id = ? AND participant_id = ?
            """,
            (event_id, student_id),
        ).fetchone()

        if existing:
            connection.rollback()
            return render_template(
                "error.html",
                **app_context(),
                title="Already registered",
                message="You already have a ticket for this event.",
            ), 409

        placeholder = token_hash(secrets.token_urlsafe(32))
        cursor = connection.execute(
            """
            INSERT INTO tickets(
                event_id,
                participant_id,
                token_hash,
                token_created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (event_id, student_id, placeholder, now_iso()),
        )

        ticket_id = cursor.lastrowid
        token = make_token(ticket_id, event_id)

        connection.execute(
            """
            UPDATE tickets
            SET token_hash = ?
            WHERE id = ?
            """,
            (token_hash(token), ticket_id),
        )

        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        return render_template(
            "error.html",
            **app_context(),
            title="Registration failed",
            message="A registration with these details already exists.",
        ), 409
    finally:
        connection.close()

    qr = qr_path(ticket_id, token)

    connection = db()
    ticket = connection.execute(
        """
        SELECT
            t.*,
            e.name AS event_name,
            e.venue,
            e.event_date,
            p.name AS participant_name,
            p.email
        FROM tickets t
        JOIN events e ON e.id = t.event_id
        JOIN participants p ON p.id = t.participant_id
        WHERE t.id = ? AND t.participant_id = ?
        """,
        (ticket_id, student_id),
    ).fetchone()
    connection.close()

    email_html = build_ticket_email(ticket, app.config["APP_NAME"])
    email_result = send_ticket_email(
        ticket["email"],
        f"Your ticket for {ticket['event_name']}",
        email_html,
        qr,
        app.config["APP_BASE_URL"],
        ticket_id,
    )

    preview_url = url_for("email_preview", ticket_id=ticket_id)

    context = app_context()
    context.update(
        ticket=dict(ticket),
        token=token,
        email_result=email_result,
        preview_url=preview_url,
        title="Ticket Issued",
    )
    return render_template("success.html", **context)


@app.get("/ticket/<int:ticket_id>")
@student_required
def ticket_page(ticket_id):
    connection = db()
    ticket = ticket_accessible(connection, ticket_id)
    connection.close()

    if not ticket:
        return render_template(
            "error.html",
            **app_context(),
            title="Ticket not found",
            message="You are not authorized to access this ticket.",
        ), 403

    context = app_context()
    context.update(ticket=dict(ticket), title=f"Ticket #{ticket_id}")
    return render_template("ticket.html", **context)


@app.get("/ticket/<int:ticket_id>/qr")
def ticket_qr(ticket_id):
    connection = db()
    ticket = ticket_accessible(connection, ticket_id)
    connection.close()

    if not ticket:
        return render_template(
            "error.html",
            **app_context(),
            title="Ticket not found",
            message="You are not authorized to access this ticket.",
        ), 403

    path = QR_DIR / f"ticket-{ticket_id}.png"
    if not path.exists():
        return render_template(
            "error.html",
            **app_context(),
            title="QR unavailable",
            message="The QR code could not be found.",
        ), 404

    return send_file(path, mimetype="image/png", as_attachment=False)


@app.get("/email-preview/<int:ticket_id>")
def email_preview(ticket_id):
    connection = db()
    ticket = ticket_accessible(connection, ticket_id)
    connection.close()

    if not ticket:
        return render_template(
            "error.html",
            **app_context(),
            title="Preview not available",
            message="You are not authorized to view this ticket preview.",
        ), 403

    path = EMAIL_DIR / f"ticket-{ticket_id}.html"
    if not path.exists():
        return render_template(
            "error.html",
            **app_context(),
            title="Preview unavailable",
            message="The email preview does not exist yet.",
        ), 404

    return send_file(path, mimetype="text/html")


@app.get("/admin/login")
def admin_login():
    if session.get("admin_authenticated"):
        return redirect(url_for("organizer"))

    return render_template(
        "admin_login.html",
        **app_context(),
        error=None,
        next=clean_next_url(request.args.get("next", "")),
        title="Organizer Login",
    )


@app.post("/admin/login")
def admin_login_submit():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = clean_next_url(request.form.get("next", ""))
    key = login_key(username)

    if login_limited(key):
        return render_template(
            "admin_login.html",
            **app_context(),
            error="Too many failed attempts. Please wait a few minutes and try again.",
            next=next_url,
            title="Organizer Login",
        ), 429

    valid = (
        hmac.compare_digest(username, app.config["ADMIN_USERNAME"])
        and verify_admin_password(password)
    )

    if not valid:
        record_login_failure(key)
        return render_template(
            "admin_login.html",
            **app_context(),
            error="Invalid administrator credentials.",
            next=next_url,
            title="Organizer Login",
        ), 401

    clear_login_failures(key)
    session.clear()
    session.permanent = True
    session["admin_authenticated"] = True
    session["admin_username"] = username
    csrf_token()

    return redirect(next_url or url_for("organizer"))


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/organizer")
@admin_required
def organizer():
    connection = db()

    events_rows = connection.execute(
        """
        SELECT
            e.*,
            COUNT(t.id) AS registered,
            COALESCE(SUM(CASE WHEN t.status = 'CHECKED-IN' THEN 1 ELSE 0 END), 0) AS checked_in
        FROM events e
        LEFT JOIN tickets t ON t.event_id = e.id
        WHERE e.is_active = 1
        GROUP BY e.id
        ORDER BY e.event_date
        """
    ).fetchall()

    total_tickets = connection.execute(
        "SELECT COUNT(*) AS n FROM tickets"
    ).fetchone()["n"]

    total_checked_in = connection.execute(
        "SELECT COUNT(*) AS n FROM tickets WHERE status = 'CHECKED-IN'"
    ).fetchone()["n"]

    total_students = connection.execute(
        "SELECT COUNT(*) AS n FROM participants WHERE password_hash IS NOT NULL"
    ).fetchone()["n"]

    recent_audit = [
        dict(row)
        for row in connection.execute(
            """
            SELECT
                id,
                ticket_id,
                participant_name,
                admin_username,
                scanned_at,
                status,
                message
            FROM checkin_audit
            ORDER BY scanned_at DESC
            LIMIT 12
            """
        ).fetchall()
    ]

    connection.close()

    context = app_context()
    context.update(
        events=[dict(row) | {"image_url": event_image_url(row["name"], row["id"], row["image_path"])} for row in events_rows],
        total_tickets=total_tickets,
        total_checked_in=total_checked_in,
        total_students=total_students,
        recent_audit=recent_audit,
        title="Organizer Dashboard",
    )
    return render_template("organizer.html", **context)


@app.route("/admin/events/new", methods=["GET", "POST"])
@admin_required
def create_event():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        venue = request.form.get("venue", "").strip()
        event_date_input = request.form.get("event_date", "").strip()
        capacity_raw = request.form.get("capacity", "").strip()
        image = request.files.get("image")

        try:
            capacity = int(capacity_raw)
        except ValueError:
            capacity = 0

        error = None
        if not name or len(name) > 120:
            error = "Event name is required and must be under 120 characters."
        elif not description or len(description) > 500:
            error = "Description is required and must be under 500 characters."
        elif not venue or len(venue) > 160:
            error = "Venue is required and must be under 160 characters."
        elif capacity < 1 or capacity > 100000:
            error = "Capacity must be between 1 and 100000."
        else:
            try:
                parsed = datetime.fromisoformat(event_date_input)
                event_date = parsed.strftime("%Y-%m-%d %I:%M %p")
            except ValueError:
                error = "Choose a valid event date and time."

        image_filename = None
        if not error and image and image.filename:
            original_name = secure_filename(image.filename)
            extension = Path(original_name).suffix.lower().lstrip(".")
            if extension not in ALLOWED_EVENT_IMAGE_EXTENSIONS:
                error = "Event image must be JPG, JPEG, PNG, or WEBP."
            else:
                image.stream.seek(0, os.SEEK_END)
                image_size = image.stream.tell()
                image.stream.seek(0)
                if image_size > MAX_EVENT_IMAGE_BYTES:
                    error = "Event image must be 5 MB or smaller."
                elif not valid_event_image_bytes(image):
                    error = "The uploaded file is not a valid JPG, PNG, or WEBP image."
                else:
                    image_filename = f"{secrets.token_hex(16)}.{extension}"

        if error:
            return render_template(
                "create_event.html",
                **app_context(),
                error=error,
                form=request.form,
                title="Create Event",
            ), 400

        if image_filename:
            image.save(EVENT_IMAGE_DIR / image_filename)

        connection = db()
        connection.execute(
            """
            INSERT INTO events(
                name, description, venue, event_date, capacity, created_at, image_path, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (name, description, venue, event_date, capacity, now_iso(), image_filename),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("organizer"))

    return render_template(
        "create_event.html",
        **app_context(),
        error=None,
        form={},
        title="Create Event",
    )


@app.post("/admin/events/<int:event_id>/remove")
@admin_required
def remove_event(event_id):
    connection = db()
    event = connection.execute(
        "SELECT id, name, image_path FROM events WHERE id = ? AND is_active = 1",
        (event_id,),
    ).fetchone()
    if not event:
        connection.close()
        return redirect(url_for("organizer"))

    connection.execute(
        "UPDATE events SET is_active = 0 WHERE id = ?",
        (event_id,),
    )
    connection.commit()
    connection.close()

    if event["image_path"]:
        image_file = EVENT_IMAGE_DIR / Path(event["image_path"]).name
        try:
            image_file.unlink(missing_ok=True)
        except OSError:
            pass

    return redirect(url_for("organizer"))


@app.get("/event-images/<path:filename>")
def event_image(filename):
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.lower().lstrip(".") not in ALLOWED_EVENT_IMAGE_EXTENSIONS:
        return "", 404
    return send_from_directory(EVENT_IMAGE_DIR, safe_name)


@app.post("/api/checkin")
@admin_required
def checkin():
    token = ""

    if request.is_json:
        body = request.get_json(silent=True) or {}
        token = str(body.get("token", "")).strip()
    else:
        token = request.form.get("token", "").strip()

    if not token or len(token) > 4096:
        return jsonify({
            "status": "INVALID TICKET",
            "message": "No valid ticket token was provided.",
        }), 400

    payload, token_error = verify_ticket_token(token)

    if token_error:
        return jsonify({
            "status": token_error,
            "message": token_error,
        }), 400

    try:
        ticket_id = int(payload["ticket_id"])
        event_id = int(payload["event_id"])
    except (TypeError, ValueError):
        return jsonify({
            "status": "INVALID TICKET",
            "message": "Ticket payload is malformed.",
        }), 400

    connection = db()

    row = connection.execute(
        """
        SELECT
            t.*,
            e.name AS event_name,
            e.venue,
            e.event_date,
            p.name AS participant_name,
            p.email
        FROM tickets t
        JOIN events e ON e.id = t.event_id
        JOIN participants p ON p.id = t.participant_id
        WHERE t.id = ? AND t.event_id = ?
        """,
        (ticket_id, event_id),
    ).fetchone()

    if not row:
        audit_checkin(
            connection,
            None,
            event_id,
            None,
            "INVALID TICKET",
            "Ticket record does not exist.",
        )
        connection.commit()
        connection.close()
        return jsonify({
            "status": "INVALID TICKET",
            "message": "Ticket record is invalid.",
        }), 400

    if not hmac.compare_digest(row["token_hash"], token_hash(token)):
        audit_checkin(
            connection,
            row["id"],
            row["event_id"],
            row["participant_name"],
            "INVALID TICKET",
            "Presented token does not match the stored ticket hash.",
        )
        connection.commit()
        connection.close()
        return jsonify({
            "status": "INVALID TICKET",
            "message": "Ticket signature or ticket record is invalid.",
        }), 400

    if row["status"] == "CHECKED-IN":
        checked = row["checked_in_at"]
        audit_checkin(
            connection,
            row["id"],
            row["event_id"],
            row["participant_name"],
            "ALREADY USED",
            "Ticket was scanned after a previous successful check-in.",
        )
        connection.commit()
        connection.close()
        return jsonify({
            "status": "ALREADY USED",
            "message": "This ticket has already been checked in.",
            "participant": row["participant_name"],
            "email": row["email"],
            "event": row["event_name"],
            "checked_in_at": checked,
            "checked_in_by": row["checked_in_by"],
        }), 200

    checked_in_at = now_iso()
    update = connection.execute(
        """
        UPDATE tickets
        SET
            status = 'CHECKED-IN',
            checked_in_at = ?,
            checked_in_by = ?
        WHERE id = ? AND status = 'ISSUED'
        """,
        (
            checked_in_at,
            session.get("admin_username", "unknown"),
            row["id"],
        ),
    )

    if update.rowcount != 1:
        refreshed = connection.execute(
            "SELECT checked_in_at, checked_in_by FROM tickets WHERE id = ?",
            (row["id"],),
        ).fetchone()
        already_checked = refreshed["checked_in_at"] if refreshed else None
        already_checked_by = refreshed["checked_in_by"] if refreshed else None

        audit_checkin(
            connection,
            row["id"],
            row["event_id"],
            row["participant_name"],
            "ALREADY USED",
            "Concurrent check-in attempt did not win the atomic update.",
        )
        connection.commit()
        connection.close()

        return jsonify({
            "status": "ALREADY USED",
            "message": "This ticket has already been checked in.",
            "participant": row["participant_name"],
            "email": row["email"],
            "event": row["event_name"],
            "checked_in_at": already_checked,
            "checked_in_by": already_checked_by,
        }), 200

    audit_checkin(
        connection,
        row["id"],
        row["event_id"],
        row["participant_name"],
        "CHECKED-IN",
        "Ticket successfully verified and checked in.",
    )
    connection.commit()
    connection.close()

    return jsonify({
        "status": "CHECKED-IN",
        "message": "Ticket verified and checked in.",
        "participant": row["participant_name"],
        "email": row["email"],
        "event": row["event_name"],
        "checked_in_at": checked_in_at,
        "checked_in_by": session.get("admin_username", "unknown"),
    }), 200


@app.get("/api/event/<int:event_id>")
@admin_required
def event_stats(event_id):
    connection = db()
    event, registered = capacity_for_event(connection, event_id)

    if event:
        checked_in = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM tickets
            WHERE event_id = ? AND status = 'CHECKED-IN'
            """,
            (event_id,),
        ).fetchone()["n"]
    else:
        checked_in = 0

    connection.close()

    if not event:
        return jsonify({"error": "Event not found"}), 404

    return jsonify({
        "id": event["id"],
        "name": event["name"],
        "capacity": event["capacity"],
        "registered": registered,
        "checked_in": checked_in,
        "remaining": max(event["capacity"] - registered, 0),
    })


@app.get("/api/audit/<int:event_id>")
@admin_required
def audit_logs(event_id):
    connection = db()
    rows = connection.execute(
        """
        SELECT
            id,
            ticket_id,
            participant_name,
            admin_username,
            scanned_at,
            status,
            message
        FROM checkin_audit
        WHERE event_id = ?
        ORDER BY scanned_at DESC
        LIMIT 200
        """,
        (event_id,),
    ).fetchall()
    connection.close()
    return jsonify([dict(row) for row in rows])


@app.get("/api/export/<int:event_id>")
@admin_required
def export_attendance(event_id):
    connection = db()
    event = connection.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()

    if not event:
        connection.close()
        return jsonify({"error": "Event not found"}), 404

    rows = connection.execute(
        """
        SELECT
            p.name,
            p.email,
            t.status,
            t.token_created_at,
            t.checked_in_at,
            t.checked_in_by
        FROM tickets t
        JOIN participants p ON p.id = t.participant_id
        WHERE t.event_id = ?
        ORDER BY p.name
        """,
        (event_id,),
    ).fetchall()
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name",
        "Email",
        "Status",
        "Ticket Created",
        "Checked In At",
        "Checked In By",
    ])

    for row in rows:
        writer.writerow([
            row["name"],
            row["email"],
            row["status"],
            row["token_created_at"],
            row["checked_in_at"] or "",
            row["checked_in_by"] or "",
        ])

    data = io.BytesIO(output.getvalue().encode("utf-8"))
    filename = (
        re.sub(r"[^A-Za-z0-9_-]+", "_", event["name"]).strip("_")
        or f"event_{event_id}"
    ) + "_attendance.csv"

    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database initialized")


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
