#!/usr/bin/env python3
"""
Energy Dashboard - HF Spaces Entry Point
Serves FastAPI backend + React frontend
"""
import os
import sys
import subprocess
import time
from pathlib import Path

def run():
    """Start the application"""
    # Get workspace root
    workspace_root = Path(__file__).parent
    backend_dir = workspace_root / "backend"
    
    # Check for .env file (required for API keys)
    env_file = workspace_root / ".env"
    if not env_file.exists():
        print("⚠️ WARNING: .env file not found!")
        print("📝 Creating .env from .env.example...")
        env_example = workspace_root / ".env.example"
        if env_example.exists():
            with open(env_example, 'r') as f:
                with open(env_file, 'w') as out:
                    out.write(f.read())
        else:
            # Create minimal .env for HF Spaces
            with open(env_file, 'w') as f:
                f.write("# Energy Dashboard Configuration\n")
                f.write("EIA_API_KEY=demo\n")
                f.write("HF_API_KEY=demo\n")
    
    # Ensure frontend is built
    frontend_dir = workspace_root / "frontend"
    frontend_dist = frontend_dir / "dist"
    
    if not frontend_dist.exists():
        print("📦 Building frontend...")
        try:
            subprocess.run(
                ["npm", "ci"],
                cwd=frontend_dir,
                check=True,
                timeout=300
            )
            subprocess.run(
                ["npm", "run", "build"],
                cwd=frontend_dir,
                check=True,
                timeout=300
            )
            print("✅ Frontend built successfully")
        except subprocess.CalledProcessError as e:
            print(f"❌ Frontend build failed: {e}")
            return False
        except FileNotFoundError:
            print("❌ npm not found - skipping frontend build")
            return False
    
    # Install Python dependencies
    print("📦 Installing Python dependencies...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
            cwd=backend_dir,
            check=True,
            timeout=300
        )
        print("✅ Dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False
    
    # Start FastAPI server
    print("🚀 Starting Energy Dashboard...")
    print("📊 Frontend: http://localhost:7860")
    print("🔧 API Docs: http://localhost:7860/docs")
    
    try:
        os.chdir(workspace_root)
        subprocess.run(
            [
                sys.executable, "-m", "uvicorn",
                "main:app",
                "--host", "0.0.0.0",
                "--port", "7860",
                "--app-dir", str(backend_dir)
            ],
            check=False
        )
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
