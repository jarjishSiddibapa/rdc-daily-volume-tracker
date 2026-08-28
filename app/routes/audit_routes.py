"""Audit log routes — admin-only view of activity log."""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required

from app import db
from app.models import AuditLog
from app.decorators import admin_required

audit_bp = Blueprint("audit", __name__)

# Whitelist of known audit action types (must stay in sync with all log_action() calls)
VALID_ACTIONS = {
    # Auth
    "login_success", "login_failed", "login_blocked", "logout",
    "password_reset_requested", "password_reset_completed",
    "password_reset_email_sent", "password_reset_email_failed",
    # Users
    "user_create", "user_update", "user_delete",
    "user_role_change", "user_deactivated", "user_reactivated",
    "user_password_changed", "user_plant_access_update",
    # Plants
    "plant_create", "plant_update", "plant_delete", "plant_list_downloaded",
    # Regions
    "region_create", "region_update", "region_delete", "region_reorder",
    # Targets
    "target_update", "target_upload", "target_template_downloaded",
    # Daily volume
    "manual_entry", "erp_sync",
    # Employee details
    "employee_details_updated", "employee_details_bulk_upload",
    # Email
    "email_settings_saved", "smtp_test",
    "zero_vol_alert_sent", "zero_vol_alert_failed", "zero_vol_alert_manual",
    "daily_report_sent", "daily_report_failed", "daily_report_manual",
    # Public API tokens (POST /api/v1/token)
    "api_token_issued", "api_login_failed", "api_login_blocked",
}


@audit_bp.route("/audit-log")
@admin_required
def audit_page():
    """Audit log page. Admin only."""
    return render_template("audit_log.html")


@audit_bp.route("/api/audit-log")
@admin_required
def api_audit_log():
    """
    Get audit log entries with pagination and optional filters.

    Query params:
      - page (default 1)
      - per_page (default 50, max 200)
      - action (filter by action type)
      - username (filter by username)
    """
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    action_filter = request.args.get("action", "").strip()
    username_filter = request.args.get("username", "").strip()[:80]  # cap length

    # Reject unknown action names to prevent probing for undisclosed action types
    if action_filter and action_filter not in VALID_ACTIONS:
        return jsonify({"error": "Invalid action filter"}), 400

    query = AuditLog.query.order_by(AuditLog.created_at.desc())

    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    if username_filter:
        query = query.filter(AuditLog.username.ilike(f"%{username_filter}%"))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "logs": [log.to_dict() for log in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "per_page": per_page,
    })
