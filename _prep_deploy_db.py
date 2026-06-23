"""Prepare a self-contained copy of the 15-min candle DB for HF deployment.

The live file (DB/bars_15min_latest.db) is WAL-mode and its -wal sidecar holds
uncommitted rows. We copy it (never touching the live original), fold the WAL in,
and switch journal mode to DELETE so the result is a single self-contained file
that ships cleanly to the Space. fast_deploy.py uploads this as
DB/bars_15min_latest.db on the repo.
"""
import os
import shutil
import sqlite3

SRC = os.path.join("DB", "bars_15min_latest.db")
TMP = os.path.join("DB", "bars_15min_deploy.db")


def main():
    if not os.path.exists(SRC):
        raise SystemExit(f"source DB not found: {SRC}")

    shutil.copy2(SRC, TMP)
    for ext in ("-wal", "-shm"):
        if os.path.exists(SRC + ext):
            shutil.copy2(SRC + ext, TMP + ext)

    con = sqlite3.connect(TMP)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA journal_mode=DELETE")
    con.commit()
    con.close()

    for ext in ("-wal", "-shm"):
        if os.path.exists(TMP + ext):
            os.remove(TMP + ext)

    con = sqlite3.connect(TMP)
    tables = con.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    cl = con.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name LIKE 'CL_%'"
    ).fetchone()[0]
    co = con.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name LIKE 'CO_%'"
    ).fetchone()[0]
    con.close()

    size_mb = round(os.path.getsize(TMP) / 1024 / 1024, 2)
    print(f"OK checkpointed -> {TMP} ({size_mb} MB) tables={tables} CL={cl} CO={co}")


if __name__ == "__main__":
    main()
