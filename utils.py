"""Shared setup: load .env and build the auth header used by every script."""

import os
from pathlib import Path

# Load KEY=VALUE lines from .env into the environment (on import).
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _value = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _value.strip().strip('"').strip("'"))

HEADERS = {"X-Lightsage-Api-Key": os.environ["LIGHTSAGE_API_KEY"]}
