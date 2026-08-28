"""Audit logging service — tracks who did what."""

import json
import logging
from flask import request
from flask_login import current_user

from app import db
from app.models import AuditLog

logger = logging.getLogger(__name__)


def log_action(action: str, details: dict | str | None = None):
    """
    Record an audit log entry.

    Args:
        action: Short action name, e.g. 'manual_entry', 'target_update',
                'user_create', 'plant_update', 'erp_sync'
        details: Dict or string with context (auto-serialised to JSON)
    """
    try:
        user_id = None
        username = "system"

        if current_user and hasattr(current_user, "id") and current_user.is_authenticated:
            user_id = current_user.id
            username = current_user.username

        ip_address = None
        try:
            ip_address = request.remote_addr
        except RuntimeError:
            pass  # outside request context (e.g. CLI)

        detail_text = None
        if details is not None:
            if isinstance(details, dict):
                detail_text = json.dumps(details, default=str)
            else:
                detail_text = str(details)

        entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            details=detail_text,
            ip_address=ip_address,
        )
        db.session.add(entry)
        # Don't commit here — let the caller's commit handle it.
        # If the caller doesn't commit, flush at least so it's in the transaction.
        db.session.flush()
    except Exception as exc:
        logger.error(f"Audit log failed: {exc}")
