# Changelog

## Unreleased

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
