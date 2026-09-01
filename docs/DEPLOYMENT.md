# Deployment guide

## Prerequisites

- Python 3.11+
- MySQL 8+
- A read-only Oracle ERP account if ERP synchronization is enabled
- SMTP credentials if email alerts or reports are enabled
- HTTPS termination and a restricted network path for production use

## Install

### Matching Windows server: copy-based deployment

When the production machine is a replica of the development machine, the shortest safe deployment is:

1. Copy the project folder to its permanent production path. Exclude `venv/`, `Logs/`, `database-backup/`, `.git/`, and any exported reports.
2. Copy the production `.env` into the project root. Do not place it in Git or send it through an unapproved channel.
3. Copy Oracle Instant Client to the same path used on development, or update `ORACLE_CLIENT_PATH` in `.env` to its production path. Thin mode needs no client folder.
4. Confirm that Python, MySQL, the database name, and the existing database account are available on the production machine.
5. Run `start-all.bat`. It creates `venv`, installs the pinned dependencies, and starts Waitress.
6. Open `/r4x8e/login`, sign in, and verify one dashboard/report request before adding `start-all.bat` to Task Scheduler.

Do not copy the development virtual environment: installed scripts contain machine-specific paths. Do not copy a development database over an existing production database. Database transfer, when actually required, should use an approved backup-and-restore process with a confirmed target.

### Git-based installation

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
start-all.bat
```

The application listens on port `8089` and uses the `/r4x8e` path prefix by default. Confirm the health of the deployment by opening `/r4x8e/login` and checking the server log before enabling scheduled email or backup jobs.

### Windows Task Scheduler

Use the repository-root `start-all.bat` as the task's **Program/script**. It resolves the project directory itself, creates a missing `.env` from `.env.example`, generates a strong Flask secret, prepares a missing virtual environment, installs missing dependencies, and runs the Waitress `server.py` entry point in the foreground. A newly created `.env` must have its placeholder MySQL settings replaced before the launcher will start the server. Keeping the server in the foreground lets Task Scheduler correctly track whether the application is still running.

In the task settings, select **Do not start a new instance** when the task is already running. The launcher records startup failures and redirected server output in `Logs/launcher.log`; the application continues to write its normal rotating log to `Logs/server.log`.

## Shared-server sizing

Start with the provided defaults:

```dotenv
WAITRESS_THREADS=4
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
REPORT_CACHE_SECONDS=10
LOG_ALL_REQUESTS=false
SLOW_REQUEST_MS=750
HEARTBEAT_ENABLED=false
```

Four threads match Waitress's conservative footprint and are sufficient for typical internal dashboard concurrency. Increase threads only when measurement shows queued requests and the database still has connection headroom. Keep the database pool bounded across all applications on the host.

Static assets are fingerprinted and cached for one year. Flask-Compress provides low-level gzip when Waitress is served directly. If a reverse proxy performs compression, it may own compression instead, but verify `Content-Encoding` and avoid compressing the same response twice.

`SCHEDULER_ENABLED` must be `true` in exactly one instance of this application. Set it to `false` in additional instances to prevent duplicate jobs.

## Reverse proxy checklist

1. Terminate TLS at the proxy and forward requests to `127.0.0.1:8089`.
2. Set `SESSION_COOKIE_SECURE=true`.
3. Restrict access to the internal application network or VPN.
4. Preserve the `/r4x8e` prefix; do not expose the application directly on a public interface.
5. Rotate the Flask, MySQL, Oracle, and SMTP credentials independently.
6. Configure filesystem permissions for `Logs/` and `database-backup/`.
7. Enable gzip or Brotli at the proxy and verify caching for `/static/` responses.
8. Monitor slow requests at the `SLOW_REQUEST_MS` threshold before increasing worker or pool sizes.

## First boot

When the users table is empty, the application seeds an `admin` account. Set `ADMIN_INITIAL_PASSWORD` for a controlled first login, or leave it unset to receive a one-time generated password in the server output. Change the password immediately and remove any temporary setup value from the environment.

## Rollback

Stop the process, deploy the previous Git commit, and start the server again. If a schema change has been applied, restore the database from an approved backup only after confirming the restore target and data-loss window with the database owner.
