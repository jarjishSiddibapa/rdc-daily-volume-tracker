"""SQLAlchemy models mapping to existing MySQL tables."""

from app import db
from flask_login import UserMixin


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=False, default="")
    role = db.Column(db.String(20), nullable=False, default="viewer")  # admin, manual_entry, viewer
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.TIMESTAMP, nullable=True)
    manual_entry_all_plants = db.Column(db.Boolean, nullable=False, default=False)
    can_edit_employee_details = db.Column(db.Boolean, nullable=False, default=False)
    can_update_targets = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    @property
    def is_active(self):
        """Flask-Login uses this to check if user is active."""
        return self.is_active_user

    def set_password(self, password):
        from flask_bcrypt import generate_password_hash
        self.password_hash = generate_password_hash(password).decode("utf-8")

    def check_password(self, password):
        from flask_bcrypt import check_password_hash
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email or "",
            "display_name": self.display_name,
            "role": self.role,
            "is_active": self.is_active_user,
            "manual_entry_all_plants": self.manual_entry_all_plants,
            "can_edit_employee_details": self.can_edit_employee_details,
            "can_update_targets": self.can_update_targets,
        }

class UserPlantAccess(db.Model):
    __tablename__ = "user_plant_access"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    plant_code = db.Column(db.String(50), db.ForeignKey("plants.plant_code", ondelete="CASCADE"), primary_key=True)


class Plant(db.Model):
    __tablename__ = "plants"

    plant_code = db.Column(db.String(50), primary_key=True)
    daily_tracker_name = db.Column(db.String(100))
    erp_name = db.Column(db.String(100))
    region = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_manual_entry = db.Column(db.Boolean, nullable=False, default=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    # Relationships
    daily_volumes = db.relationship("PlantDailyVolume", backref="plant", lazy="dynamic")
    monthly_volumes = db.relationship("PlantMonthlyVolume", backref="plant", lazy="dynamic")
    monthly_targets = db.relationship("PlantMonthlyTarget", backref="plant", lazy="dynamic")

    def to_dict(self):
        return {
            "plant_code": self.plant_code,
            "daily_tracker_name": self.daily_tracker_name,
            "erp_name": self.erp_name,
            "region": self.region,
            "is_active": self.is_active,
            "is_manual_entry": self.is_manual_entry,
            "display_order": self.display_order,
        }


class Region(db.Model):
    __tablename__ = "regions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "display_order": self.display_order,
        }


class PlantDailyVolume(db.Model):
    __tablename__ = "plant_daily_volume"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    plant_code = db.Column(
        db.String(50), db.ForeignKey("plants.plant_code", ondelete="CASCADE"), nullable=False
    )
    entry_date = db.Column(db.Date, nullable=False)
    volume = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)
    invoiced_qty = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.UniqueConstraint("plant_code", "entry_date", name="unique_plant_day"),
        db.Index("idx_pdv_entry_date", "entry_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "plant_code": self.plant_code,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "volume": float(self.volume) if self.volume else 0.0,
            "invoiced_qty": float(self.invoiced_qty) if self.invoiced_qty else 0.0,
        }


class PlantMonthlyVolume(db.Model):
    __tablename__ = "plant_monthly_volume"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    plant_code = db.Column(
        db.String(50), db.ForeignKey("plants.plant_code", ondelete="CASCADE"), nullable=False
    )
    month_date = db.Column(db.Date, nullable=False)  # YYYY-MM-01
    total_actual_volume = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.UniqueConstraint("plant_code", "month_date", name="unique_plant_month_vol"),
        db.Index("idx_pmv_month_date", "month_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "plant_code": self.plant_code,
            "month_date": self.month_date.isoformat() if self.month_date else None,
            "total_actual_volume": float(self.total_actual_volume) if self.total_actual_volume else 0.0,
        }


class PlantMonthlyTarget(db.Model):
    __tablename__ = "plant_monthly_target"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    plant_code = db.Column(
        db.String(50), db.ForeignKey("plants.plant_code", ondelete="CASCADE"), nullable=False
    )
    month_date = db.Column(db.Date, nullable=False)  # YYYY-MM-01
    target_volume = db.Column(db.Numeric(15, 2), nullable=False, default=0.00)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.UniqueConstraint("plant_code", "month_date", name="unique_plant_month_target"),
        db.Index("idx_pmt_month_date", "month_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "plant_code": self.plant_code,
            "month_date": self.month_date.isoformat() if self.month_date else None,
            "target_volume": float(self.target_volume) if self.target_volume else 0.0,
        }


