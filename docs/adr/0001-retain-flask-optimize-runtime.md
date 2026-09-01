# ADR 0001: Retain Flask and optimize the current runtime

- Status: Accepted
- Date: 2026-09-01

## Context

RDC Daily Volume Tracker is a server-rendered internal application. Its main latency comes from synchronous MySQL queries, Oracle ERP calls, Excel generation, network transfer, and browser rendering. It runs beside other applications on one server, so predictable memory, connection, and CPU usage matter more than framework benchmark throughput.

The existing Flask routes, Flask-Login decorators, Flask-SQLAlchemy models, Jinja templates, APScheduler jobs, and synchronous Oracle integration would all require adaptation in a FastAPI rewrite. Keeping synchronous database and Oracle calls inside FastAPI would move that blocking work to a thread pool, limiting the practical gain.

## Decision

Retain Flask and Waitress for the current application. Improve the measured hot paths instead:

- cache and compress versioned assets;
- load page-specific vendor assets conditionally;
- remove continuous client-side animation work;
- give every navigation and API action immediate feedback;
- coalesce short bursts of identical report requests;
- bound Waitress threads and SQLAlchemy connections;
- log errors and slow requests instead of every static request.

Adopt FastAPI only for a future independently scalable API when its I/O chain can use async-capable database and external-service clients, or when requirements include high-concurrency streaming, server-sent events, or WebSockets.

## Options considered

### Keep Flask and optimize

Best fit for the existing server-rendered workflows. It delivers the highest immediate performance improvement with the least migration and operational risk.

### Rewrite the whole application in FastAPI

Provides an ASGI-first request model and excellent API tooling, but does not make blocking MySQL/Oracle work asynchronous by itself. Rewriting authentication, templates, routes, background jobs, and deployment would be costly and could increase memory during a staged dual-stack migration.

### Split a new FastAPI service beside Flask

Useful if a new high-concurrency public API emerges. It is unnecessary for the current internal dashboard and would add a second runtime, deployment unit, and connection pool on the shared host.

## Trade-off

Flask remains thread-based and will not match an async-first framework for very high numbers of concurrent idle connections. In return, the application avoids a broad rewrite and keeps a smaller operational footprint for its actual workload.

## Consequences

- Current routes and templates remain compatible.
- Performance work stays focused on queries, caching, transfer size, and interaction latency.
- Scheduled jobs must run in one process only.
- A future FastAPI boundary should be service-level, not a file-by-file framework conversion.

## Action items

- Measure slow requests from production logs.
- Review Waitress threads and database pool limits after observing real concurrency.
- Revisit this decision if async streaming or independently scaled API traffic becomes a requirement.
