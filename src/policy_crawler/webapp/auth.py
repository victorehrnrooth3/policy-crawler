"""Session management for the webapp.

Sessions are HMAC-signed cookies. No server-side state required.
Cookie format mirrors tokens.py: base64url(payload_json).base64url(hmac_sha256).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Request, Response

from policy_crawler.config import get_settings

COOKIE_SESSION = "session"
COOKIE_CSRF = "csrf_token"
SESSION_TTL = 30 * 24 * 60 * 60  # 30 days


class AuthRequired(Exception):
    """Raised when a protected route is accessed without a valid session."""


def _session_key() -> bytes:
    settings = get_settings()
    if not settings.session_cookie_secret:
        raise RuntimeError("SESSION_COOKIE_SECRET not set")
    return settings.session_cookie_secret.encode()


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * ((-len(s)) % 4))


def _sign_payload(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(_session_key(), payload_json, hashlib.sha256).digest()
    return f"{_b64e(payload_json)}.{_b64e(sig)}"


def _verify_payload(cookie: str) -> dict[str, Any] | None:
    parts = cookie.split(".")
    if len(parts) != 2:
        return None
    payload_b64, sig_b64 = parts
    try:
        payload_json = _b64d(payload_b64)
        actual_sig = _b64d(sig_b64)
    except Exception:
        return None
    try:
        expected_sig = hmac.new(_session_key(), payload_json, hashlib.sha256).digest()
    except RuntimeError:
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(payload_json)
    except Exception:
        return None
    if int(time.time()) > payload.get("exp", 0):
        return None
    return payload


def set_session(response: Response, email: str, request: Request | None = None) -> None:
    now = int(time.time())
    cookie = _sign_payload({"email": email, "iat": now, "exp": now + SESSION_TTL})
    secure = request is not None and request.url.scheme == "https"
    response.set_cookie(
        COOKIE_SESSION,
        cookie,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL,
        secure=secure,
    )


def current_user(request: Request) -> str | None:
    cookie = request.cookies.get(COOKIE_SESSION)
    if not cookie:
        return None
    payload = _verify_payload(cookie)
    if not payload:
        return None
    return str(payload.get("email", ""))


def require_session(request: Request) -> str:
    """FastAPI dependency — returns email or raises AuthRequired."""
    user = current_user(request)
    if not user:
        raise AuthRequired()
    return user


# ── CSRF ──────────────────────────────────────────────────────────────────────


def get_csrf_token(request: Request) -> str:
    """Return the CSRF token from the cookie, generating a new one if absent."""
    return request.cookies.get(COOKIE_CSRF) or secrets.token_hex(16)


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_CSRF, token, httponly=False, samesite="strict")


def verify_csrf(request: Request, form_token: str) -> bool:
    cookie_token = request.cookies.get(COOKIE_CSRF)
    return bool(cookie_token and hmac.compare_digest(cookie_token, form_token))
