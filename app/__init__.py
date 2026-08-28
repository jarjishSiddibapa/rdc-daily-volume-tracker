"""Flask application factory for Daily Volume Tracker."""

import os
import secrets
from datetime import timedelta
from urllib.parse import quote_plus
from flask import Flask, session, request as flask_request, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()


def create_app():
    app = Flask(__name__)

    # ── Configuration ────────────────────────────────────────────────────
    # Auto-generate a strong secret key if not properly set
    secret = os.getenv("FLASK_SECRET_KEY", "")
    if not secret or "dev-secret" in secret or "change-in-production" in secret:
        secret = secrets.token_hex(32)
        print(
            "\n[CRITICAL WARNING] FLASK_SECRET_KEY is not set or uses a placeholder.\n"
            "  → A new random key was generated. ALL existing user sessions are now invalid.\n"
            "  → Every restart will log out every user.\n"
            "  → Add a strong, stable key to your .env file:\n"
            "     FLASK_SECRET_KEY=" + secrets.token_hex(32) + "\n"
        )
    app.config["SECRET_KEY"] = secret

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', ''))}@"
        f"{os.getenv('MYSQL_HOST', 'localhost')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DB', 'daily_volume_tracker')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload

    # ── Session Security ─────────────────────────────────────────────────
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=10)
    app.config["SESSION_COOKIE_HTTPONLY"] = True       # JS cannot read session cookie
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"      # Prevent cross-site CSRF
    app.config["SESSION_COOKIE_NAME"] = "__dvt_sess"   # Non-default cookie name
    # Set SESSION_COOKIE_SECURE=true in .env when running behind HTTPS
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

    # ── Extensions ───────────────────────────────────────────────────────
    db.init_app(app)
    bcrypt.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login_page"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"
    login_manager.session_protection = "strong"  # Detect IP/UA change → force re-login

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))

    # ── Security middleware ───────────────────────────────────────────────
    @app.before_request
    def _security_before():
        session.permanent = True  # Reset the 10-min inactivity timer

    @app.after_request
    def _security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Restrict browser features not needed by this app
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        # CSP: allow only known CDNs for scripts/styles/fonts; no inline scripts except
        # the tiny theme-restore snippet in base.html (unsafe-inline needed for that)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.jsdelivr.net; "
            "font-src 'self' fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        # HSTS — tell browsers to always use HTTPS for this origin (1 year)
        if flask_request.is_secure:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        # Prevent caching of authenticated pages (back button leak) and
        # token-authenticated API responses (may contain business data)
        if current_user.is_authenticated or g.get("api_token") is not None:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    # ── Register Blueprints ──────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.plants import plants_bp
    from app.routes.daily_volume import daily_volume_bp
    from app.routes.targets import targets_bp
    from app.routes.users import users_bp
    from app.routes.audit_routes import audit_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(plants_bp)
    app.register_blueprint(daily_volume_bp)
    app.register_blueprint(targets_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(audit_bp)

    from app.routes.email_routes import email_bp
    app.register_blueprint(email_bp)

    from app.routes.regions import regions_bp
    app.register_blueprint(regions_bp)

    from app.routes.employee_routes import employee_bp
    app.register_blueprint(employee_bp)

    from app.routes.analytics import analytics_bp
    app.register_blueprint(analytics_bp)

    from app.routes.backup_routes import backup_bp
    app.register_blueprint(backup_bp)

    from app.routes.api_v1 import api_v1_bp
    app.register_blueprint(api_v1_bp)

    # ── Seed admin user + regions + backup settings on first run ────────
    with app.app_context():
        _seed_admin_user()
        _seed_regions()
        _seed_backup_settings()
        _migrate_plant_display_order()

    # ── Schedule daily zero-volume email at 6 PM IST ─────────────────────
    _start_scheduler(app)

    # ── URL obfuscation: all routes behind a non-obvious prefix ──────────
    app.wsgi_app = _PrefixMiddleware(app.wsgi_app, prefix="/r4x8e")

    return app


class _PrefixMiddleware:
    """WSGI middleware that requires a URL prefix for all routes.

    Makes URLs look like /r4x8e/plants instead of /plants,
    so the purpose isn't obvious from the address bar.
    """

    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")

        # If path starts with prefix, strip it and route normally
        if path.startswith(self.prefix):
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            environ["SCRIPT_NAME"] = self.prefix
            return self.app(environ, start_response)

        # Allow bare /static/ for cached assets
        if path.startswith("/static/"):
            return self.app(environ, start_response)

        # Everything else: redirect to prefixed version
        from werkzeug.wrappers import Response
        location = self.prefix + path
        qs = environ.get("QUERY_STRING", "")
        if qs:
            location += "?" + qs
        resp = Response(status=302, headers={"Location": location})
        return resp(environ, start_response)


def _seed_admin_user():
    """Create the admin user if the users table is empty."""
    from app.models import User

    # Create the users table if it doesn't exist
    db.create_all()

    # Only seed if no users exist at all
    if User.query.first() is not None:
        return

    initial_password = os.getenv("ADMIN_INITIAL_PASSWORD", "")
    if not initial_password:
        initial_password = secrets.token_urlsafe(16)
        print(
            "\n[SETUP] No ADMIN_INITIAL_PASSWORD set in .env — "
            f"generated one-time password: {initial_password}\n"
            "        Change it immediately after first login.\n"
        )

    admin = User(
        username="admin",
        display_name="Administrator",
        role="admin",
        is_active_user=True,
    )
    admin.set_password(initial_password)
    db.session.add(admin)
    db.session.commit()
    print("[OK] Admin user seeded (username: admin)")


def _seed_backup_settings():
    """Seed the database_backup_settings row if it doesn't exist yet."""
    from app.models import DatabaseBackupSettings
    if db.session.get(DatabaseBackupSettings, 1) is None:
        db.session.add(DatabaseBackupSettings(
            id=1, is_enabled=False, backup_times="02:00", max_backups=30
        ))
        db.session.commit()
        print("[OK] Database backup settings seeded (disabled by default)")


def _migrate_plant_display_order():
    """Add display_order column to plants table if it doesn't exist, then initialise values."""
    from sqlalchemy import text
    try:
        db.session.execute(text(
            "ALTER TABLE plants ADD COLUMN display_order INT NOT NULL DEFAULT 0"
        ))
        db.session.commit()
        print("[OK] Added display_order column to plants table")
    except Exception:
        db.session.rollback()
        # Column already exists — that's fine

    # Initialise display_order for any plants still at 0 by assigning sequential
    # numbers within each region (alphabetical by daily_tracker_name as baseline).
    from app.models import Plant
    zero_plants = Plant.query.filter_by(display_order=0).order_by(
        Plant.region, Plant.daily_tracker_name
    ).all()
    if zero_plants:
        region_counter: dict = {}
        for plant in zero_plants:
            r = plant.region or ""
            region_counter[r] = region_counter.get(r, 0) + 1
            plant.display_order = region_counter[r]
        db.session.commit()
        print(f"[OK] Initialised display_order for {len(zero_plants)} plants")


def _seed_regions():
    """Seed regions table from REGION_ORDER if empty."""
    from app.models import Region
    from app.services.report_generator import REGION_ORDER

    if Region.query.first() is not None:
        return

    for i, name in enumerate(REGION_ORDER):
        db.session.add(Region(name=name, display_order=i + 1))
    db.session.commit()
    print(f"[OK] Seeded {len(REGION_ORDER)} regions")


def _start_scheduler(app):
    """Start APScheduler — checks every minute if it's time to send the alert."""
    import os

    # Don't start scheduler in the reloader child process
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' and app.debug:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        ist = pytz.timezone('Asia/Kolkata')

        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = BackgroundScheduler(daemon=True)

        # Run every minute; the job itself checks if current time is within the alert window.
        # misfire_grace_time=300 ensures the job still fires if it was delayed up to 5 min
        # (e.g. after an app restart). max_instances=1 prevents overlapping runs.
        scheduler.add_job(
            func=_check_and_send_email,
            trigger=CronTrigger(minute='*', timezone=ist),
            id='zero_volume_email_check',
            name='Check if email alert is due',
            replace_existing=True,
            kwargs={'app': app},
            misfire_grace_time=300,
            max_instances=1,
        )

        # ERP sync — runs every 30 minutes
        scheduler.add_job(
            func=_run_erp_sync,
            trigger=IntervalTrigger(minutes=30, timezone=ist),
            id='erp_sync_job',
            name='Auto ERP sync every 30 minutes',
            replace_existing=True,
            kwargs={'app': app},
        )

        # DB backup — checks every minute, fires at configured times
        scheduler.add_job(
            func=_check_and_run_backup,
            trigger=CronTrigger(minute='*', timezone=ist),
            id='db_backup_job',
            name='Scheduled database backup',
            replace_existing=True,
            kwargs={'app': app},
            misfire_grace_time=300,
            max_instances=1,
        )

        scheduler.start()
        print("[OK] Email scheduler started (checks every minute for configured alert times)")
        print("[OK] ERP sync scheduler started (runs every 30 minutes)")
    except ImportError:
        print("[WARN] APScheduler not installed -- daily email disabled")
    except Exception as exc:
        print(f"[WARN] Scheduler error: {exc}")


# Track which (alert_type, date, configured_time_str) combos have already fired
_fired_alerts = set()


def _is_within_window(now, alert_time_str: str, window_minutes: int = 5) -> bool:
    """Return True if *now* falls within [alert_time, alert_time + window_minutes)."""
    from datetime import datetime, timedelta
    try:
        hh, mm = alert_time_str.strip().split(":")
        target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        return target <= now < target + timedelta(minutes=window_minutes)
    except Exception:
        return False


def _already_sent(alert_type: str, fire_date, fire_time_cfg: str) -> bool:
    """Return True if this alert was already successfully sent (checks DB).

    Called only when the in-memory cache misses (e.g. after an app restart).
    Inserts the key into _fired_alerts so subsequent minute-ticks are fast.
    """
    global _fired_alerts
    from app.models import EmailAlertLog
    exists = EmailAlertLog.query.filter_by(
        alert_type=alert_type,
        fire_date=fire_date,
        fire_time_cfg=fire_time_cfg,
    ).first() is not None
    if exists:
        # Sync back into memory so we don't hit DB every minute
        _fired_alerts.add((alert_type, fire_date.isoformat(), fire_time_cfg))
    return exists


def _record_sent(alert_type: str, fire_date, fire_time_cfg: str, sent_at) -> None:
    """Persist a successful send to DB and update in-memory cache."""
    global _fired_alerts
    from app.models import EmailAlertLog
    from datetime import timezone
    try:
        log_entry = EmailAlertLog(
            alert_type=alert_type,
            fire_date=fire_date,
            fire_time_cfg=fire_time_cfg,
            sent_at=sent_at.astimezone(timezone.utc).replace(tzinfo=None),
        )
        db.session.add(log_entry)
        db.session.commit()
        _fired_alerts.add((alert_type, fire_date.isoformat(), fire_time_cfg))
    except Exception:
        db.session.rollback()
        # UniqueConstraint violation = another instance already logged it — safe to ignore.
        # Any other error: in-memory mark is not added so it will retry next tick.
        raise


def _check_and_send_email(app):
    """Check if current IST time is within any configured alert window, then send.

    Guarantees exactly-once delivery:
    - Successful sends are recorded in email_alert_log (DB) so they survive restarts.
    - Failed sends are NOT recorded — the next scheduler tick retries automatically
      within the 5-minute window.
    - In-memory _fired_alerts is the fast path; DB is the authoritative source.
    """
    import logging
    import pytz
    from datetime import datetime, timedelta

    logger = logging.getLogger(__name__)

    # 'global' declaration MUST come before any assignment to _fired_alerts.
    # Without it, Python treats the set-comprehension pruning below as a local
    # assignment, making _fired_alerts local for the ENTIRE function scope
    # and causing UnboundLocalError on every read above it.
    global _fired_alerts

    try:
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        today = now.date()
        today_key = today.isoformat()

        with app.app_context():
            from app.models import EmailSettings
            settings = db.session.get(EmailSettings, 1)
            if not settings:
                return

            # ── Zero-volume alert ────────────────────────────────────────
            if settings.is_enabled:
                zv_times = [t.strip() for t in (settings.alert_times or "18:00").split(",") if t.strip()]
                for alert_t in zv_times:
                    mem_key = ("zv", today_key, alert_t)
                    if mem_key in _fired_alerts:
                        continue                          # fast path: already done
                    if not _is_within_window(now, alert_t):
                        continue                          # not our window yet / anymore
                    if _already_sent("zv", today, alert_t):
                        continue                          # DB says sent (after restart)
                    # ── Not yet sent — attempt delivery ──────────────────
                    try:
                        from app.services.email_service import send_zero_volume_alert
                        from datetime import timedelta
                        result = send_zero_volume_alert(target_date=today - timedelta(days=1))
                        _record_sent("zv", today, alert_t, now)
                        print(f"[Email] Zero-volume alert sent (cfg={alert_t} IST): {result}")
                    except Exception as exc:
                        # Send or record failed → do NOT mark as fired → retry next tick
                        logger.error(
                            f"[Email] Zero-volume alert FAILED (cfg={alert_t} IST, "
                            f"will retry): {exc}",
                            exc_info=True,
                        )

            # ── Daily production report ──────────────────────────────────
            if settings.report_is_enabled:
                rpt_times = [t.strip() for t in (settings.report_alert_times or "18:00").split(",") if t.strip()]
                for alert_t in rpt_times:
                    mem_key = ("rpt", today_key, alert_t)
                    if mem_key in _fired_alerts:
                        continue
                    if not _is_within_window(now, alert_t):
                        continue
                    if _already_sent("rpt", today, alert_t):
                        continue
                    try:
                        from app.services.email_service import send_daily_report_email
                        result = send_daily_report_email()
                        _record_sent("rpt", today, alert_t, now)
                        print(f"[Email] Daily report sent (cfg={alert_t} IST): {result}")
                    except Exception as exc:
                        logger.error(
                            f"[Email] Daily report FAILED (cfg={alert_t} IST, "
                            f"will retry): {exc}",
                            exc_info=True,
                        )

            # Prune old in-memory keys (> 2 days) to prevent unbounded growth.
            # 'global _fired_alerts' above makes this assignment safe.
            cutoff = (now - timedelta(days=2)).strftime("%Y-%m-%d")
            _fired_alerts = {k for k in _fired_alerts if k[1] >= cutoff}

    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).error(
            f"_check_and_send_email unhandled exception: {exc}", exc_info=True
        )


