# User guide

This guide covers the normal operator, viewer, and administrator workflows in RDC Daily Volume Tracker. Screen names can vary by role because the navigation hides features the current account cannot use.

> Screenshots use fictional plants and volumes created only for documentation. Never publish screenshots from a live environment without reviewing them for sensitive business data.

## Sign in

Open `http://localhost:8089/r4x8e/login`, replacing the origin for a deployed environment. Enter the username or email and password provided by an administrator.

![RDC DVT sign-in screen](images/login.jpg)

Web sessions expire after 10 minutes of inactivity. If a page returns to sign-in, authenticate again and repeat any unsaved action. Repeated failed attempts temporarily lock sign-in for that account and client address.

## Understand your access

| Role | Typical workflow |
| --- | --- |
| `admin` | Full reporting, configuration, synchronization, exports, audit, user management, email, and backup access |
| `manual_entry` | Enter and correct volumes for all or specifically assigned plants |
| `viewer` | Read dashboards and reports without modifying operational data |

A manual-entry account can also receive separate permissions for monthly targets and employee details. Plant access can be unrestricted or limited to selected plants.

## Dashboard

The dashboard is the daily operating view. Select a date to compare plants and areas across:

- produced and invoiced volume;
- daily and month-to-date target attainment;
- the previous month and previous year;
- plant, area, and portfolio totals;
- the source and freshness of synchronized data.

![Daily production dashboard](images/dashboard.jpg)

Use **ERP Sync** only when you are authorized to refresh Oracle-backed plants. Synchronization is read-only against Oracle and updates the application’s MySQL reporting data. Manual plants remain editable through Manual Entry.

## Manual volume entry

Open **Manual Entry**, choose an allowed plant, and use the appropriate workflow.

### Enter a single day

1. Select the date.
2. Enter the volume in CUM.
3. Review the plant and date.
4. Save the entry.

### Review or correct up to 30 days

1. Open the 30-day editor for a plant.
2. Review each date and existing value.
3. Enter or correct the necessary values.
4. Select **Save All** once the month is ready.

![Thirty-day manual volume editor](images/manual-entry.jpg)

Use `0` only when it is a real operational value. Do not use zero as a placeholder for missing information because zero-volume alerts treat it as reported production.

## Targets

Open **Targets** and select the target month. Authorized users can update values inline or import a workbook.

![Monthly target planning](images/targets.jpg)

For an Excel import:

1. Download the target template from the page.
2. Keep plant codes unchanged so rows can be matched safely.
3. Enter the monthly target values.
4. Upload the completed workbook.
5. Review the resulting table before leaving the page.

Target changes affect dashboard and report comparisons for the selected month. If a target appears missing, confirm both the month and the plant’s active status.

## Reports and analytics

Use **Report** for operational daily, monthly, and yearly summaries. Use **Analytics** for flexible comparisons and exports.

The day-wise analytics flow is:

1. Choose a quick range or set From and To dates.
2. Optionally filter the plant list.
3. Switch between **Production** and **Invoiced**.
4. Choose whether plants with no data should be hidden.
5. Select **Load Report**.
6. Select **Export Excel** to download the same filtered result.

![Day-wise production analytics](images/analytics.jpg)

The day-wise view is intended for ranges up to 92 days. Use **Monthly Summary** for longer periods. Exports include the current metric, dates, and plant selection, so verify those controls before sharing a workbook.

## Areas, plants, employees, and territory managers

Administrators use **Areas** and **Plants** to keep the reporting hierarchy accurate. Plant codes should remain stable because ERP synchronization, target imports, manual entries, and exports use them as operational identifiers. Display order controls how areas and plants appear throughout the product.

Use **Employee & TM** to maintain the employee and territory-manager information associated with plants. A manual-entry user sees this feature only when the specific employee-details permission is enabled.

## User administration

Administrators can:

- create and edit users;
- select `admin`, `manual_entry`, or `viewer` access;
- activate or deactivate an account;
- grant all-plant or selected-plant access;
- grant target and employee-detail permissions where appropriate;
- review sensitive changes in **Audit Log**.

Deactivate an account that should no longer sign in instead of reusing it for another person. Each person should have an individual account so audit records remain meaningful.

## Zero-volume alerts

Open **Zero Vol Alert** to configure alert recipients and scheduled times. The scheduler evaluates enabled times in Asia/Kolkata and sends the current zero-volume result through the configured SMTP connection.

If an alert is missing, an administrator should confirm the enabled schedule, recipients, SMTP settings, application scheduler, and server log. A failed send is left eligible for retry; a successful send is recorded to prevent duplicates.

## Daily report email

Open **Daily Report** to maintain recipients and delivery times for scheduled operational reports. Keep the application scheduler enabled in exactly one running process. Enabling it in multiple instances can duplicate ERP, report, alert, and backup work.

## Database backups

Open **DB Backup** to configure backup times and retention. Backups are written as SQL files under the local ignored `database-backup/` directory.

Local backups must be protected with filesystem permissions and copied to approved protected storage. Test restores against an isolated MySQL database; never test a restore over the live database.

## API access

The integration API is read-only and exposes daily, monthly, and yearly volume data.

1. Request a token with an active application username and password at `POST /r4x8e/api/v1/token`.
2. Send the returned value as `Authorization: Bearer <token>`.
3. Request the required volume endpoint.
4. Issue a new token after its 24-hour expiry.

![RDC DVT API reference](images/api-documentation.jpg)

The complete endpoint list, parameters, requests, and responses are in [`API_DOCUMENTATION.html`](../API_DOCUMENTATION.html). Treat a token like a password and never place it in a repository, screenshot, shared workbook, or issue.

## Safe operating checklist

- Verify the selected plant, date, month, and metric before saving or exporting.
- Keep `.env`, API tokens, database dumps, logs, and Oracle connection details private.
- Use HTTPS and a trusted network or VPN for deployed environments.
- Treat `/r4x8e` as a route prefix, not as a security boundary.
- Report unexplained data changes with the affected plant, date, and approximate time so an administrator can check the audit and server logs.

For startup, deployment, backup validation, and troubleshooting, see the [operations runbook](OPERATIONS.md) and [deployment guide](DEPLOYMENT.md).
