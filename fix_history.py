import json
import os
from pathlib import Path

# 1. Path to your history file
history_path = Path("output/data/content_history.json")
token_path = Path("youtube_token.json")

print("--- DailyFitX System Repair ---")

# 2. Fix Database (Remove missing files from pending list)
if history_path.exists():
    with open(history_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    fixed_count = 0
    for entry in data:
        # If the video isn't uploaded yet, check if the file actually exists
        if not entry.get("uploaded", False):
            video_path = entry.get("video_path")
            if video_path and not os.path.exists(video_path):
                # Using .encode to avoid Windows terminal crash on special characters
                safe_name = os.path.basename(video_path).encode('ascii', 'replace').decode()
                print(f"Cleanup: Marking missing file as 'skipped': {safe_name}")
                entry["uploaded"] = True
                entry["skipped_because_missing"] = True
                fixed_count += 1
    
    if fixed_count > 0:
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Success: Fixed {fixed_count} ghost records in database.")
    else:
        print("Database: No missing pending files found.")
else:
    print("Database: history file not found, skipping check.")

# 3. Reset Login Token
if token_path.exists():
    try:
        os.remove(token_path)
        print("Login Security: Expired token removed. You will be asked to log in again next time.")
    except Exception as e:
        print(f"Error removing token: {e}")
else:
    print("Login Security: Old token already gone.")

print("\nRepair Complete! Now run: python upload_all.py")
