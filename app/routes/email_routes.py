"""Email settings routes — admin-only config for zero-volume alerts."""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for
from flask_login import login_required

from app import db
from app.models import EmailSettings
from app.decorators import admin_required
from app.services.email_service import test_smtp_connection, send_zero_volume_alert, send_daily_report_email
from app.services.audit import log_action

email_bp = Blueprint("email", __name__)


def _get_or_create_settings() -> EmailSettings:
    """Get the singleton row, creating it if absent."""
    settings = db.session.get(EmailSettings, 1)
    if not settings:
        settings = EmailSettings(id=1)
        db.session.add(settings)
        db.session.commit()
    return settings


@email_bp.route("/email-settings")
@admin_required
def email_settings_page():
    """Redirect old URL to zero volume alert."""
    return redirect(url_for("email.zero_volume_alert_page"))


@email_bp.route("/zero-volume-alert")
@admin_required
def zero_volume_alert_page():
    return render_template("zero_volume_alert.html")


@email_bp.route("/daily-report-email")
@admin_required
def daily_report_email_page():
    return render_template("daily_report_email.html")


@email_bp.route("/api/email-settings", methods=["GET"])
@admin_required
def api_get_email_settings():
    """Fetch current email settings (password is never returned)."""
    settings = _get_or_create_settings()
    data = settings.to_dict()
    # Tell frontend if a password is already saved
    data["has_password"] = bool(settings.smtp_password)
    return jsonify(data)


@email_bp.route("/api/email-settings", methods=["POST"])
@admin_required
def api_save_email_settings():
    """Save email settings. SMTP password only saved if test passes."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    settings = _get_or_create_settings()

    # Update fields
    if "smtp_email" in data:
        settings.smtp_email = data["smtp_email"].strip()
    if "smtp_host" in data:
        settings.smtp_host = data["smtp_host"].strip() or "smtp.gmail.com"
    if "smtp_port" in data:
        try:
            settings.smtp_port = int(data["smtp_port"] or 587)
        except (ValueError, TypeError):
            return jsonify({"error": "smtp_port must be a valid integer"}), 400
    if "smtp_password" in data and data["smtp_password"]:
        settings.smtp_password = data["smtp_password"]
    if "to_addresses" in data:
        settings.to_addresses = data["to_addresses"].strip()
    if "cc_addresses" in data:
        settings.cc_addresses = data["cc_addresses"].strip()
    if "signature_html" in data:
        settings.signature_html = data["signature_html"]
    if "is_enabled" in data:
        settings.is_enabled = bool(data["is_enabled"])
    if "alert_times" in data:
        settings.alert_times = data["alert_times"].strip() or "18:00"
    # Report email fields
    if "report_to_addresses" in data:
        settings.report_to_addresses = data["report_to_addresses"].strip()
    if "report_cc_addresses" in data:
        settings.report_cc_addresses = data["report_cc_addresses"].strip()
    if "report_is_enabled" in data:
        settings.report_is_enabled = bool(data["report_is_enabled"])
    if "report_alert_times" in data:
        settings.report_alert_times = data["report_alert_times"].strip() or "18:00"
    if "zv_include_employee_details" in data:
        settings.zv_include_employee_details = bool(data["zv_include_employee_details"])

    try:
        db.session.commit()
        log_action("email_settings_saved", {
            "zero_vol_enabled": settings.is_enabled,
            "zero_vol_times": settings.alert_times,
            "report_enabled": settings.report_is_enabled,
            "report_times": settings.report_alert_times,
        })
        db.session.commit()
        return jsonify({"status": "success", "message": "Settings saved"})
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 500


@email_bp.route("/api/email-settings/test", methods=["POST"])
@admin_required
def api_test_smtp():
    """Test SMTP connection with provided credentials."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data"}), 400

    host = data.get("smtp_host", "smtp.gmail.com").strip()
    try:
        port = int(data.get("smtp_port", 587))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "smtp_port must be a valid integer"}), 400
    email = data.get("smtp_email", "").strip()
    password = data.get("smtp_password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required"})

    result = test_smtp_connection(host, port, email, password)
    log_action("smtp_test", {
        "success": result["success"],
        "host": host,
        "port": port,
        "email": email,
    })
    db.session.commit()
    return jsonify(result)


@email_bp.route("/api/email-settings/send-now", methods=["POST"])
@admin_required
def api_send_now():
    """Manually trigger the zero-volume alert email."""
    result = send_zero_volume_alert(force=True)
    log_action("zero_vol_alert_manual", {
        "success": result["success"],
        "plant_count": result.get("count", 0),
        "message": result.get("message", ""),
    })
    db.session.commit()
    return jsonify(result)


@email_bp.route("/api/email-settings/send-report-now", methods=["POST"])
@admin_required
def api_send_report_now():
    """Manually trigger the daily production report email."""
    result = send_daily_report_email(force=True)
    log_action("daily_report_manual", {
        "success": result["success"],
        "message": result.get("message", ""),
    })
    db.session.commit()
    return jsonify(result)
