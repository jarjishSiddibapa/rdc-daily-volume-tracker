"""API token generation and verification for the public read-only /api/v1/ endpoints.

Tokens are issued via POST /api/v1/token (username + password) and expire
after TOKEN_LIFETIME_HOURS — the calling application re-authenticates to get
a fresh one rather than holding a permanent credential.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from app import db
from app.models import ApiToken, User

TOKEN_PREFIX = "dvt_"
TOKEN_LIFETIME_HOURS = 24


def _hash_token(raw_token: str) -> str:
    """Deterministic hash used for DB lookup. Tokens are high-entropy random
    strings (not user-chosen passwords), so an unsalted SHA-256 digest is
    sufficient and allows direct indexed lookup by hash."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def authenticate(username: str, password: str) -> "User | None":
    """Validate username/email + password. Returns the User row, or None."""
    if not username or not password:
        return None
    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()
    if not user or not user.is_active_user or not user.check_password(password):
        return None
    return user


def issue_token(user: "User") -> tuple[str, "ApiToken"]:
    """Create and persist a new API token for *user*. Returns (raw_token, ApiToken row).

    The raw token is returned exactly once — only its hash is stored. Each
    call issues a fresh token valid for TOKEN_LIFETIME_HOURS; older tokens for
    the same user remain valid until their own expiry.
    """
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=TOKEN_LIFETIME_HOURS)

    token = ApiToken(
        name=f"{user.username} (API login)",
        token_prefix=raw[:12],
        token_hash=_hash_token(raw),
        scopes="read",
        created_by=user.id,
        is_active=True,
        expires_at=expires_at,
    )
    db.session.add(token)
    db.session.commit()
    return raw, token


def verify_token(raw_token: str) -> "ApiToken | None":
    """Look up an active, non-expired token by its raw value. Updates last_used_at."""
    if not raw_token or not raw_token.startswith(TOKEN_PREFIX):
        return None

    token_hash = _hash_token(raw_token)
    token = ApiToken.query.filter_by(token_hash=token_hash, is_active=True).first()
    if not token:
        return None

    if token.expires_at and token.expires_at < datetime.utcnow():
        return None

    token.last_used_at = datetime.utcnow()
    db.session.commit()
    return token