class PlantEmployeeDetails(db.Model):
    __tablename__ = "plant_employee_details"

    plant_code = db.Column(
        db.String(50), db.ForeignKey("plants.plant_code", ondelete="CASCADE"), primary_key=True
    )
    on_roll = db.Column(db.Integer, nullable=False, default=0)
    teamlease = db.Column(db.Integer, nullable=False, default=0)
    no_of_tm = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    updated_by = db.Column(db.String(80), nullable=True)

    def to_dict(self):
        return {
            "plant_code": self.plant_code,
            "on_roll": self.on_roll,
            "teamlease": self.teamlease,
            "no_of_tm": self.no_of_tm,
            "updated_at": self.updated_at.strftime("%d-%m-%Y %H:%M") if self.updated_at else None,
            "updated_by": self.updated_by or "",
        }


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = db.Column(db.String(80), nullable=False, default="system")
    action = db.Column(db.String(50), nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), index=True)

    user = db.relationship("User", backref="audit_logs", lazy="select")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "action": self.action,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EmailSettings(db.Model):
    """Single-row config for the daily zero-volume email alert."""
    __tablename__ = "email_settings"

    id = db.Column(db.Integer, primary_key=True)
    smtp_email = db.Column(db.String(255), nullable=True)
    smtp_password = db.Column(db.String(255), nullable=True)  # app password
    smtp_host = db.Column(db.String(255), nullable=False, default="smtp.gmail.com")
    smtp_port = db.Column(db.Integer, nullable=False, default=587)
    to_addresses = db.Column(db.Text, nullable=True)   # comma-separated
    cc_addresses = db.Column(db.Text, nullable=True)   # comma-separated
    signature_html = db.Column(db.Text, nullable=True)  # HTML signature block
    is_enabled = db.Column(db.Boolean, nullable=False, default=False)
    alert_times = db.Column(db.String(255), nullable=False, default="18:00")  # comma-separated HH:MM

    # ── Daily Production Report email config ─────────────────────────────
    report_to_addresses = db.Column(db.Text, nullable=True)
    report_cc_addresses = db.Column(db.Text, nullable=True)
    report_is_enabled = db.Column(db.Boolean, nullable=False, default=False)
    report_alert_times = db.Column(db.String(255), nullable=False, default="18:00")

    # Zero-volume alert options
    zv_include_employee_details = db.Column(db.Boolean, nullable=False, default=True)

    updated_at = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "smtp_email": self.smtp_email or "",
            "smtp_host": self.smtp_host or "smtp.gmail.com",
            "smtp_port": self.smtp_port or 587,
            "to_addresses": self.to_addresses or "",
            "cc_addresses": self.cc_addresses or "",
            "signature_html": self.signature_html or "",
            "is_enabled": self.is_enabled,
            "alert_times": self.alert_times or "18:00",
            "report_to_addresses": self.report_to_addresses or "",
            "report_cc_addresses": self.report_cc_addresses or "",
            "report_is_enabled": self.report_is_enabled,
            "report_alert_times": self.report_alert_times or "18:00",
            "zv_include_employee_details": self.zv_include_employee_details,
            # Never expose smtp_password to the frontend
        }


class EmailAlertLog(db.Model):
    """Records each successfully sent scheduled email alert.

    Used to guarantee exactly-once delivery even across app restarts.
    A row is only inserted after a confirmed successful send, so if the
    app crashes mid-send the row will be absent and the next scheduler
    tick will retry within the configured time window.
    """
    __tablename__ = "email_alert_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 'zv' = zero-volume alert, 'rpt' = daily production report
    alert_type = db.Column(db.String(10), nullable=False)
    # Calendar date the alert is for (today in IST at time of send)
    fire_date = db.Column(db.Date, nullable=False)
    # The configured HH:MM string (e.g. "18:00") — not the actual send time
    fire_time_cfg = db.Column(db.String(5), nullable=False)
    # Actual UTC datetime when the email was successfully sent
    sent_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        # Prevents double-inserts if two scheduler threads race (shouldn't happen
        # with max_instances=1, but this is a hard DB-level safety net).
        db.UniqueConstraint(
            "alert_type", "fire_date", "fire_time_cfg",
            name="uq_email_alert_log_type_date_time",
        ),
    )


class ApiToken(db.Model):
    """Bearer token for external applications reading data via the public /api/v1/ endpoints.

    Only a salted hash of the token is stored — the raw value is shown once,
    at creation time, and cannot be retrieved afterwards.
    """
    __tablename__ = "api_tokens"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    token_prefix = db.Column(db.String(12), nullable=False)  # shown in UI to identify the token
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)  # sha256 hex digest
    scopes = db.Column(db.String(50), nullable=False, default="read")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_used_at = db.Column(db.TIMESTAMP, nullable=True)
    expires_at = db.Column(db.TIMESTAMP, nullable=True)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

    creator = db.relationship("User", backref="api_tokens", lazy="select")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "token_prefix": self.token_prefix,
            "scopes": self.scopes,
            "created_by": self.creator.username if self.creator else None,
            "is_active": self.is_active,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DatabaseBackupSettings(db.Model):
    """Single-row config for scheduled automatic database backups."""
    __tablename__ = "database_backup_settings"

    id          = db.Column(db.Integer, primary_key=True)
    is_enabled  = db.Column(db.Boolean, nullable=False, default=False)
    # Comma-separated HH:MM values, e.g. "02:00,14:00"
    backup_times = db.Column(db.String(255), nullable=False, default="02:00")
    # Keep at most this many backup files on disk
    max_backups  = db.Column(db.Integer, nullable=False, default=30)
    updated_at   = db.Column(
        db.TIMESTAMP,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    def to_dict(self):
        return {
            'id':           self.id or 1,
            'is_enabled':   self.is_enabled,
            'backup_times': self.backup_times or '02:00',
            'max_backups':  self.max_backups  or 30,
        }
