"""Sign in with Google: only active users with a matching, verified e-mail get in."""
import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import get_settings
from app.routers import google_auth
from tests.conftest import Api


def _token(**claims) -> str:
    base = {"iss": "https://accounts.google.com", "aud": "cid", "exp": time.time() + 300, "email_verified": True}
    body = base64.urlsafe_b64encode(json.dumps({**base, **claims}).encode()).decode().rstrip("=")
    return f"x.{body}.sig"


@pytest.fixture
def google(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "cid")
    monkeypatch.setattr(s, "google_client_secret", "secret")
    monkeypatch.setattr(s, "google_allowed_domain", "")
    box = {}
    monkeypatch.setattr(google_auth, "exchange_code", lambda code, uri: {"id_token": _token(**box["claims"])})
    return box


def _start(a: Api, next_="/history"):
    r = a.c.get(f"/auth/google/start?next={next_}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith(google_auth.AUTH_URL)
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["redirect_uri"][0].endswith("/auth/google/callback")
    return q["state"][0], q["nonce"][0]


def _callback(a: Api, google, state, **claims):
    google["claims"] = claims
    return a.c.get(f"/auth/google/callback?state={state}&code=abc", follow_redirects=False)


def _set_email(username, email):
    admin = Api("admin")
    uid = next(u["id"] for u in admin.get("/api/admin/users").json() if u["username"] == username)
    assert admin.patch(f"/api/admin/users/{uid}", json={"email": email}).status_code == 200
    return admin, uid


def test_login_page_hides_google_when_not_configured(seed):
    assert "เข้าสู่ระบบด้วย Google" not in Api().c.get("/login").text
    assert Api().c.get("/auth/google/start", follow_redirects=False).headers["location"] == "/login?error=google_off"


def test_registered_email_signs_in(seed, google):
    _set_email("teacher1", "Teacher.One@Example.com")  # stored lower-case
    a = Api()
    assert "เข้าสู่ระบบด้วย Google" in a.c.get("/login").text
    state, nonce = _start(a)
    r = _callback(a, google, state, email="teacher.one@example.com", nonce=nonce)
    assert r.status_code == 303 and r.headers["location"] == "/history"
    assert a.get("/api/auth/me").json()["username"] == "teacher1"


@pytest.mark.parametrize("change,error", [
    ({"email": "stranger@example.com"}, "google_no_user"),
    ({"email_verified": False}, "google_unverified"),
    ({"aud": "someone-else"}, "google_failed"),
    ({"nonce": "wrong"}, "google_failed"),
    ({"exp": 1}, "google_failed"),
])
def test_rejected_tokens(seed, google, change, error):
    _set_email("teacher1", "t1@example.com")
    a = Api()
    state, nonce = _start(a)
    r = _callback(a, google, state, **{"email": "t1@example.com", "nonce": nonce, **change})
    assert r.headers["location"] == f"/login?error={error}"
    assert a.get("/api/auth/me").status_code == 401


def test_wrong_state_and_replay_rejected(seed, google):
    _set_email("teacher1", "t1@example.com")
    a = Api()
    state, nonce = _start(a)
    assert _callback(a, google, "forged", email="t1@example.com", nonce=nonce).headers["location"] == "/login?error=google_state"
    # The state is used up even after a failure, so the real one cannot be replayed afterwards.
    assert _callback(a, google, state, email="t1@example.com", nonce=nonce).headers["location"] == "/login?error=google_state"


def test_inactive_user_and_domain(seed, google, monkeypatch):
    admin, uid = _set_email("teacher1", "t1@school.ac.th")
    admin.patch(f"/api/admin/users/{uid}", json={"is_active": False})
    a = Api()
    state, nonce = _start(a)
    assert _callback(a, google, state, email="t1@school.ac.th", nonce=nonce).headers["location"] == "/login?error=google_no_user"

    admin.patch(f"/api/admin/users/{uid}", json={"is_active": True})
    monkeypatch.setattr(get_settings(), "google_allowed_domain", "school.ac.th")
    state, nonce = _start(a)
    assert _callback(a, google, state, email="t1@school.ac.th", nonce=nonce).headers["location"] == "/login?error=google_domain"
    state, nonce = _start(a)
    r = _callback(a, google, state, email="t1@school.ac.th", nonce=nonce, hd="school.ac.th")
    assert r.headers["location"] == "/history"


def test_next_cannot_leave_the_site(seed, google):
    _set_email("teacher1", "t1@example.com")
    a = Api()
    state, nonce = _start(a, next_="//evil.example")
    assert _callback(a, google, state, email="t1@example.com", nonce=nonce).headers["location"] == "/"


def test_error_message_shown_on_login_page(seed):
    assert "ยังไม่ได้ลงทะเบียนในระบบ" in Api().c.get("/login?error=google_no_user").text
