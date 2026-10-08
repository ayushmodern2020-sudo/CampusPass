import os

os.environ["MAIL_MODE"] = "demo"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "AdminPass123"

import app as application

application.app.config.update(TESTING=True)


def fresh_app(tmp_path):
    application.DB_PATH = tmp_path / "test.db"
    application.QR_DIR = tmp_path / "qr"
    application.EMAIL_DIR = tmp_path / "emails"
    application.QR_DIR.mkdir(parents=True, exist_ok=True)
    application.EMAIL_DIR.mkdir(parents=True, exist_ok=True)
    application.login_failures.clear()

    def fake_qr_path(ticket_id, token):
        path = application.QR_DIR / f"ticket-{ticket_id}.png"
        path.write_bytes(b"test-image")
        return path

    application.qr_path = fake_qr_path
    application.init_db()
    return application.app.test_client()


def get_csrf(client):
    with client.session_transaction() as sess:
        token = sess.get("_csrf_token")
        if not token:
            sess["_csrf_token"] = "test-csrf-token"
            token = "test-csrf-token"
        return token


def register_student(client, name="Ayush", email="ayush@example.com", password="StrongPass1"):
    token = get_csrf(client)
    return client.post(
        "/student/register",
        data={
            "_csrf_token": token,
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )


def login_admin(client):
    token = get_csrf(client)
    return client.post(
        "/admin/login",
        data={
            "_csrf_token": token,
            "username": "admin",
            "password": "AdminPass123",
        },
    )


def test_root_requires_student_login(tmp_path):
    client = fresh_app(tmp_path)
    response = client.get("/")
    assert response.status_code == 302
    assert "/student/login" in response.headers["Location"]


def test_student_can_register_and_view_events(tmp_path):
    client = fresh_app(tmp_path)
    response = register_student(client)
    assert response.status_code == 302
    assert "/events" in response.headers["Location"]

    response = client.get("/events")
    assert response.status_code == 200
    assert b"TechFest 2026" in response.data


def test_event_and_registration_require_student_authentication(tmp_path):
    client = fresh_app(tmp_path)
    response = client.get("/events/1")
    assert response.status_code == 302
    assert "/student/login" in response.headers["Location"]

    response = client.post("/register/1")
    assert response.status_code == 400
    assert b"security token" in response.data.lower()


def test_student_registration_creates_one_ticket_and_duplicate_is_blocked(tmp_path):
    client = fresh_app(tmp_path)
    response = register_student(client)
    assert response.status_code == 302

    csrf = get_csrf(client)
    first = client.post("/register/1", data={"_csrf_token": csrf})
    assert first.status_code == 200
    assert b"You're registered." in first.data

    second = client.post("/register/1", data={"_csrf_token": get_csrf(client)})
    assert second.status_code == 409
    assert b"Already registered" in second.data

    connection = application.db()
    row = connection.execute(
        "SELECT * FROM tickets ORDER BY id DESC LIMIT 1"
    ).fetchone()
    connection.close()
    assert row is not None


def test_admin_protection_and_checkin(tmp_path):
    client = fresh_app(tmp_path)

    response = client.get("/organizer")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]

    register_student(client)
    csrf = get_csrf(client)
    client.post("/register/1", data={"_csrf_token": csrf})

    connection = application.db()
    row = connection.execute(
        "SELECT * FROM tickets ORDER BY id DESC LIMIT 1"
    ).fetchone()
    token = application.make_token(row["id"], row["event_id"])
    connection.execute(
        "UPDATE tickets SET token_hash = ? WHERE id = ?",
        (application.token_hash(token), row["id"]),
    )
    connection.commit()
    connection.close()

    client.post("/student/logout", data={"_csrf_token": get_csrf(client)})

    login = login_admin(client)
    assert login.status_code == 302
    assert "/organizer" in login.headers["Location"]

    csrf = get_csrf(client)
    first = client.post(
        "/api/checkin",
        json={"token": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 200
    assert first.json["status"] == "CHECKED-IN"

    second = client.post(
        "/api/checkin",
        json={"token": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert second.status_code == 200
    assert second.json["status"] == "ALREADY USED"

    invalid = client.post(
        "/api/checkin",
        json={"token": "forged-token"},
        headers={"X-CSRF-Token": csrf},
    )
    assert invalid.status_code == 400
    assert invalid.json["status"] == "INVALID TICKET"


def test_ticket_qr_is_private(tmp_path):
    client = fresh_app(tmp_path)
    response = client.get("/ticket/1/qr")
    assert response.status_code in {302, 403}
