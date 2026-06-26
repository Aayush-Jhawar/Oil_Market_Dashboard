import os
import shutil
import time

src_db = r"I:\Public\Summer Interns Energy\DB\bars_15min_20260623.db"
temp_db = "temp.db"

success = False
for attempt in range(10):
    try:
        shutil.copy2(src_db, temp_db)
        for ext in ["-wal", "-shm"]:
            if os.path.exists(src_db + ext):
                shutil.copy2(src_db + ext, temp_db + ext)
        success = True
        break
    except Exception as e:
        print(f"Attempt {attempt} failed: {e}")
        time.sleep(1)

print(f"Copy success: {success}")
