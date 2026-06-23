import sys
import os

# Add the backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.bars15_paper_engine import run_replay

def main():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'DB')
    print("Running replay engine...")
    run_replay(db_dir=db_path)
    print("Replay completed!")

if __name__ == "__main__":
    main()
