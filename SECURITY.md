# Security policy

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Contact the repository owner privately through the GitHub profile or the organization’s established security channel with:

- affected commit or deployment;
- reproduction steps;
- impact and suggested mitigation;
- whether any credentials or business data may have been exposed.

Allow time for a fix before public disclosure.

## Deployment safeguards

- Keep `.env` outside version control and rotate any secret that may have been exposed.
- Use a strong, stable `FLASK_SECRET_KEY` and `SESSION_COOKIE_SECURE=true` behind HTTPS.
- Use least-privilege, read-only Oracle credentials for reporting.
- Restrict MySQL, SMTP, Oracle, and the application port to trusted networks.
- Treat API tokens and database backups as sensitive data.
- The `/r4x8e` prefix is not authentication and must not be used as the only access control.
