# Contributing

Recommended environment: Python 3.12, 64-bit.

```sh
python -m venv .venv
# Activate the environment or use the full path to its Python executable.
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python scripts/package_source.py
```

Local tests do not require a Telegram token. Three CDN tests are skipped by default; enable them with `RUN_NETWORK_TESTS=1`.

Verify new export options by decoding real output files and checking their format, dimensions, duration, and alpha channel. For settings changes, verify persistence across restarts and isolation between users. Pull requests should describe the resulting behavior and the checks performed.

Keep bot messages, documentation, and issue reports in English. Internal settings values are persisted, so changing those values requires a migration strategy.

Do not commit `.env`, preference databases, private emoji files, virtual environments, or logs containing tokens. The source packager uses an explicit list of allowed paths and additional checks for credential patterns.
