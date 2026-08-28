"""
Database backup service — pure Python (no mysqldump dependency).

Generates a complete .sql file with DROP/CREATE TABLE statements and
INSERT rows for every table. Handles all common column types safely.
"""

import os
import logging
from datetime import datetime, date, time as ttime
from decimal import Decimal

import pymysql
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Absolute path to the backup directory (project_root/database-backup/)
_HERE = os.path.dirname(os.path.abspath(__file__))          # app/services/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))     # project root
BACKUP_DIR = os.path.join(_PROJECT_ROOT, 'database-backup')


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_db_config() -> dict:
    return {
        'host':     os.getenv('MYSQL_HOST', 'localhost'),
        'port':     int(os.getenv('MYSQL_PORT', '3306')),
        'user':     os.getenv('MYSQL_USER', 'root'),
        'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DB', 'daily_volume_tracker'),
        'charset':  'utf8mb4',
    }


def _escape(val) -> str:
    """Convert any Python value into a MySQL-safe literal."""
    if val is None:
        return 'NULL'
    if isinstance(val, bool):
        return '1' if val else '0'
    if isinstance(val, (int, float, Decimal)):
        return str(val)
    if isinstance(val, datetime):
        return "'" + val.strftime('%Y-%m-%d %H:%M:%S') + "'"
    if isinstance(val, date):
        return "'" + val.strftime('%Y-%m-%d') + "'"
    if isinstance(val, ttime):
        return "'" + val.strftime('%H:%M:%S') + "'"
    if isinstance(val, bytes):
        return '0x' + val.hex()
    s = str(val)
    s = s.replace('\\', '\\\\')
    s = s.replace("'",  "\\'")
    s = s.replace('\x00', '\\0')
    return "'" + s + "'"


# ── public API ────────────────────────────────────────────────────────────────

def create_backup(backup_dir: str = None) -> dict:
    """
    Write a full SQL backup to backup_dir (defaults to BACKUP_DIR).

    Returns:
        {'status': 'success', 'filename': ..., 'filepath': ...,
         'size_mb': ..., 'table_count': ..., 'timestamp': ...}
        or
        {'status': 'error', 'message': ...}
    """
    backup_dir = backup_dir or BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)

    cfg  = _get_db_config()
    now  = datetime.now()
    name = f"daily_volume_tracker_db_backup_{now.strftime('%H%M_%d%m%Y')}.sql"
    path = os.path.join(backup_dir, name)

    try:
        conn = pymysql.connect(**cfg)
        cur  = conn.cursor()

        with open(path, 'w', encoding='utf-8') as f:

            # ── File header ──────────────────────────────────────────────
            f.write('-- =====================================================\n')
            f.write('-- Daily Volume Tracker — Full Database Backup\n')
            f.write(f'-- Generated : {now.strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'-- Database  : {cfg["database"]}\n')
            f.write(f'-- Host      : {cfg["host"]}:{cfg["port"]}\n')
            f.write('-- =====================================================\n\n')
            f.write('SET NAMES utf8mb4;\n')
            f.write('SET FOREIGN_KEY_CHECKS=0;\n')
            f.write('SET SQL_MODE="NO_AUTO_VALUE_ON_ZERO";\n\n')
            f.write(f'CREATE DATABASE IF NOT EXISTS `{cfg["database"]}`\n')
            f.write('  DEFAULT CHARACTER SET utf8mb4\n')
            f.write('  DEFAULT COLLATE utf8mb4_unicode_ci;\n')
            f.write(f'USE `{cfg["database"]}`;\n\n')

            # ── Tables ───────────────────────────────────────────────────
            cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
            tables = [r[0] for r in cur.fetchall()]

            for tbl in tables:
                f.write(f'-- ── `{tbl}` ────────────────────────────────────\n')
                f.write(f'DROP TABLE IF EXISTS `{tbl}`;\n')

                cur.execute(f'SHOW CREATE TABLE `{tbl}`')
                f.write(cur.fetchone()[1] + ';\n\n')

                cur.execute(f'SELECT COUNT(*) FROM `{tbl}`')
                row_count = cur.fetchone()[0]
                if row_count == 0:
                    continue

                cur.execute(f'DESCRIBE `{tbl}`')
                cols     = [r[0] for r in cur.fetchall()]
                col_list = '`,`'.join(cols)

                cur.execute(f'SELECT * FROM `{tbl}`')
                rows = cur.fetchall()

                # Write in chunks of 500 rows to keep line lengths manageable
                CHUNK = 500
                for i in range(0, len(rows), CHUNK):
                    chunk = rows[i:i + CHUNK]
                    val_rows = [
                        '(' + ','.join(_escape(v) for v in row) + ')'
                        for row in chunk
                    ]
                    f.write(f'INSERT INTO `{tbl}` (`{col_list}`) VALUES\n')
                    f.write(',\n'.join(val_rows) + ';\n')
                f.write('\n')

            f.write('SET FOREIGN_KEY_CHECKS=1;\n')
            f.write(f'-- Backup complete: {len(tables)} tables\n')

        cur.close()
        conn.close()

        size = os.path.getsize(path)
        logger.info(f"Backup created: {name}  ({size / 1024 / 1024:.2f} MB)")
        return {
            'status':      'success',
            'filename':    name,
            'filepath':    path,
            'size_mb':     round(size / 1024 / 1024, 2),
            'table_count': len(tables),
            'timestamp':   now.isoformat(),
        }

    except Exception as exc:
        logger.error(f"Backup failed: {exc}", exc_info=True)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        return {'status': 'error', 'message': str(exc)}


def list_backups(backup_dir: str = None) -> list:
    """Return list of backup dicts sorted newest-first."""
    backup_dir = backup_dir or BACKUP_DIR
    if not os.path.exists(backup_dir):
        return []
    files = []
    for fname in os.listdir(backup_dir):
        if fname.startswith('daily_volume_tracker_db_backup_') and fname.endswith('.sql'):
            fpath = os.path.join(backup_dir, fname)
            stat  = os.stat(fpath)
            files.append({
                'filename':   fname,
                'filepath':   fpath,
                'size_mb':    round(stat.st_size / 1024 / 1024, 2),
                'created_at': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            })
    files.sort(key=lambda x: x['created_at'], reverse=True)
    return files


def prune_old_backups(max_keep: int, backup_dir: str = None) -> list:
    """Delete backups beyond max_keep (oldest first). Returns deleted filenames."""
    backups = list_backups(backup_dir)
    to_delete = backups[max_keep:]
    deleted   = []
    for b in to_delete:
        try:
            os.remove(b['filepath'])
            deleted.append(b['filename'])
            logger.info(f"Pruned old backup: {b['filename']}")
        except Exception as e:
            logger.warning(f"Could not delete {b['filename']}: {e}")
    return deleted
