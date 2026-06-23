import os
from huggingface_hub import HfApi, CommitOperationAdd
from dotenv import load_dotenv

def deploy():
    load_dotenv()
    token = os.getenv("HF_API_KEY")
    api = HfApi()
    
    repo_id = "YourGrimReaper/energy-dashboard"
    
    print(f"Deploying to Space: {repo_id}")
    try:
        api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", token=token, exist_ok=True, private=False)
    except Exception as e:
        print(e)

    print("Collecting files to upload...")
    operations = []
    
    # We use os.walk and explicitly remove ignored directories to prevent traversing them
    ignored_dirs = {'node_modules', '.venv', 'venv', '.venv-1', '.git', '__pycache__', 'research_journals', 'DB', 'Data', 'Papers', 'dist', '.cache'}
    ignored_extensions = {'.db', '.db-wal', '.pyc', '.log', '.zip', '.png'}
    
    for root, dirs, files in os.walk('.'):
        # modify dirs in-place to prune search
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        
        for file in files:
            if any(file.endswith(ext) for ext in ignored_extensions):
                continue
                
            local_path = os.path.join(root, file)
            # Make path relative to current dir, e.g., 'backend/main.py'
            path_in_repo = os.path.relpath(local_path, '.')
            
            # Skip dotfiles in root like .env
            if path_in_repo == '.env' or path_in_repo.endswith('.env'):
                continue
                
            if path_in_repo == 'deploy_to_hf.py' or path_in_repo == 'fast_deploy.py':
                continue

            try:
                with open(local_path, "rb") as f:
                    file_data = f.read()
            except Exception as e:
                print(f"Skipping {local_path} due to read error: {e}")
                continue

            operations.append(
                CommitOperationAdd(
                    path_in_repo=path_in_repo.replace("\\", "/"),
                    path_or_fileobj=file_data
                )
            )

    # Explicitly include the checkpointed 15-min candle DB. The DB/ dir and .db
    # files are skipped by the rules above, but the app needs this one file:
    # WTI/Brent live prices read it (DB-first) and the paper-trading engine
    # replays it. Generate it first with: python _prep_deploy_db.py
    seed_db = os.path.join("DB", "bars_15min_deploy.db")
    if os.path.exists(seed_db):
        with open(seed_db, "rb") as f:
            operations.append(
                CommitOperationAdd(
                    path_in_repo="DB/bars_15min_latest.db",
                    path_or_fileobj=f.read(),
                )
            )
        print("Including seed candle DB -> DB/bars_15min_latest.db")
    else:
        print(f"WARNING: {seed_db} not found; paper trading + WTI/Brent prices will be empty on HF")

    # Ship the pre-populated daily-history DB so historical charts work without
    # the 3.6GB Data/ folder or network access. Size-guarded so we never upload
    # the giant root-level energy.db by mistake.
    # Ship the SLIM daily-history DB (built by _build_slim_db.py: full schema +
    # price_history, minus the multi-GB historical_term_structure table) as
    # backend/energy.db so historical charts work without the 3.6GB Data/ folder.
    energy_db = os.path.join("backend", "energy_deploy.db")
    if os.path.exists(energy_db) and os.path.getsize(energy_db) < 50 * 1024 * 1024:
        with open(energy_db, "rb") as f:
            operations.append(
                CommitOperationAdd(path_in_repo="backend/energy.db", path_or_fileobj=f.read())
            )
        print(f"Including slim history DB -> backend/energy.db ({round(os.path.getsize(energy_db)/1024/1024,2)} MB)")
    else:
        print("WARNING: backend/energy_deploy.db missing/too large; run 'python _build_slim_db.py'. Historical charts may be empty on HF")

    print(f"Uploading {len(operations)} files in a single commit...")
    api.create_commit(
        repo_id=repo_id,
        repo_type="space",
        operations=operations,
        commit_message="Initial dashboard deployment",
        token=token
    )
    
    print("==========================================")
    print("[OK] Deployment successful!")
    print(f"View your space at: https://huggingface.co/spaces/{repo_id}")
    print("==========================================")

if __name__ == "__main__":
    deploy()
