# Changelog

## Unreleased

- Added ERP organization-master discovery so plants appear before their first production transaction.
- Added an idempotent active-plant reconciliation command that matches Excel tracker names by organization code, establishes the approved active/inactive baseline, and preserves it during later ERP syncs.
- Added new-plant details to ERP sync responses and immediate UI notification while keeping existing statuses and tracker names unchanged.
- Added a one-click `start-all.bat` launcher designed for Windows Task Scheduler, including safe `.env` creation and secret generation.
- Added a lightweight, delayed loading-status message alongside the progress animation.
- Added versioned long-term caching and low-CPU gzip for static and dynamic assets.
- Reduced shared-server footprint with configurable Waitress threads, database pool limits, and selective request logging.
- Added a bounded, invalidated report cache for burst dashboard/report traffic.
- Removed continuous smooth-scroll, background, cursor-tilt, ripple, and count-up animation work.
- Added immediate route/API progress, button busy states, skeleton table loading, and reduced-motion support.
- Added an RDC Daily Volume Tracker favicon and conditional date-picker loading.
- Documented the decision to retain Flask instead of performing a low-value framework rewrite.

## 1.0.0 — 2026-08-28

- Published the Flask application, templates, static assets, configuration template, and API reference.
- Added portable Windows startup and Waitress production-style serving.
- Added repository security exclusions and setup documentation.
