import os
from huggingface_hub import HfApi
from dotenv import load_dotenv

def deploy():
    load_dotenv()
    token = os.getenv("HF_API_KEY")
    if not token:
        print("HF_API_KEY not found in .env")
        return

    api = HfApi()
    
    print("Authenticating...")
    try:
        user_info = api.whoami(token=token)
        username = user_info['name']
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    space_name = "energy-dashboard"
    repo_id = f"{username}/{space_name}"
    
    print(f"Creating/getting Space: {repo_id}")
    try:
        api.create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk="docker",
            token=token,
            exist_ok=True,
            private=False
        )
        print("Space is ready.")
    except Exception as e:
        print(f"Error creating space: {e}")

    print("Uploading project files (this may take a few minutes)...")
    api.upload_folder(
        folder_path=".",
        repo_id=repo_id,
        repo_type="space",
        token=token,
        ignore_patterns=[
            ".venv*", 
            "node_modules", 
            "__pycache__", 
            ".git", 
            "research_journals",
            "backtest_journal.db",
            "bars_15min_latest.db*"
        ]
    )
    
    print("==========================================")
    print("✅ Deployment initiated successfully!")
    print(f"🔗 View your space at: https://huggingface.co/spaces/{repo_id}")
    print("Note: Hugging Face will take a few minutes to build the Docker image.")
    print("==========================================")

if __name__ == "__main__":
    deploy()
