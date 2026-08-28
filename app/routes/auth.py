"""Authentication routes — login / logout / forgot-password."""

import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User
from app.services.audit import log_action

auth_bp = Blueprint("auth", __name__)

# In-memory brute-force tracker: {ip: [failed_attempt_datetime, ...]}
_failed_attempts: dict = defaultdict(list)
_MAX_ATTEMPTS = 5        # failures before lockout
_LOCKOUT_MINUTES = 15    # how long the lockout lasts

# In-memory password-reset rate limiter: {ip: [request_datetime, ...]}
_reset_attempts: dict = defaultdict(list)
_MAX_RESET_ATTEMPTS = 3    # max reset requests per window
_RESET_WINDOW_MINUTES = 15  # rolling window duration


def _is_locked_out(ip: str) -> tuple[bool, int]:
    """Return (locked, seconds_remaining). Prunes old entries as a side-effect."""
    cutoff = datetime.utcnow() - timedelta(minutes=_LOCKOUT_MINUTES)
    attempts = [t for t in _failed_attempts[ip] if t > cutoff]
    _failed_attempts[ip] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        oldest_in_window = min(attempts)
        unlock_at = oldest_in_window + timedelta(minutes=_LOCKOUT_MINUTES)
        remaining = max(0, int((unlock_at - datetime.utcnow()).total_seconds()))
        return True, remaining
    return False, 0


def _record_failure(ip: str):
    _failed_attempts[ip].append(datetime.utcnow())


def _clear_failures(ip: str):
    _failed_attempts.pop(ip, None)


def _is_reset_locked_out(ip: str) -> bool:
    """Return True if IP has exceeded reset-request limit. Prunes old entries."""
    cutoff = datetime.utcnow() - timedelta(minutes=_RESET_WINDOW_MINUTES)
    attempts = [t for t in _reset_attempts[ip] if t > cutoff]
    _reset_attempts[ip] = attempts
    return len(attempts) >= _MAX_RESET_ATTEMPTS


@auth_bp.route("/login", methods=["GET"])
def login_page():
    """Show login page. Redirect if already logged in."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
def login_submit():
    """Handle login form submission."""
    ip = request.remote_addr

    locked, remaining = _is_locked_out(ip)
    if locked:
        mins = (remaining // 60) + 1
        msg = f"Too many failed attempts. Try again in {mins} minute(s)."
        log_action("login_blocked", {"reason": "brute_force_lockout", "ip": ip})
        db.session.commit()
        if request.is_json:
            return jsonify({"error": msg}), 429
        flash(msg, "error")
        return render_template("login.html"), 429

    # Support both form data and JSON
    if request.is_json:
        data = request.get_json()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
    else:
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

    if not username or not password:
        if request.is_json:
            return jsonify({"error": "Username and password required"}), 400
        flash("Please enter both username and password.", "error")
        return render_template("login.html"), 400

    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user or not user.check_password(password):
        _record_failure(ip)
        remaining_attempts = _MAX_ATTEMPTS - len(_failed_attempts[ip])
        log_action("login_failed", {"username": username, "attempts_remaining": remaining_attempts})
        db.session.commit()
        if request.is_json:
            return jsonify({"error": "Invalid credentials"}), 401
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401

    if not user.is_active:
        log_action("login_blocked", {"username": username, "reason": "account_inactive"})
        db.session.commit()
        if request.is_json:
            return jsonify({"error": "Account disabled. Contact admin."}), 403
        flash("Account disabled. Contact admin.", "error")
        return render_template("login.html"), 403

    # Successful login — clear failure counter, regenerate session (prevent fixation)
    _clear_failures(ip)
    session.clear()
    login_user(user, remember=False)
    log_action("login_success", {"username": user.username, "role": user.role})
    db.session.commit()

    if request.is_json:
        return jsonify({"status": "success", "user": user.to_dict()})

    # Safe redirect — reject any URL with a scheme or netloc (prevent open redirect)
    next_page = request.args.get("next", "")
    parsed = urlparse(next_page)
    if not next_page or parsed.scheme or parsed.netloc:
        next_page = url_for("dashboard.index")
    return redirect(next_page)


@auth_bp.route("/forgot-password", methods=["GET"])
def forgot_password_page():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return render_template("forgot_password.html")


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password_submit():
    ip = request.remote_addr
    if _is_reset_locked_out(ip):
        flash("Too many reset requests. Please wait 15 minutes before trying again.", "error")
        return render_template("forgot_password.html"), 429

    email = (request.form.get("email") or "").strip().lower()
    if not email:
        flash("Please enter your email address.", "error")
        return render_template("forgot_password.html"), 400

    # Record attempt before lookup (prevents timing-based enumeration)
    _reset_attempts[ip].append(datetime.utcnow())

    user = User.query.filter_by(email=email).first()
    # Always show success to avoid user enumeration
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()

        from app.services.email_service import send_password_reset_email
        reset_link = url_for("auth.reset_password_page", token=token, _external=True)
        send_password_reset_email(user.email, user.display_name or user.username, reset_link)
        log_action("password_reset_requested", {"email": email, "username": user.username})
        db.session.commit()

    flash("If that email is registered, a reset link has been sent.", "info")
    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET"])
def reset_password_page(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        flash("This reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password_page"))
    return render_template("reset_password.html", token=token)


@auth_bp.route("/reset-password/<token>", methods=["POST"])
def reset_password_submit(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        flash("This reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password_page"))

    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return render_template("reset_password.html", token=token), 400

    if password != confirm:
        flash("Passwords do not match.", "error")
        return render_template("reset_password.html", token=token), 400

    user.set_password(password)
    user.reset_token = None
    user.reset_token_expires = None
    db.session.commit()
    log_action("password_reset_completed", {"username": user.username})
    db.session.commit()

    flash("Password reset successfully. Please log in.", "info")
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Log out the current user.

    - GET: used for normal navigation (sidebar Logout button) – redirects to login page
    - POST: used for background/tab-close requests – returns a minimal response
    """
    log_action("logout", {"username": current_user.username})
    db.session.commit()
    logout_user()

    # Background logout (e.g. tab close via fetch/sendBeacon)
    if request.method == "POST" or request.is_json:
        return ("", 204)

    # Normal browser navigation
    return redirect(url_for("auth.login_page"))
