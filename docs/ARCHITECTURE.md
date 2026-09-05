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
6. Responses include security headers; authenticated and token-authenticated dynamic responses disable browser caching.
7. Versioned static assets are cached for one year and compressible responses use low-CPU gzip.

## Performance model

The primary request path is synchronous because the MySQL and Oracle drivers in this application are synchronous. Report generation uses bulk SQL queries rather than per-plant queries, then keeps up to 16 report dates in a 10-second in-process cache. Known data mutations clear that cache immediately.

Browser work is deliberately small: server-rendered Jinja pages, one shared CSS file, and one dependency-free JavaScript file. Date-picker assets load only on dashboard, report, targets, and analytics pages. Loading feedback uses transform/opacity animation only while a request is active; there is no continuous smooth-scroll or cursor-tracking loop.

Waitress defaults to four threads and SQLAlchemy defaults to five pooled MySQL connections plus five temporary overflow connections. Both values are environment-configurable so this application can coexist with other services on the same host.

## Data flow

```text
Manual entry ────────────────────────────────────────────────┐
Oracle organization master (read-only) ── plant discovery ──┼── MySQL ── analytics/report services ── dashboard/Excel/API
Oracle production/invoicing (read-only) ── volume sync ──────┘

MySQL ── backup service ── database-backup/*.sql (ignored local artifact)
Report/alert services ── SMTP (optional, configured in the admin UI)
```

Manual entries and ERP rows are represented separately so the UI can identify whether a plant is manual or synchronized. Analytics supports both produced and invoiced metrics. Organization discovery does not depend on production transactions: every enabled, inventory-enabled ERP organization is checked in one batch. Existing plant status and tracker names are preserved, while a genuinely new organization code is created as an active plant with its ERP name as the initial tracker name.

## Scheduled jobs

APScheduler starts with the application when `SCHEDULER_ENABLED=true` and checks the following jobs in Asia/Kolkata time:

- Zero-volume alert: checks every minute against configured alert times.
- Daily report email: checks every minute against configured report times.
- ERP synchronization: runs every 30 minutes.
- Database backup: checks every minute against configured backup times and retention.

Failed email sends are not marked as sent, allowing the next scheduler tick to retry. Backup files are created locally and must be protected by filesystem permissions.

Run scheduled jobs in exactly one application process. If additional web instances are introduced later, disable their schedulers or extract scheduling to a dedicated worker to prevent duplicate ERP, email, and backup work.

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

Framework direction is recorded in [ADR 0001](adr/0001-retain-flask-optimize-runtime.md). FastAPI becomes appropriate only if a separately scalable, async-first API is needed and the database/ERP call chain is also converted to non-blocking drivers.
