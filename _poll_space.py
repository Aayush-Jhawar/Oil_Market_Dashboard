"""Poll the HF Space build/runtime stage until it settles, then exit."""
import os
import time
from dotenv import load_dotenv
from huggingface_hub import HfApi

load_dotenv()
api = HfApi()
tok = os.getenv("HF_API_KEY")
REPO = "YourGrimReaper/energy-dashboard"

TERMINAL = {"RUNNING", "BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE", "PAUSED", "STOPPED"}

last = None
deadline = time.time() + 30 * 60  # 30 min cap
while time.time() < deadline:
    try:
        rt = api.get_space_runtime(REPO, token=tok)
        stage = rt.stage
    except Exception as e:
        stage = f"ERR:{e}"
    if stage != last:
        print(f"[{time.strftime('%H:%M:%S')}] stage -> {stage}", flush=True)
        last = stage
    if stage in TERMINAL:
        print(f"FINAL: {stage}", flush=True)
        break
    time.sleep(20)
else:
    print(f"TIMEOUT after 30min, last stage: {last}", flush=True)