def _check_and_run_backup(app):
    """Check if current IST time matches a configured backup window; if so, run it.

    Uses the same exactly-once pattern as _check_and_send_email:
    - In-memory _fired_alerts tracks (type, date, time_cfg) tuples.
    - Successful backups are also recorded in the DB via EmailAlertLog
      (reuses the same table with alert_type='bkp').
    """
    import logging as _log
    _bkp_logger = _log.getLogger(__name__)
    try:
        import pytz
        from datetime import datetime, timedelta
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        today = now.date()

        with app.app_context():
            from app.models import DatabaseBackupSettings
            s = db.session.get(DatabaseBackupSettings, 1)
            if not s or not s.is_enabled:
                return

            times = [t.strip() for t in (s.backup_times or '02:00').split(',') if t.strip()]
            for t_str in times:
                mem_key = ('bkp', today.isoformat(), t_str)
                if mem_key in _fired_alerts:
                    continue
                if not _is_within_window(now, t_str):
                    continue
                if _already_sent('bkp', today, t_str):
                    continue
                try:
                    from app.services.backup_service import create_backup, prune_old_backups
                    result = create_backup()
                    if result['status'] == 'success':
                        prune_old_backups(s.max_backups)
                        _record_sent('bkp', today, t_str, now)
                        print(f"[Backup] Scheduled backup done: {result['filename']}")
                    else:
                        _bkp_logger.error(f"[Backup] Scheduled backup FAILED: {result.get('message')}")
                except Exception as exc:
                    _bkp_logger.error(f"[Backup] Scheduled backup error: {exc}", exc_info=True)
    except Exception as exc:
        import logging as _l
        _l.getLogger(__name__).error(f"_check_and_run_backup error: {exc}", exc_info=True)


def _run_erp_sync(app):
    """Run a full ERP sync — called automatically every 30 minutes."""
    import logging as _logging
    _erp_logger = _logging.getLogger(__name__)
    with app.app_context():
        try:
            from app.services.erp_sync import sync_erp_data
            from datetime import datetime
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            now = datetime.now(ist).strftime("%Y-%m-%d %H:%M IST")
            _erp_logger.info(f"[{now}] Auto ERP sync starting...")
            result = sync_erp_data()
            if result.get("status") == "error":
                _erp_logger.error(f"[{now}] Auto ERP sync FAILED: {result.get('message')}")
            else:
                _erp_logger.info(
                    f"[{now}] Auto ERP sync done — "
                    f"daily:{result['synced_daily']} monthly:{result['synced_monthly']} "
                    f"new_plants:{result['new_plants']} errors:{len(result['errors'])}"
                )
                if result['errors']:
                    for e in result['errors']:
                        _erp_logger.warning(f"ERP sync partial error: {e}")
        except Exception as exc:
            _erp_logger.exception(f"Auto ERP sync unhandled exception: {exc}")
