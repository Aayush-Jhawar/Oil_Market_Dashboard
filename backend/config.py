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

# ── Live 15-minute candle DB location ───────────────────────────────────────
# This DB is written continuously by the I:->local sync and read by the price/
# curve hot path and the paper engine. It MUST live on a LOCAL, non-synced disk:
# a OneDrive/Dropbox client locks the SQLite file while uploading it, which makes
# every write fail with "database is locked" (and previously wedged the whole
# app). Default to a local app-data folder; override with the BARS15_DB_DIR env
# var. The legacy in-repo DB/ folder (which lives under OneDrive) is used only to
# seed the local copy once.
_LEGACY_DB_DIR = str(Path(__file__).resolve().parent.parent / "DB")
_DEFAULT_BARS15_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"),
    "Dashboard_v3", "DB",
)
BARS15_DB_DIR = os.getenv("BARS15_DB_DIR", _DEFAULT_BARS15_DIR)
BARS15_DB_PATH = os.path.join(BARS15_DB_DIR, "bars_15min_latest.db")
# Export to the environment so modules that don't import config can resolve the
# same path via os.environ without an import dependency.
os.environ.setdefault("BARS15_DB_DIR", BARS15_DB_DIR)
os.environ.setdefault("BARS15_DB_PATH", BARS15_DB_PATH)


def ensure_bars15_db_dir() -> str:
    """Create BARS15_DB_DIR and seed bars_15min_latest.db from the legacy in-repo
    DB/ folder on first run. Returns BARS15_DB_DIR. Safe to call repeatedly."""
    try:
        os.makedirs(BARS15_DB_DIR, exist_ok=True)
        if not os.path.exists(BARS15_DB_PATH):
            legacy = os.path.join(_LEGACY_DB_DIR, "bars_15min_latest.db")
            if os.path.exists(legacy):
                import shutil
                shutil.copy2(legacy, BARS15_DB_PATH)
    except Exception:
        pass
    return BARS15_DB_DIR


# Seed/ensure the local DB folder as soon as config is imported, before any
# reader/writer resolves the path.
ensure_bars15_db_dir()