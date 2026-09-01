# Contributing

## Workflow

1. Create a focused branch from `main`.
2. Keep changes small and explain the user-visible impact in the pull request.
3. Use a local `.env`; never commit secrets, exports, backups, logs, or generated analysis.
4. Update the relevant documentation when routes, configuration, roles, or operational behavior changes.
5. Run the validation commands below before opening a pull request.

## Validation

```powershell
python -m compileall -q app run.py server.py
python -m unittest discover -s tests -v
python -m pip check
```

The documentation tests verify that public links resolve and that portfolio screenshots remain valid, high-resolution JPEG files.

If you change code, refresh the local Graphify code graph with `graphify update .` as described in `AGENTS.md` for the maintainer workspace.

## Pull requests

Include:

- a short problem statement and solution summary;
- configuration or schema changes;
- screenshots for meaningful UI changes, with production data redacted;
- validation commands and results;
- rollout or rollback notes for operational changes.
