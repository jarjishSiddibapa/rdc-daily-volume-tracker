"""Role-based access control decorators."""

from functools import wraps
from flask import jsonify, redirect, url_for, request, g
from flask_login import current_user


def admin_required(f):
    """Restrict route to admin users only."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        if current_user.role != "admin":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Admin access required"}), 403
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def employee_details_required(f):
    """Restrict route to admin + users with can_edit_employee_details permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        if current_user.role != "admin" and not current_user.can_edit_employee_details:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Employee details permission required"}), 403
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def manual_entry_required(f):
    """Restrict route to admin + manual_entry users."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        if current_user.role not in ("admin", "manual_entry"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Manual entry permission required"}), 403
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def targets_required(f):
    """Restrict route to admin OR manual_entry users with can_update_targets permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        if current_user.role == "admin":
            return f(*args, **kwargs)
        if current_user.role == "manual_entry" and current_user.can_update_targets:
            return f(*args, **kwargs)
        if request.is_json or request.path.startswith("/api/"):
            return jsonify({"error": "Targets update permission required"}), 403
        return redirect(url_for("dashboard.index"))
    return decorated


def api_token_required(f):
    """Restrict route to requests carrying a valid Bearer API token.

    Used only by the public /api/v1/ blueprint — unrelated to the
    session-based Flask-Login auth used everywhere else. Never redirects;
    always returns JSON, since callers are external applications.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        from app.services.api_tokens import verify_token

        auth_header = request.headers.get("Authorization", "")
        raw_token = ""
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[len("Bearer "):].strip()

        if not raw_token:
            return jsonify({"error": "Missing API token. Send it as: Authorization: Bearer <token>"}), 401

        token = verify_token(raw_token)
        if not token:
            return jsonify({"error": "Invalid, revoked, or expired API token"}), 401

        g.api_token = token
        return f(*args, **kwargs)
    return decorated
