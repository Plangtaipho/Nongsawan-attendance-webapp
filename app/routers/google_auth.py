"""Sign in with Google (OpenID Connect authorization-code flow).

Google only proves who the person is. They get in only if an active user in our
database has that exact, Google-verified e-mail; accounts are never created here.
The ID token comes straight from Google's token endpoint over TLS, authenticated
with our client secret, so its signature does not need separate checking
(OpenID Connect Core 3.1.3.7); its audience, issuer, expiry and nonce are checked.
"""
import base64
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.security import new_csrf_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/google", include_in_schema=False)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
STATE_MAX_AGE = 10 * 60


def _fail(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?error={code}", status_code=303)


def _safe_next(value: str | None) -> str:
    v = value or "/"
    return v if v.startswith("/") and not v.startswith(("//", "/\\")) else "/"


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Swap the authorization code for tokens at Google. Separate so tests can replace it."""
    s = get_settings()
    data = urllib.parse.urlencode({
        "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (fixed https URL)
        return json.load(resp)


def _claims(id_token: str) -> dict:
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@router.get("/start")
def start(request: Request, next: str | None = None):
    s = get_settings()
    if not s.google_enabled:
        return _fail("google_off")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    request.session["g_oauth"] = {"state": state, "nonce": nonce, "at": int(time.time()), "next": _safe_next(next)}
    params = {
        "client_id": s.google_client_id, "response_type": "code", "scope": "openid email profile",
        "redirect_uri": str(request.url_for("google_callback")), "state": state, "nonce": nonce,
        "prompt": "select_account",
    }
    if s.google_allowed_domain:
        params["hd"] = s.google_allowed_domain  # only a hint to Google's chooser; enforced in the callback
    return RedirectResponse(AUTH_URL + "?" + urllib.parse.urlencode(params), status_code=303)


@router.get("/callback", name="google_callback")
def callback(request: Request, state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db)):
    s = get_settings()
    saved = request.session.pop("g_oauth", None)
    if not s.google_enabled:
        return _fail("google_off")
    if not saved or not state or not secrets.compare_digest(state, saved.get("state", "")) \
            or time.time() - saved.get("at", 0) > STATE_MAX_AGE:
        return _fail("google_state")
    if error or not code:
        return _fail("google_cancel")

    try:
        tokens = exchange_code(code, str(request.url_for("google_callback")))
        claims = _claims(tokens["id_token"])
    except (urllib.error.URLError, KeyError, ValueError, IndexError) as e:
        log.warning("Google token exchange failed: %s", e.__class__.__name__)
        return _fail("google_failed")

    if (claims.get("aud") != s.google_client_id or claims.get("iss") not in ISSUERS
            or claims.get("exp", 0) < time.time() or claims.get("nonce") != saved.get("nonce")):
        return _fail("google_failed")
    email = str(claims.get("email", "")).strip().lower()
    if not email or claims.get("email_verified") is not True:
        return _fail("google_unverified")
    if s.google_allowed_domain and claims.get("hd") != s.google_allowed_domain:
        return _fail("google_domain")

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not user.is_active:
        return _fail("google_no_user")

    request.session.clear()  # new session on login (prevents session fixation)
    request.session["user_id"] = user.id
    request.session["csrf"] = new_csrf_token()
    return RedirectResponse(saved.get("next", "/"), status_code=303)
