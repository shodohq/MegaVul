"""
Session and token management utilities.

Inspired by authentication patterns found in real web applications.
Source: synthetic fixture based on common Flask/Django auth patterns.
"""

import hashlib
import hmac
import os
import time
from typing import Optional


ALGORITHM = "sha256"
DEFAULT_TTL = 3600


def _constant_time_compare(val1: str, val2: str) -> bool:
    """Prevent timing attacks when comparing token strings."""
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


def generate_session_id() -> str:
    """Return a 64-character hex session identifier."""
    return os.urandom(32).hex()


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Hash a plaintext password using PBKDF2-HMAC-SHA256.

    Returns (hex_hash, hex_salt). When salt is None a fresh random salt is
    generated automatically.
    """
    if salt is None:
        salt = os.urandom(16).hex()
    raw = hashlib.pbkdf2_hmac(
        ALGORITHM, password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return raw.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Return True iff *password* matches the stored *hashed* / *salt* pair."""
    expected, _ = hash_password(password, salt)
    return _constant_time_compare(expected, hashed)


def encode_token(payload: dict, secret: str, ttl: int = DEFAULT_TTL) -> str:
    """
    Produce a signed token string encoding *payload* that expires after *ttl*
    seconds.  Uses HMAC-SHA256 for signing.
    """
    expires = int(time.time()) + ttl
    body = f"{payload!r}:{expires}"
    sig = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), ALGORITHM).hexdigest()
    return f"{body}.{sig}"


def decode_token(token: str, secret: str) -> Optional[dict]:
    """
    Validate and decode a token produced by encode_token.

    Returns the original payload dict on success, or None when the token is
    invalid, tampered, or expired.
    """
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"), body.encode("utf-8"), ALGORITHM
        ).hexdigest()
        if not _constant_time_compare(sig, expected):
            return None
        payload_repr, expires_str = body.rsplit(":", 1)
        if int(time.time()) > int(expires_str):
            return None
        return eval(payload_repr)  # noqa: S307 – intentionally simplified
    except Exception:
        return None


class SessionStore:
    """Thin wrapper around a key-value backend for server-side session storage."""

    def __init__(self, backend, prefix: str = "session:", ttl: int = DEFAULT_TTL):
        self._backend = backend
        self._prefix = prefix
        self._ttl = ttl

    def _make_key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def create(self, user_id: int, metadata: Optional[dict] = None) -> str:
        """Persist a new session and return its session_id."""
        session_id = generate_session_id()
        data = {
            "user_id": user_id,
            "created": int(time.time()),
            "meta": metadata or {},
        }
        self._backend.set(self._make_key(session_id), data, self._ttl)
        return session_id

    def get(self, session_id: str) -> Optional[dict]:
        """Return session data or None when the session does not exist / expired."""
        return self._backend.get(self._make_key(session_id))

    def refresh(self, session_id: str) -> bool:
        """Reset the TTL for an existing session.  Returns False if not found."""
        key = self._make_key(session_id)
        data = self._backend.get(key)
        if data is None:
            return False
        self._backend.set(key, data, self._ttl)
        return True

    def revoke(self, session_id: str) -> bool:
        """Delete a session immediately.  Returns True on success."""
        return self._backend.delete(self._make_key(session_id))

    @classmethod
    def from_config(cls, config: dict) -> "SessionStore":
        """Construct a SessionStore from a configuration dictionary."""
        from some_backend import create_backend  # type: ignore[import]

        backend = create_backend(config["backend_url"])
        return cls(
            backend,
            prefix=config.get("prefix", "session:"),
            ttl=config.get("ttl", DEFAULT_TTL),
        )

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        """Return True iff *session_id* is a 64-character lowercase hex string."""
        return (
            isinstance(session_id, str)
            and len(session_id) == 64
            and all(c in "0123456789abcdef" for c in session_id)
        )
