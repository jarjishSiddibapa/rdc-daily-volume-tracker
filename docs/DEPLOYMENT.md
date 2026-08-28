# Deployment guide

## Prerequisites

- Python 3.11+
- MySQL 8+
- A read-only Oracle ERP account if ERP synchronization is enabled
- SMTP credentials if email alerts or reports are enabled
- HTTPS termination and a restricted network path for production use

## Install

```powershell
git clone https://github.com/jarjishSiddibapa/rdc-daily-volume-tracker.git
cd rdc-daily-volume-tracker
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create the database before the first application start:

```sql
CREATE DATABASE daily_volume_tracker
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

Copy `.env.example` to `.env` and provide values for the MySQL connection, Flask secret, and (when needed) Oracle connection. Do not put credentials in a service file, screenshot, issue, or commit.

## Oracle connectivity

The application uses `python-oracledb`. Thin mode is the default and needs no local Oracle client. Set `ORACLE_CLIENT_PATH` to an installed Oracle Instant Client directory only when thick mode is required. `ORACLE_HOST`, `ORACLE_PORT`, and `ORACLE_SERVICE` are mandatory when ERP features are used.

## Start modes

Development server:

```powershell
python run.py
```

Production-style local server (Waitress):

```powershell
python server.py
```

Windows helper:

```text
start_app.bat
```

The application listens on port `8089` and uses the `/r4x8e` path prefix. Confirm the health of the deployment by opening `/r4x8e/login` and checking the server log before enabling scheduled email or backup jobs.

## Reverse proxy checklist

1. Terminate TLS at the proxy and forward requests to `127.0.0.1:8089`.
2. Set `SESSION_COOKIE_SECURE=true`.
3. Restrict access to the internal application network or VPN.
4. Preserve the `/r4x8e` prefix; do not expose the application directly on a public interface.
5. Rotate the Flask, MySQL, Oracle, and SMTP credentials independently.
6. Configure filesystem permissions for `Logs/` and `database-backup/`.

## First boot

When the users table is empty, the application seeds an `admin` account. Set `ADMIN_INITIAL_PASSWORD` for a controlled first login, or leave it unset to receive a one-time generated password in the server output. Change the password immediately and remove any temporary setup value from the environment.

## Rollback

Stop the process, deploy the previous Git commit, and start the server again. If a schema change has been applied, restore the database from an approved backup only after confirming the restore target and data-loss window with the database owner.
