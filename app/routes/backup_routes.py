"""Database backup admin routes."""

import os

from flask import Blueprint, render_template, jsonify, request, send_file

from app import db
from app.decorators import admin_required
from app.models import DatabaseBackupSettings
from app.services.backup_service import BACKUP_DIR, create_backup, list_backups, prune_old_backups
from app.services.audit import log_action

backup_bp = Blueprint('backup', __name__)


# ── Page ──────────────────────────────────────────────────────────────────────

@backup_bp.route('/database-backup')
@admin_required
def backup_page():
    return render_template('backup.html')


# ── Settings ──────────────────────────────────────────────────────────────────

@backup_bp.route('/api/backup/settings', methods=['GET'])
@admin_required
def api_get_backup_settings():
    s = db.session.get(DatabaseBackupSettings, 1)
    return jsonify(s.to_dict() if s else DatabaseBackupSettings().to_dict())


@backup_bp.route('/api/backup/settings', methods=['PUT'])
@admin_required
def api_update_backup_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    s = db.session.get(DatabaseBackupSettings, 1)
    if not s:
        s = DatabaseBackupSettings(id=1)
        db.session.add(s)

    if 'is_enabled' in data:
        s.is_enabled = bool(data['is_enabled'])
    if 'backup_times' in data:
        s.backup_times = str(data['backup_times']).strip() or '02:00'
    if 'max_backups' in data:
        s.max_backups = max(1, min(365, int(data['max_backups'])))

    db.session.commit()
    log_action('backup_settings_update', data)
    db.session.commit()
    return jsonify({'status': 'success', 'settings': s.to_dict()})


# ── Run / list / download / delete ───────────────────────────────────────────

@backup_bp.route('/api/backup/run', methods=['POST'])
@admin_required
def api_run_backup():
    result = create_backup()
    if result['status'] == 'success':
        # Prune old backups after a successful manual run too
        s = db.session.get(DatabaseBackupSettings, 1)
        max_keep = s.max_backups if s else 30
        prune_old_backups(max_keep)
        log_action('backup_created', {
            'filename': result['filename'],
            'size_mb':  result['size_mb'],
            'trigger':  'manual',
        })
        db.session.commit()
    return jsonify(result)


@backup_bp.route('/api/backup/list')
@admin_required
def api_list_backups():
    return jsonify({'backups': list_backups()})


@backup_bp.route('/api/backup/download/<path:filename>')
@admin_required
def api_download_backup(filename):
    safe = os.path.basename(filename)
    if not (safe.startswith('daily_volume_tracker_db_backup_') and safe.endswith('.sql')):
        return jsonify({'error': 'Invalid filename'}), 400
    fpath = os.path.join(BACKUP_DIR, safe)
    if not os.path.exists(fpath):
        return jsonify({'error': 'Backup file not found'}), 404
    return send_file(fpath, as_attachment=True, download_name=safe)


@backup_bp.route('/api/backup/delete/<path:filename>', methods=['DELETE'])
@admin_required
def api_delete_backup(filename):
    safe = os.path.basename(filename)
    if not (safe.startswith('daily_volume_tracker_db_backup_') and safe.endswith('.sql')):
        return jsonify({'error': 'Invalid filename'}), 400
    fpath = os.path.join(BACKUP_DIR, safe)
    if not os.path.exists(fpath):
        return jsonify({'error': 'File not found'}), 404
    os.remove(fpath)
    log_action('backup_deleted', {'filename': safe})
    db.session.commit()
    return jsonify({'status': 'success'})
