"""HMAC-signed token generation and verification for vote links and magic links."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta
from typing import Any
from uuid import uuid4

from policy_crawler.config import get_settings

VOTE_TOKEN_TTL = timedelta(days=14)
MAGIC_LINK_TOKEN_TTL = timedelta(days=30)


def _get_key() -> bytes:
    settings = get_settings()
    if not settings.token_hmac_secret:
        raise RuntimeError("TOKEN_HMAC_SECRET not set")
    return settings.token_hmac_secret.encode()


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64_decode(s: str) -> bytes:
    # Restore stripped padding before decoding
    return base64.urlsafe_b64decode(s + "=" * ((-len(s)) % 4))


def make_token(payload: dict[str, Any], kind: str, expires_in: timedelta) -> str:
    """Create a signed token.

    Format: <b64url(payload_json)>.<b64url(hmac_sha256(key, payload_json))>
    """
    now = int(time.time())
    full_payload: dict[str, Any] = {
        **payload,
        "kind": kind,
        "iat": now,
        "exp": now + int(expires_in.total_seconds()),
        "nonce": uuid4().hex,
    }
    payload_json = json.dumps(full_payload, separators=(",", ":")).encode()
    sig = hmac.new(_get_key(), payload_json, hashlib.sha256).digest()
    return f"{_b64_encode(payload_json)}.{_b64_encode(sig)}"


def verify_token(token: str, expected_kind: str) -> dict[str, Any] | None:
    """Verify HMAC, expiry, and kind. Returns payload dict on success, None on any failure."""
    parts = token.split(".")
    if len(parts) != 2:
        return None
    payload_b64, sig_b64 = parts
    try:
        payload_json = _b64_decode(payload_b64)
        actual_sig = _b64_decode(sig_b64)
    except Exception:
        return None

    try:
        expected_sig = hmac.new(_get_key(), payload_json, hashlib.sha256).digest()
    except Exception:
        return None

    if not hmac.compare_digest(expected_sig, actual_sig):
        return None

    try:
        payload = json.loads(payload_json)
    except (ValueError, TypeError):
        return None

    if payload.get("kind") != expected_kind:
        return None
    if int(time.time()) > payload.get("exp", 0):
        return None

    return payload
