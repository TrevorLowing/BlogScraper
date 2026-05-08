# Contributing

## Development Setup

- Use Python 3.11+
- Install deps with `pip install -r requirements.txt`
- Run tests with `pytest -q`

## Code Guidelines

- Keep changes focused and small where possible
- Add or update tests for behavior changes
- Prefer configuration via environment variables over hardcoded values
- Never commit secrets (`local.settings.json`, keys, connection strings)

## Pull Request Expectations

- Include a clear description of why the change is needed
- Call out any operational/deployment impact
- Ensure tests pass locally before opening a PR
- Update docs (`README.md`, `CHANGELOG.md`, and relevant markdown files) when behavior changes

## Suggested Commit Style

- `add: ...` for new capabilities
- `update: ...` for enhancements
- `fix: ...` for bug fixes
- `docs: ...` for documentation-only changes
