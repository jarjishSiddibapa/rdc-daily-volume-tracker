"""Dashboard and report routes."""

from datetime import date, datetime

from flask import Blueprint, render_template, jsonify, request, send_file
from flask_login import login_required

from app.decorators import manual_entry_required
from app.services.report_generator import generate_report
from app.services.erp_sync import sync_erp_data
from app.services.excel_service import export_report_excel

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    """Dashboard page."""
    return render_template("dashboard.html")


@dashboard_bp.route("/report")
@login_required
def report_page():
    """Report view page."""
    return render_template("report.html")


@dashboard_bp.route("/api/dashboard")
@login_required
def api_dashboard():
    """Get dashboard data (today's report)."""
    date_str = request.args.get("date")
    if date_str:
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        report_date = date.today()

    report = generate_report(report_date)
    return jsonify(report)


@dashboard_bp.route("/api/report")
@login_required
def api_report():
    """Get full report data."""
    date_str = request.args.get("date")
    if date_str:
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        report_date = date.today()

    report = generate_report(report_date)
    return jsonify(report)


@dashboard_bp.route("/api/report/export")
@login_required
def api_report_export():
    """Export report as Excel file."""
    date_str = request.args.get("date")
    if date_str:
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        report_date = date.today()

    report = generate_report(report_date)
    excel_buffer = export_report_excel(report)

    filename = f"Daily_Volume_Report_{report_date.isoformat()}.xlsx"
    return send_file(
        excel_buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@dashboard_bp.route("/api/sync-erp", methods=["POST"])
@manual_entry_required
def api_sync_erp():
    """Trigger ERP data sync. Admin and manual_entry users only."""
    result = sync_erp_data()
    # Only 500 on complete failure (status=error), not partial errors
    if result.get("status") == "error":
        return jsonify(result), 500
    # Partial errors (some plants failed) still return 200 with warnings
    return jsonify(result), 200
