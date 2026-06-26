import sqlite3 as _sqlite3
import os
import glob as _glob
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('sync')

source_dir = r"I:\Public\Summer Interns Energy\DB"
candidates = sorted(_glob.glob(os.path.join(source_dir, "bars_15min_????????.db")))
if not candidates:
    print("No candidates")
    exit()

dest_db = os.environ.get("BARS15_DB_PATH") or os.path.join("DB", "bars_15min_latest.db")
dest_conn = _sqlite3.connect(dest_db, timeout=10)
total_inserted = 0
latest = {}
try:
    dest_conn.execute("PRAGMA journal_mode=WAL")
    dest_conn.execute("PRAGMA busy_timeout=10000")
    for src_db in candidates:
        src_conn = None
        temp_db = None
        try:
            import shutil
            import tempfile
            temp_dir = tempfile.gettempdir()
            base_name = os.path.basename(src_db)
            temp_db = os.path.join(temp_dir, base_name)
            try:
                shutil.copy2(src_db, temp_db)
                for ext in ["-wal", "-shm"]:
                    if os.path.exists(src_db + ext):
                        shutil.copy2(src_db + ext, temp_db + ext)
            except Exception as copy_err:
                logger.warning(f"DB sync: copy failed for {src_db} - {copy_err}")
                continue

            src_conn = _sqlite3.connect(temp_db, timeout=10)
            tables = [t[0] for t in src_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            before = dest_conn.total_changes
            skipped = []
            for tbl in tables:
                try:
                    ddl = src_conn.execute(
                        f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{tbl}'"
                    ).fetchone()
                    if ddl and ddl[0]:
                        dest_conn.execute(ddl[0].replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
                        dest_conn.execute(
                            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{tbl}_ts ON {tbl}(timestamp)"
                        )
                    rows = src_conn.execute(
                        f"SELECT timestamp, open, high, low, close, volume FROM {tbl}"
                    ).fetchall()
                    dest_conn.executemany(
                        f"INSERT OR IGNORE INTO {tbl} (timestamp, open, high, low, close, volume) VALUES (?,?,?,?,?,?)",
                        rows,
                    )
                    dest_conn.commit()
                except Exception as te:
                    print(f"Table {tbl} error: {te}")
                    try:
                        dest_conn.rollback()
                    except:
                        pass
                    skipped.append(tbl)
            if skipped:
                print(f"Skipped {len(skipped)} tables")
            total_inserted += max(0, dest_conn.total_changes - before)
        except Exception as e:
            print(f"Error merging {src_db}: {e}")
        finally:
            if src_conn:
                src_conn.close()
            if temp_db:
                for ext in ["", "-wal", "-shm"]:
                    try:
                        if os.path.exists(temp_db + ext):
                            os.remove(temp_db + ext)
                    except:
                        pass
    print(f"Total inserted: {total_inserted}")
finally:
    dest_conn.close()
