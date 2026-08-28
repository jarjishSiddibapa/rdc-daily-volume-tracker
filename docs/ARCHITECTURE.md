# Architecture

## Responsibilities

RDC Daily Volume Tracker is a server-rendered Flask application with a small browser-side JavaScript layer. The application is intentionally organized around operational workflows rather than a separate frontend build system.

```text
app/
├── __init__.py          application factory, security headers, scheduler
├── models.py            SQLAlchemy models and serialization helpers
├── decorators.py        session, role, and API-token guards
├── routes/              HTML pages and JSON endpoints
├── services/            reporting, ERP, email, backup, audit, and Excel logic
├── templates/           Jinja pages and email templates
└── static/              CSS and browser interactions
```

## Request flow

1. A browser or API client sends a request to the fixed `/r4x8e` prefix.
2. `_PrefixMiddleware` strips the prefix before Flask routing and redirects bare paths to the prefixed URL.
3. Web routes use Flask-Login and role decorators. API routes use `Authorization: Bearer <token>` and always return JSON errors.
4. Route handlers call focused service modules for calculations, exports, synchronization, email, or backup work.
5. SQLAlchemy reads and writes MySQL. Oracle queries are isolated in `oracle_service.py` and are used by the ERP synchronization service.
6. Responses include security headers; authenticated and token-authenticated responses disable browser caching.

## Data flow

```text
Manual entry ───────────────┐
                            ├── MySQL ── analytics/report services ── dashboard/Excel/API
Oracle ERP (read-only) ─ ERP sync ─┘

MySQL ── backup service ── database-backup/*.sql (ignored local artifact)
Report/alert services ── SMTP (optional, configured in the admin UI)
```

Manual entries and ERP rows are represented separately so the UI can identify whether a plant is manual or synchronized. Analytics supports both produced and invoiced metrics.

## Scheduled jobs

APScheduler starts with the application and checks the following jobs in Asia/Kolkata time:

- Zero-volume alert: checks every minute against configured alert times.
- Daily report email: checks every minute against configured report times.
- ERP synchronization: runs every 30 minutes.
- Database backup: checks every minute against configured backup times and retention.

Failed email sends are not marked as sent, allowing the next scheduler tick to retry. Backup files are created locally and must be protected by filesystem permissions.

## Security boundaries

- Secrets are loaded from `.env`, which is ignored by Git.
- Passwords are hashed with Flask-Bcrypt; API tokens are stored hashed and expire after 24 hours.
- Login and API-token issuance have in-memory brute-force lockout tracking.
- Admin-only routes protect user, region, plant, email, audit, and backup configuration.
- The URL prefix is routing hygiene, not authentication. Put deployments behind HTTPS and a network access boundary.

## Extension points

- Add a page or JSON route under `app/routes/` and register its blueprint in `create_app()`.
- Add reusable business logic under `app/services/`; keep route functions thin.
- Add a model in `app/models.py`, then document any schema migration or compatibility behavior.
- Add API fields only with a backwards-compatible response note in `API_DOCUMENTATION.html`.
