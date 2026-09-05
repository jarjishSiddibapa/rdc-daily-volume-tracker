# Operations runbook

## Daily startup check

1. Confirm MySQL is reachable with the configured `.env` values.
2. Start `server.py` and check that the email, ERP sync, and backup scheduler messages appear once.
3. Open `/r4x8e/login` and confirm the login page loads.
4. Check `Logs/server.log` for repeated database or SMTP errors.

## ERP synchronization

ERP synchronization runs every 30 minutes and can also be triggered from the dashboard. It first checks the enabled, inventory-enabled Oracle organization master, then synchronizes recent production and invoicing. Existing active/inactive status and tracker names are preserved. A completely new organization code is created as active and reported in the sync response.

A failed Oracle connection is logged and does not prevent manual-entry workflows. Check `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`, credentials, and (if applicable) `ORACLE_CLIENT_PATH` before retrying.

## Approved active-plant baseline

Use the reconciliation command when an approved Excel list must replace the current active/inactive baseline. Stop the application first so the scheduler cannot overlap the maintenance transaction.

```powershell
# Preview only
python scripts\reconcile_active_plants.py "C:\path\RDC_Updated_Plant_Name.xlsx"

# Commit after reviewing the preview
python scripts\reconcile_active_plants.py "C:\path\RDC_Updated_Plant_Name.xlsx" --apply
```

The command validates the `Updated Plant Name` worksheet and matches rows only by normalized organization code. Listed codes become active and receive the workbook tracker name. Every other existing plant becomes inactive. The command also records every currently enabled ERP organization in MySQL, leaving unlisted organizations inactive, so later syncs can distinguish them from genuinely new organizations. It is idempotent and starts no background scheduler.

## Email alerts and reports

Configure SMTP settings and recipients from Email Settings. Zero-volume and daily-report schedules are stored in MySQL and evaluated every minute in Asia/Kolkata time. If a send fails, inspect the log and correct the SMTP configuration; successful sends are recorded to avoid duplicates.

## Database backups

The backup service writes full SQL exports to the ignored `database-backup/` directory. Configure backup times and maximum retention from Database Backup. Periodically copy approved backups to protected storage; local backup files are not a disaster-recovery system by themselves.

To validate a backup without touching production, restore it into an isolated MySQL database and run the application against that database using a separate `.env`.

## Common symptoms

| Symptom | First checks |
| --- | --- |
| Login redirects repeatedly | Confirm the `/r4x8e` prefix and stable `FLASK_SECRET_KEY`; check session-cookie settings |
| Empty dashboard | Check MySQL connectivity, active plants, selected date, and the latest ERP sync log |
| ERP data unavailable | Check Oracle credentials, DSN values, network access, and thick-mode client path |
| Emails not arriving | Check SMTP settings, recipient configuration, scheduler output, and spam/quarantine |
| Backup missing | Check MySQL access, the configured time zone, retention settings, and filesystem permissions |
| API returns `401` | Issue a new token and send it as `Authorization: Bearer <token>` |

## Incident notes

Record the deployment commit, start time, affected job, log excerpt (redacted), and recovery action. Do not paste passwords, tokens, connection strings, or production volume data into tickets or public issues.
