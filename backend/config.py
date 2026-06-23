"""
Configuration for the backend.
Loads environment variables from `.env` and controls runtime behavior.
"""

import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

# Data fetching strategy
def _parse_bool_env(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

USE_YFINANCE = _parse_bool_env("USE_YFINANCE", True)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DATA_FETCHER_WARNINGS = True

# Cache settings
CACHE_DIR = os.getenv("CACHE_DIR", "/tmp/dashboard_cache")
CACHE_PRICE_DATA = True
CACHE_DURATION_SECONDS = 300  # 5 minutes

# Data source settings
# DISABLED: Do not use fallback prices - only show real data from yfinance
FALLBACK_TO_DEFAULTS = False
ALLOW_EMPTY_HISTORY = True  # Allow returning empty history instead of failing

# Environment string for logging
ENVIRONMENT = "Host"