"""Tests for digest/tokens.py — round-trip, expiry, and tamper rejection."""

from __future__ import annotations

import base64
import json
from collections.abc import Generator
from datetime import timedelta

import pytest

_MOCK_SECRET = "test-secret-key-for-tokens-32bytes!!"


@pytest.fixture(autouse=True)
def _token_settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    from policy_crawler.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("TOKEN_HMAC_SECRET", _MOCK_SECRET)
    yield
    get_settings.cache_clear()


def test_round_trip_vote_token() -> None:
    from policy_crawler.digest.tokens import make_token, verify_token

    payload = {"job_id": "abc-123", "vote": "up"}
    token = make_token(payload, "vote", timedelta(days=1))
    result = verify_token(token, "vote")

    assert result is not None
    assert result["job_id"] == "abc-123"
    assert result["vote"] == "up"
    assert result["kind"] == "vote"


def test_round_trip_magic_link_token() -> None:
    from policy_crawler.digest.tokens import make_token, verify_token

    token = make_token({"purpose": "session"}, "magic_link", timedelta(days=30))
    result = verify_token(token, "magic_link")

    assert result is not None
    assert result["kind"] == "magic_link"
    assert result["purpose"] == "session"


def test_token_contains_nonce() -> None:
    from policy_crawler.digest.tokens import make_token

    t1 = make_token({"x": 1}, "vote", timedelta(days=1))
    t2 = make_token({"x": 1}, "vote", timedelta(days=1))
    assert t1 != t2


def test_expired_token_returns_none() -> None:
    from policy_crawler.digest.tokens import make_token, verify_token

    token = make_token({"x": 1}, "vote", timedelta(seconds=-1))
    assert verify_token(token, "vote") is None


def test_wrong_kind_returns_none() -> None:
    from policy_crawler.digest.tokens import make_token, verify_token

    token = make_token({"x": 1}, "vote", timedelta(days=1))
    assert verify_token(token, "magic_link") is None


def test_tampered_signature_returns_none() -> None:
    from policy_crawler.digest.tokens import make_token, verify_token

    token = make_token({"x": 1}, "vote", timedelta(days=1))
    payload_b64, sig_b64 = token.split(".")
    # Flip the last character of the signature
    flipped = sig_b64[:-1] + ("A" if sig_b64[-1] != "A" else "B")
    assert verify_token(f"{payload_b64}.{flipped}", "vote") is None


def test_tampered_payload_returns_none() -> None:
    from policy_crawler.digest.tokens import make_token, verify_token

    token = make_token({"x": 1}, "vote", timedelta(days=1))
    payload_b64, sig_b64 = token.split(".")

    raw = base64.urlsafe_b64decode(payload_b64 + "=" * ((-len(payload_b64)) % 4))
    payload = json.loads(raw)
    payload["x"] = 999
    new_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()

    assert verify_token(f"{new_b64}.{sig_b64}", "vote") is None


def test_malformed_token_returns_none() -> None:
    from policy_crawler.digest.tokens import verify_token

    assert verify_token("notavalidtoken", "vote") is None
    assert verify_token("a.b.c", "vote") is None
    assert verify_token("", "vote") is None


def test_missing_secret_raises() -> None:
    from unittest.mock import MagicMock, patch

    from policy_crawler.config import Settings
    from policy_crawler.digest.tokens import make_token

    # Patch get_settings so that token_hmac_secret is None regardless of .env content.
    mock_settings = MagicMock(spec=Settings)
    mock_settings.token_hmac_secret = None

    with (
        patch("policy_crawler.digest.tokens.get_settings", return_value=mock_settings),
        pytest.raises(RuntimeError, match="TOKEN_HMAC_SECRET"),
    ):
        make_token({"x": 1}, "vote", timedelta(days=1))
