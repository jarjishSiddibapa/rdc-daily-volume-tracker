"""Email service — SMTP connection testing and zero-volume alert emails."""

import html as _html
import logging
import smtplib
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import func

from app import db
from app.models import EmailSettings, Plant, PlantDailyVolume, PlantEmployeeDetails
from app.services.audit import log_action

logger = logging.getLogger(__name__)


def _get_settings() -> EmailSettings | None:
    """Get the singleton EmailSettings row."""
    return db.session.get(EmailSettings, 1)


def _combined_plant_name(plant) -> str:
    """Show both tracker and ERP name: 'TrackerName (ERPName)'."""
    t = (plant.daily_tracker_name or "").strip()
    e = (plant.erp_name or "").strip()
    if t and e and t != e:
        return f"{t} ({e})"
    return t or e or plant.plant_code


def send_password_reset_email(to_email: str, display_name: str, reset_link: str) -> dict:
    """Send a password-reset link to the user using the configured SMTP settings."""
    settings = _get_settings()
    if not settings or not settings.smtp_email or not settings.smtp_password:
        return {"success": False, "message": "SMTP credentials not configured"}

    html = f"""
    <html>
    <body style="font-family: Calibri, Arial, sans-serif; color: #333; line-height: 1.6;">
        <p>Hi {display_name},</p>
        <p>We received a request to reset your Daily Volume Tracker password.</p>
        <p style="margin: 24px 0;">
            <a href="{reset_link}"
               style="background:#1a5276;color:#fff;padding:12px 28px;text-decoration:none;
                      border-radius:6px;font-weight:600;font-size:14px;">
                Reset My Password
            </a>
        </p>
        <p style="font-size:12px;color:#666;">
            This link expires in <strong>1 hour</strong>. If you did not request a reset,
            you can safely ignore this email.
        </p>
        <p style="font-size:12px;color:#888;">
            Or copy this link: {reset_link}
        </p>
        {f'<div style="margin-top:20px;">{settings.signature_html}</div>' if settings.signature_html else ''}
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Daily Volume Tracker — Password Reset Request"
    msg["From"] = settings.smtp_email
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.smtp_email, settings.smtp_password)
        server.sendmail(settings.smtp_email, [to_email], msg.as_string())
        server.quit()
        logger.info(f"Password reset email sent to {to_email}")
        log_action("password_reset_email_sent", {"to": to_email})
        db.session.commit()
        return {"success": True, "message": "Reset email sent"}
    except Exception as exc:
        logger.error(f"Failed to send reset email to {to_email}: {exc}")
        log_action("password_reset_email_failed", {"to": to_email, "error": str(exc)})
        db.session.commit()
        return {"success": False, "message": str(exc)}


def test_smtp_connection(host: str, port: int, email: str, password: str) -> dict:
    """
    Test SMTP connection with the given credentials.
    Returns {"success": True/False, "message": str}
    """
    try:
        server = smtplib.SMTP(host, port, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(email, password)
        server.quit()
        return {"success": True, "message": "SMTP connection successful"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "Authentication failed — check email and app password"}
    except smtplib.SMTPConnectError:
        return {"success": False, "message": f"Could not connect to {host}:{port}"}
    except TimeoutError:
        return {"success": False, "message": f"Connection to {host}:{port} timed out"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


def _build_zero_volume_html(plants: list[dict], report_date: date, signature_html: str,
                            include_employee_details: bool = True) -> str:
    """Build the HTML email body — clean, readable zero-volume alert."""

    date_str   = report_date.strftime("%d-%m-%Y")
    month_name = report_date.strftime("%b %Y")
    count      = len(plants)

    FONT    = "font-family:Calibri,Arial,sans-serif;"
    BD      = "border:1px solid #E2E8F0;"
    TH      = (f"padding:9px 11px;font-size:11.5px;font-weight:700;color:#1E3A5F;"
               f"{BD}{FONT}text-align:center;background:#EEF2F7;")
    TH_L    = TH.replace("text-align:center;", "text-align:left;")
    TD      = f"padding:8px 11px;font-size:12px;{BD}{FONT}color:#374151;vertical-align:middle;text-align:center;"
    TD_L    = TD.replace("text-align:center;", "text-align:left;")
    TD_R    = TD.replace("text-align:center;", "text-align:right;")

    rows_html = ""
    for i, p in enumerate(plants, 1):
        row_bg    = "background:#F8FAFC;" if i % 2 == 0 else "background:#FFFFFF;"
        zero_days = p.get("zero_days_this_month", 0)
        mtd       = p.get("mtd_volume", 0.0)
        per_day   = p.get("per_day_volume", 0.0)
        on_roll   = p.get("on_roll",   0)
        teamlease = p.get("teamlease", 0)
        total_emp = on_roll + teamlease
        no_of_tm  = p.get("no_of_tm",  0)

        emp_cells = (
            f'<td style="{TD}">{on_roll}</td>'
            f'<td style="{TD}">{teamlease}</td>'
            f'<td style="{TD}font-weight:700;color:#1E3A5F;">{total_emp}</td>'
            f'<td style="{TD}">{no_of_tm}</td>'
        ) if include_employee_details else ""

        rows_html += (
            f'<tr style="{row_bg}">'
            f'<td style="{TD}color:#9CA3AF;">{i}</td>'
            f'<td style="{TD}font-weight:700;">{_html.escape(str(p["plant_code"]))}</td>'
            f'<td style="{TD_L}font-weight:600;">{_html.escape(str(p["plant_name"]))}</td>'
            f'<td style="{TD}">{_html.escape(str(p["region"]))}</td>'
            f'<td style="{TD}">{date_str}</td>'
            f'<td style="{TD}font-weight:700;color:#B91C1C;">0</td>'
            f'<td style="{TD_R}">{round(mtd):,}</td>'
            f'<td style="{TD_R}">{round(per_day):,}</td>'
            f'<td style="{TD}font-weight:600;">{zero_days}</td>'
            + emp_cells +
            f'</tr>'
        )

    if signature_html:
        sig_block = (
            '<p style="margin:20px 0 0;font-size:12px;color:#374151;'
            + FONT + '">' + signature_html + '</p>'
        )
    else:
        sig_block = ""

    if include_employee_details:
        emp_group_th = (
            '<th colspan="4" style="padding:7px 11px;font-size:10px;font-weight:700;'
            'letter-spacing:0.08em;text-transform:uppercase;color:#FFFFFF;'
            'background:#14532D;' + BD + 'text-align:center;">Employee &amp; TM Details</th>'
        )
        emp_col_ths = (
            f'<th style="{TH}">Onroll</th>'
            f'<th style="{TH}">Teamlease</th>'
            f'<th style="{TH}">Total Emp.</th>'
            f'<th style="{TH}">No. of TMs</th>'
        )
    else:
        emp_group_th = ""
        emp_col_ths  = ""

    html = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
        f'<body style="margin:0;padding:24px;background:#F1F5F9;{FONT}">'

        # Card
        '<div style="max-width:1050px;margin:0 auto;background:#FFFFFF;'
        'border:1px solid #E2E8F0;border-radius:6px;overflow:hidden;">'

        # Header strip
        f'<div style="background:#1E3A5F;padding:20px 28px;">'
        f'<div style="font-size:11px;color:#93C5FD;letter-spacing:0.1em;'
        f'text-transform:uppercase;margin-bottom:4px;">RDC Concrete &mdash; Daily Volume Tracker</div>'
        f'<div style="font-size:20px;font-weight:700;color:#FFFFFF;">'
        f'Zero Volume Alert &mdash; {date_str}</div>'
        f'<div style="font-size:12px;color:#BFDBFE;margin-top:3px;">'
        f'{count} active plant(s) with no production recorded</div>'
        f'</div>'

        # Body
        '<div style="padding:22px 28px;">'
        f'<p style="margin:0 0 16px;font-size:13px;color:#374151;">'
        f'Dear Team,<br><br>'
        f'The following <strong>{count} plant(s)</strong> reported '
        f'<strong style="color:#B91C1C;">zero production volume</strong> for '
        f'<strong>{date_str}</strong>.</p>'

        # Table
        '<div style="overflow-x:auto;">'
        '<table cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;width:100%;font-size:12px;">'

        # Group header
        '<thead>'
        f'<tr>'
        f'<th colspan="4" style="padding:7px 11px;font-size:10px;font-weight:700;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:#FFFFFF;'
        f'background:#1E3A5F;{BD}text-align:center;">Plant Information</th>'
        f'<th colspan="5" style="padding:7px 11px;font-size:10px;font-weight:700;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:#FFFFFF;'
        f'background:#7F1D1D;{BD}text-align:center;">Production Data</th>'
        + emp_group_th +
        '</tr>'

        # Column headers
        '<tr>'
        f'<th style="{TH}width:36px;">Sr.</th>'
        f'<th style="{TH}">Plant Code</th>'
        f'<th style="{TH_L}">Plant Name</th>'
        f'<th style="{TH}">Area</th>'
        f'<th style="{TH}">Prod Date</th>'
        f'<th style="{TH}color:#B91C1C;">Prod Qty (M3)</th>'
        f'<th style="{TH}text-align:right;">MTD Volume</th>'
        f'<th style="{TH}text-align:right;">Per Day Vol.</th>'
        f'<th style="{TH}">Zero Days<br>({month_name})</th>'
        + emp_col_ths +
        '</tr>'
        '</thead>'

        f'<tbody>{rows_html}</tbody>'
        '</table></div>'

        # Footer note
        '<p style="margin:16px 0 0;font-size:11px;color:#9CA3AF;">'
        'This is an automated alert from the RDC Daily Volume Tracker. '
        'Do not reply to this email.</p>'

        + sig_block +

        '</div>'   # /body padding
        '</div>'   # /card
        '</body></html>'
    )
    return html


def send_zero_volume_alert(target_date: date | None = None, force: bool = False) -> dict:
    """
    Query active plants with zero volume on target_date (default: yesterday),
    then send the HTML alert email.

    Args:
        force: If True, send even if is_enabled is False (for manual "Send Now").

    Returns {"success": bool, "message": str, "count": int}
    """
    settings = _get_settings()
    if not settings:
        return {"success": False, "message": "Email settings not configured", "count": 0}

    if not force and not settings.is_enabled:
        return {"success": False, "message": "Email alerts are disabled", "count": 0}

    if not settings.smtp_email or not settings.smtp_password:
        return {"success": False, "message": "SMTP credentials not set", "count": 0}

    if not settings.to_addresses:
        return {"success": False, "message": "No recipients configured", "count": 0}

    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    # ── Get all active plants ────────────────────────────────────────────
    active_plants = Plant.query.filter_by(is_active=True).order_by(Plant.region, Plant.display_order, Plant.plant_code).all()

    # ── Get plants that HAVE daily volume on target_date ──────────────────
    plants_with_volume = {
        dv.plant_code
        for dv in PlantDailyVolume.query.filter(
            PlantDailyVolume.entry_date == target_date,
            PlantDailyVolume.volume > 0,
        ).all()
    }

    # ── Count days with volume > 0 per plant this month ──────────────────
    month_start = date(target_date.year, target_date.month, 1)
    total_days_so_far = (target_date - month_start).days + 1  # inclusive of target_date

    all_codes = [p.plant_code for p in active_plants]
    nonzero_rows = (
        db.session.query(
            PlantDailyVolume.plant_code,
            func.count(PlantDailyVolume.entry_date).label("nonzero_count"),
        )
        .filter(
            PlantDailyVolume.entry_date >= month_start,
            PlantDailyVolume.entry_date <= target_date,
            PlantDailyVolume.volume > 0,
            PlantDailyVolume.plant_code.in_(all_codes),
        )
        .group_by(PlantDailyVolume.plant_code)
        .all()
    )
    nonzero_count = {r.plant_code: r.nonzero_count for r in nonzero_rows}

    # ── MTD volume per plant this month ──────────────────────────────────
    mtd_rows = (
        db.session.query(
            PlantDailyVolume.plant_code,
            func.sum(PlantDailyVolume.volume).label("mtd_vol"),
        )
        .filter(
            PlantDailyVolume.entry_date >= month_start,
            PlantDailyVolume.entry_date <= target_date,
            PlantDailyVolume.plant_code.in_(all_codes),
        )
        .group_by(PlantDailyVolume.plant_code)
        .all()
    )
    mtd_vol_map = {r.plant_code: float(r.mtd_vol or 0) for r in mtd_rows}

    # ── Employee details map ─────────────────────────────────────────────
    emp_map = {
        d.plant_code: d
        for d in PlantEmployeeDetails.query.all()
    }

    # ── Zero-volume = active plants that either have no record or volume=0 ─
    zero_volume_plants = []
    for p in active_plants:
        if p.plant_code not in plants_with_volume:
            zero_days = total_days_so_far - nonzero_count.get(p.plant_code, 0)
            mtd_volume = mtd_vol_map.get(p.plant_code, 0.0)
            per_day_volume = round(mtd_volume / total_days_so_far, 2) if total_days_so_far > 0 else 0.0
            emp = emp_map.get(p.plant_code)
            zero_volume_plants.append({
                "plant_code": p.plant_code,
                "plant_name": _combined_plant_name(p),
                "region": p.region or "—",
                "zero_days_this_month": zero_days,
                "mtd_volume": round(mtd_volume, 2),
                "per_day_volume": per_day_volume,
                "on_roll":   emp.on_roll   if emp else 0,
                "teamlease": emp.teamlease if emp else 0,
                "no_of_tm":  emp.no_of_tm  if emp else 0,
            })

    if not zero_volume_plants:
        logger.info(f"No zero-volume plants for {target_date}, skipping email.")
        return {"success": True, "message": "No zero-volume plants — no email sent", "count": 0}

    # ── Build and send email ─────────────────────────────────────────────
    html_body = _build_zero_volume_html(
        zero_volume_plants, target_date, settings.signature_html or "",
        include_employee_details=settings.zv_include_employee_details,
    )

    date_str = target_date.strftime("%d-%m-%Y")
    subject = f"⚠️ Zero Volume Alert — {len(zero_volume_plants)} Plant(s) — {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_email
    msg["To"] = settings.to_addresses

    if settings.cc_addresses:
        msg["Cc"] = settings.cc_addresses

    msg.attach(MIMEText(html_body, "html"))

    # Build full recipient list
    all_recipients = [
        addr.strip()
        for addr in (settings.to_addresses or "").split(",")
        if addr.strip()
    ]
    all_recipients += [
        addr.strip()
        for addr in (settings.cc_addresses or "").split(",")
        if addr.strip()
    ]

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.smtp_email, settings.smtp_password)
        server.sendmail(settings.smtp_email, all_recipients, msg.as_string())
        server.quit()

        sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Zero-volume alert sent for {target_date}: {len(zero_volume_plants)} plants")
        log_action("zero_vol_alert_sent", {
            "sent_at": sent_at,
            "report_date": str(target_date),
            "trigger": "manual" if force else "auto",
            "subject": subject,
            "from_address": settings.smtp_email,
            "to_addresses": settings.to_addresses,
            "cc_addresses": settings.cc_addresses or "",
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "recipient_count": len(all_recipients),
            "zero_plant_count": len(zero_volume_plants),
            "zero_plant_codes": [p["plant_code"] for p in zero_volume_plants],
            "total_active_plants": len(active_plants),
            "include_employee_details": settings.zv_include_employee_details,
        })
        db.session.commit()
        return {
            "success": True,
            "message": f"Email sent — {len(zero_volume_plants)} zero-volume plant(s)",
            "count": len(zero_volume_plants),
        }
    except Exception as exc:
        failed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.error(f"Failed to send zero-volume email: {exc}")
        log_action("zero_vol_alert_failed", {
            "failed_at": failed_at,
            "report_date": str(target_date),
            "trigger": "manual" if force else "auto",
            "subject": subject,
            "from_address": settings.smtp_email,
            "to_addresses": settings.to_addresses,
            "cc_addresses": settings.cc_addresses or "",
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "recipient_count": len(all_recipients),
            "zero_plant_count": len(zero_volume_plants),
            "zero_plant_codes": [p["plant_code"] for p in zero_volume_plants],
            "error": str(exc),
        })
        db.session.commit()
        return {"success": False, "message": f"Send failed: {str(exc)}", "count": 0}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DAILY PRODUCTION REPORT EMAIL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_RED = "#DD7E6B"
_YELLOW = "#FFD966"
_GREEN = "#6AA84F"
_WHITE = "#ffffff"


def _budget_color(pct_str: str) -> str:
    """Color based on % extrapolation vs budget: <90 red, 90-100 yellow, >100 green."""
    val = int(pct_str.replace("%", "").replace(",", "").strip() or "0")
    if val < 90:
        return _RED
    elif val <= 100:
        return _YELLOW
    return _GREEN


def _variation_color(pct_str: str) -> str:
    """Color for % variation columns: negative=red, 0-10=yellow, >10=green."""
    val = int(pct_str.replace("%", "").replace(",", "").strip() or "0")
    if val < 0:
        return _RED
    elif val <= 10:
        return _YELLOW
    return _GREEN


def _fmt(num) -> str:
    if num is None:
        return "0"
    val = float(num)
    if val == int(val):
        return f"{int(val):,}"
    formatted = f"{val:.2f}".rstrip('0')
    int_part, dec_part = formatted.split('.')
    return f"{int(int_part):,}.{dec_part}"


def _build_report_html(report: dict, signature_html: str) -> str:
    """Build the HTML daily production report matching the PDF format."""
    meta = report["meta"]
    regions = report["regions"]
    company = report["company_total"]

    yesterday_str = meta["yesterday"]  # YYYY-MM-DD
    dt = datetime.strptime(yesterday_str, "%Y-%m-%d")
    month_label = dt.strftime("%b")

    # Platform-safe day formatting (%-d on Linux, %#d on Windows)
    try:
        day_label = dt.strftime("%-d-%b")
    except ValueError:
        day_label = dt.strftime("%#d-%b")

    hdr = (
        "border:1px solid #999;padding:6px 8px;text-align:center;"
        "font-size:11px;font-weight:700;color:#000;background:#D9D9D9;"
    )
    td = "border:1px solid #ccc;padding:5px 7px;font-size:11px;text-align:right;"
    td_left = "border:1px solid #ccc;padding:5px 7px;font-size:11px;text-align:left;"
    td_center = "border:1px solid #ccc;padding:5px 7px;font-size:11px;text-align:center;"

    # Table header
    table = f"""
    <table style="border-collapse:collapse;width:100%;max-width:1300px;font-family:Calibri,Arial,sans-serif;">
    <thead><tr>
        <th style="{hdr}">Sr.<br>No</th>
        <th style="{hdr}text-align:left;">Plant Name</th>
        <th style="{hdr}">Produced Quantity<br>{day_label}</th>
        <th style="{hdr}">Invoiced Quantity<br>{day_label}</th>
        <th style="{hdr}">Daily<br>Avg</th>
        <th style="{hdr}">Req.<br>Vol/day</th>
        <th style="{hdr}">MTD<br>Volume</th>
        <th style="{hdr}">Extrapol<br>Vol</th>
        <th style="{hdr}">Budget/<br>Target</th>
        <th style="{hdr}">% Extrapolation<br>V/S Budget</th>
        <th style="{hdr}">Last<br>Month</th>
        <th style="{hdr}">% Variation<br>LM v/s CM</th>
        <th style="{hdr}">Last Year<br>{month_label}-Vol</th>
        <th style="{hdr}">% Variation<br>LY v/s CM</th>
    </tr></thead>
    <tbody>
    """

    sr = 0
    for region in regions:
        plants = region["plants"]
        sub = region["subtotal"]

        for p in plants:
            sr += 1
            bg = _budget_color(p["pct_extrap_vs_budget"])
            lm_bg = _variation_color(p["pct_vs_last_month"])
            ly_bg = _variation_color(p["pct_vs_last_year"])
            inv_qty = p.get('invoiced_qty', 0) or 0
            daily_vol = p.get('daily_volume', 0) or 0
            inv_short = daily_vol > 0 and inv_qty < daily_vol
            inv_style = f"{td}background:{bg};color:#C0392B;font-weight:900;" if inv_short else f"{td}background:{bg};"

            table += f"""<tr>
                <td style="{td_center}background:{bg};">{sr}</td>
                <td style="{td_left}background:{bg};font-weight:600;">{_html.escape(p['plant_name'].split(' (')[0])}</td>
                <td style="{td}background:{bg};">{_fmt(p['daily_volume'])}</td>
                <td style="{inv_style}">{_fmt(inv_qty)}</td>
                <td style="{td}background:{bg};">{_fmt(p['daily_avg'])}</td>
                <td style="{td}background:{bg};">{_fmt(p['req_vol_day'])}</td>
                <td style="{td}background:{bg};">{_fmt(p['mtd_volume'])}</td>
                <td style="{td}background:{bg};">{_fmt(p['extrapolated'])}</td>
                <td style="{td}background:{bg};">{_fmt(p['target'])}</td>
                <td style="{td_center}background:{bg};font-weight:700;">{p['pct_extrap_vs_budget']}</td>
                <td style="{td}background:{lm_bg};">{_fmt(p['last_month'])}</td>
                <td style="{td_center}background:{lm_bg};font-weight:700;">{p['pct_vs_last_month']}</td>
                <td style="{td}background:{ly_bg};">{_fmt(p['last_year'])}</td>
                <td style="{td_center}background:{ly_bg};font-weight:700;">{p['pct_vs_last_year']}</td>
            </tr>"""

        # Region subtotal row — skip for Unassigned
        if sub is None:
            continue
        sub_bg = _budget_color(sub["pct_extrap_vs_budget"])
        sub_lm = _variation_color(sub["pct_vs_last_month"])
        sub_ly = _variation_color(sub["pct_vs_last_year"])
        bold = "font-weight:800;font-size:12.5px;"
        reg_td = "border:1px solid #999;padding:7px 8px;text-align:right;"
        reg_td_left = "border:1px solid #999;padding:7px 8px;text-align:left;"
        reg_td_center = "border:1px solid #999;padding:7px 8px;text-align:center;"

        table += f"""<tr>
            <td style="{reg_td_center}{bold}background:{sub_bg};">{sub.get('label','')}</td>
            <td style="{reg_td_left}{bold}background:{sub_bg};letter-spacing:0.04em;text-transform:uppercase;">{sub['region_name']}</td>
            <td style="{reg_td}{bold}background:{sub_bg};">{_fmt(sub['daily_volume'])}</td>
            <td style="{reg_td}{bold}background:{sub_bg};">{_fmt(sub.get('invoiced_qty', 0))}</td>
            <td style="{reg_td}{bold}background:{sub_bg};">{_fmt(sub['daily_avg'])}</td>
            <td style="{reg_td}{bold}background:{sub_bg};">{_fmt(sub['req_vol_day'])}</td>
            <td style="{reg_td}{bold}background:{sub_bg};">{_fmt(sub['mtd_volume'])}</td>
            <td style="{reg_td}{bold}background:{sub_bg};">{_fmt(sub['extrapolated'])}</td>
            <td style="{reg_td}{bold}background:{sub_bg};">{_fmt(sub['target'])}</td>
            <td style="{reg_td_center}{bold}background:{sub_bg};">{sub['pct_extrap_vs_budget']}</td>
            <td style="{reg_td}{bold}background:{sub_lm};">{_fmt(sub['last_month'])}</td>
            <td style="{reg_td_center}{bold}background:{sub_lm};">{sub['pct_vs_last_month']}</td>
            <td style="{reg_td}{bold}background:{sub_ly};">{_fmt(sub['last_year'])}</td>
            <td style="{reg_td_center}{bold}background:{sub_ly};">{sub['pct_vs_last_year']}</td>
        </tr>"""

    # Company total row
    c_bg = _budget_color(company["pct_extrap_vs_budget"])
    c_lm = _variation_color(company["pct_vs_last_month"])
    c_ly = _variation_color(company["pct_vs_last_year"])
    bold = "font-weight:900;"

    table += f"""<tr style="background:#1a5276;color:#fff;">
        <td style="{td_center}{bold}color:#fff;border-color:#1a5276;"></td>
        <td style="{td_left}{bold}color:#fff;border-color:#1a5276;">COMPANY TOTAL</td>
        <td style="{td}{bold}color:#fff;border-color:#1a5276;">{_fmt(company['daily_volume'])}</td>
        <td style="{td}{bold}color:#fff;border-color:#1a5276;">{_fmt(company.get('invoiced_qty', 0))}</td>
        <td style="{td}{bold}color:#fff;border-color:#1a5276;">{_fmt(company['daily_avg'])}</td>
        <td style="{td}{bold}color:#fff;border-color:#1a5276;">{_fmt(company['req_vol_day'])}</td>
        <td style="{td}{bold}color:#fff;border-color:#1a5276;">{_fmt(company['mtd_volume'])}</td>
        <td style="{td}{bold}color:#fff;border-color:#1a5276;">{_fmt(company['extrapolated'])}</td>
        <td style="{td}{bold}color:#fff;border-color:#1a5276;">{_fmt(company['target'])}</td>
        <td style="{td_center}{bold}background:{c_bg};border-color:#1a5276;">{company['pct_extrap_vs_budget']}</td>
        <td style="{td}{bold}background:{c_lm};border-color:#1a5276;">{_fmt(company['last_month'])}</td>
        <td style="{td_center}{bold}background:{c_lm};border-color:#1a5276;">{company['pct_vs_last_month']}</td>
        <td style="{td}{bold}background:{c_ly};border-color:#1a5276;">{_fmt(company['last_year'])}</td>
        <td style="{td_center}{bold}background:{c_ly};border-color:#1a5276;">{company['pct_vs_last_year']}</td>
    </tr>"""

    table += "</tbody></table>"

    report_date_str = dt.strftime("%d-%m-%Y")
    vol_plant = meta.get("vol_per_plant", 0)
    active = meta.get("active_plants", 0)

    html = f"""
    <html><body style="font-family:Calibri,Arial,sans-serif;color:#333;line-height:1.4;">
        <p>Dear All,</p>
        <p>Please find the volume report of <strong>{report_date_str}</strong>.</p>
        <p style="font-size:12px;">{meta.get('summary','')}</p>
        {table}
        <p style="font-size:11px;color:#888;margin-top:16px;">
            This is an automated report from the Daily Volume Tracker.
        </p>
        {f'<div style="margin-top:16px;">{signature_html}</div>' if signature_html else ''}
    </body></html>
    """
    return html


def send_daily_report_email(force: bool = False) -> dict:
    """Send the daily production report email."""
    settings = _get_settings()
    if not settings:
        return {"success": False, "message": "Email settings not configured"}

    if not force and not settings.report_is_enabled:
        return {"success": False, "message": "Report email is disabled"}

    if not settings.smtp_email or not settings.smtp_password:
        return {"success": False, "message": "SMTP credentials not set"}

    to = settings.report_to_addresses
    if not to:
        return {"success": False, "message": "No report recipients configured"}

    # Generate report for today (which looks at yesterday's data)
    from app.services.report_generator import generate_report
    report = generate_report()

    html_body = _build_report_html(report, settings.signature_html or "")

    dt = datetime.strptime(report["meta"]["yesterday"], "%Y-%m-%d")
    date_label = dt.strftime("%d-%m-%Y")

    subject = f"RDC Concrete | {date_label} | {report['meta'].get('summary', f'Daily Production Report — {date_label}')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_email
    msg["To"] = to
    if settings.report_cc_addresses:
        msg["Cc"] = settings.report_cc_addresses

    msg.attach(MIMEText(html_body, "html"))

    all_recipients = [a.strip() for a in to.split(",") if a.strip()]
    all_recipients += [a.strip() for a in (settings.report_cc_addresses or "").split(",") if a.strip()]

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.smtp_email, settings.smtp_password)
        server.sendmail(settings.smtp_email, all_recipients, msg.as_string())
        server.quit()

        sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Daily report email sent for {date_label}")
        log_action("daily_report_sent", {
            "sent_at": sent_at,
            "report_date": date_label,
            "trigger": "manual" if force else "auto",
            "subject": subject,
            "from_address": settings.smtp_email,
            "to_addresses": to,
            "cc_addresses": settings.report_cc_addresses or "",
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "recipient_count": len(all_recipients),
            "active_plant_count": report["meta"].get("active_plants", 0),
            "company_daily_volume": report["company_total"].get("daily_volume", 0),
            "company_mtd_volume": report["company_total"].get("mtd_volume", 0),
            "company_pct_vs_budget": report["company_total"].get("pct_extrap_vs_budget", "—"),
        })
        db.session.commit()
        return {"success": True, "message": f"Report email sent for {date_label}"}
    except Exception as exc:
        failed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.error(f"Failed to send report email: {exc}")
        log_action("daily_report_failed", {
            "failed_at": failed_at,
            "report_date": date_label,
            "trigger": "manual" if force else "auto",
            "subject": subject,
            "from_address": settings.smtp_email,
            "to_addresses": to,
            "cc_addresses": settings.report_cc_addresses or "",
            "smtp_host": settings.smtp_host,
            "smtp_port": settings.smtp_port,
            "recipient_count": len(all_recipients),
            "error": str(exc),
        })
        db.session.commit()
        return {"success": False, "message": f"Send failed: {str(exc)}"}