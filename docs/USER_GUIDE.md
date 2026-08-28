# User guide

## Sign in

Open `http://localhost:8089/r4x8e/login` (replace the origin for a deployed environment). Enter the account created by an administrator. Sessions expire after 10 minutes of inactivity; sign in again when prompted.

![Login screen](images/login.png)

## Dashboard and reports

The dashboard summarizes production by plant and region. Use the report views for daily, monthly, and yearly comparisons. Data may combine manual entries with the most recent ERP synchronization; the plant metadata indicates which source applies.

## Manual volume entry

Users with the `admin` or `manual_entry` role can open Manual Entry, choose an allowed plant and date, enter the volume, and save. Administrators can grant all-plant access or restrict a user to specific plants. Review the saved date and plant before submitting corrections.

## Analytics and exports

Administrators can use Analytics to switch between produced and invoiced metrics, filter time periods, and export workbook reports. The export reflects the selected filters, so keep a copy of the selection when sharing a report.

## Administration

Administrators manage:

- users, roles, active status, and plant access;
- plants, regions, and display ordering;
- monthly targets and employee details;
- email destinations, alert times, and report schedules;
- backup retention and scheduled backup times;
- audit history and API tokens.

## API access

Create a token from an active user credential using `POST /r4x8e/api/v1/token`, then send `Authorization: Bearer <token>` to the read-only volume endpoints. Tokens expire after 24 hours. The complete request and response reference is [`API_DOCUMENTATION.html`](../API_DOCUMENTATION.html).

![API documentation](images/api-documentation.png)

## Safe operating habits

- Never share `.env`, API tokens, database dumps, or screenshots containing production data.
- Verify the current plant and date before saving manual entries.
- Treat the URL prefix as a route convention, not a security control.
- Use HTTPS and a restricted network path for deployed environments.
