import os
from dotenv import load_dotenv
from huggingface_hub import HfApi

load_dotenv()
api = HfApi()
tok = os.getenv("HF_API_KEY")
rt = api.get_space_runtime("YourGrimReaper/energy-dashboard", token=tok)
print("stage:", rt.stage)
print("hardware:", rt.hardware)
cs = api.list_repo_commits("YourGrimReaper/energy-dashboard", repo_type="space", token=tok)
print("latest commit:", cs[0].commit_id[:8], cs[0].created_at)
