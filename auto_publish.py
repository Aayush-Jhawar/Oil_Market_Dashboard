"""
auto_publish.py — keep the Hugging Face Space in sync with the local data feed.

Each cycle it:
  1. Syncs the auto-updating candle DB from the I: drive into DB/bars_15min_latest.db
     (the same copy main.py's scheduler does, but standalone so it runs without
     the full backend up). Copies .db + .db-wal + .db-shm so WAL rows aren't lost.
  2. Checks the WTI front-month (timestamp, close). If it hasn't changed since the
     last push, it does NOTHING — no commit, no rebuild.
  3. On a real change: checkpoints the candle DB and runs fast_deploy.py, which
     uploads only the files whose content changed (the candle DB). HF dedups the
     unchanged 41 MB energy.db, so each push is light (~1.4 MB).

IMPORTANT — why we push on change, not blindly every minute:
  Every commit to a HF Space triggers a Docker rebuild + container restart
  (~1-2 min of downtime). The candle feed is 15-minute bars, so there is nothing
  new to push more than ~once per 15 min anyway. Polling often but pushing only
  on change gives near-real-time updates without the Space perpetually restarting.

Usage (from the repo root, with the I: drive mounted):
  backend\\venv\\Scripts\\python.exe auto_publish.py                 # loop, poll 300s
  backend\\venv\\Scripts\\python.exe auto_publish.py --interval=60   # poll every 60s
  backend\\venv\\Scripts\\python.exe auto_publish.py --once          # single cycle
  backend\\venv\\Scripts\\python.exe auto_publish.py --once --force  # push even if unchanged
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
IDRIVE_BASE = r"I:\Public\Summer Interns Energy\DB\bars_15min_20260612"
DEST_BASE = os.path.join(ROOT, "DB", "bars_15min_latest")
CANDLE = DEST_BASE + ".db"
MARKER = os.path.join(ROOT, ".last_publish.json")
MONTHS = {'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
          'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12}


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def sync_from_idrive():
    copied = []
    for ext in (".db", ".db-wal", ".db-shm"):
        src, dst = IDRIVE_BASE + ext, DEST_BASE + ext
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst)
                copied.append(ext)
            except Exception as e:
                log(f"  sync copy failed {ext}: {e}")
    if not copied:
        log(f"  WARNING: I: drive source not found at {IDRIVE_BASE}.db")
    return copied


def front_marker():
    """WTI front-month (timestamp, close) from the candle DB — the change key."""
    try:
        con = sqlite3.connect(CANDLE)
        tabs = sorted(
            (t[0] for t in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'CL_%'").fetchall()),
            key=lambda t: (lambda s: (int(s[1:]) if s[1:].isdigit() else 99, MONTHS.get(s[0], 99)))(t.split('_')[1]),
        )
        for t in tabs:
            row = con.execute(f"SELECT timestamp, close FROM {t} ORDER BY timestamp DESC LIMIT 1").fetchone()
            if row:
                con.close()
                return {"contract": t, "ts": row[0], "close": row[1]}
        con.close()
    except Exception as e:
        log(f"  marker read failed: {e}")
    return None


def load_marker():
    try:
        with open(MARKER) as f:
            return json.load(f)
    except Exception:
        return None


def save_marker(m):
    with open(MARKER, "w") as f:
        json.dump(m, f)


def run(script):
    r = subprocess.run([PY, os.path.join(ROOT, script)], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  {script} FAILED (exit {r.returncode}): {(r.stderr or r.stdout)[-600:]}")
        return False
    return True


def cycle(force=False):
    sync_from_idrive()
    m = front_marker()
    if not m:
        log("  no candle data found; skipping")
        return
    last = load_marker()
    if not force and last and last.get("ts") == m["ts"] and last.get("close") == m["close"]:
        log(f"  no change (WTI front {m['contract']} {m['ts']} @ {m['close']}); not pushing")
        return
    log(f"  change: WTI front {m['contract']} {m['ts']} @ {m['close']} -> checkpoint + deploy")
    if not run("_prep_deploy_db.py"):
        return
    if not run("fast_deploy.py"):
        return
    save_marker(m)
    log("  pushed to HF (rebuild triggered)")


def main():
    args = sys.argv[1:]
    once = "--once" in args
    force = "--force" in args
    interval = 300
    for a in args:
        if a.startswith("--interval="):
            interval = max(30, int(a.split("=")[1]))
    log(f"auto_publish: poll every {interval}s, push only on data change (Ctrl+C to stop)")
    cycle(force=force)
    if once:
        return
    while True:
        time.sleep(interval)
        try:
            cycle()
        except Exception as e:
            log(f"cycle error: {e}")


if __name__ == "__main__":
    main()
