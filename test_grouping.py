#!/usr/bin/env python3
"""Test script to verify log grouping works correctly"""

import time
import subprocess
import os
from pathlib import Path
from datetime import datetime

def test_log_grouping():
    # Start the capture in background
    print("Starting OpenCapture...")
    proc = subprocess.Popen(["python", "run.py"],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          text=True)

    # Give it time to start
    time.sleep(3)

    print("Testing app switching and logging...")

    # Simulate some activity (manual testing needed)
    print("\nPlease perform the following actions:")
    print("1. Click on different applications")
    print("2. Type some text in each app")
    print("3. Switch between apps multiple times")
    print("\nPress Ctrl+C when done...")

    try:
        # Wait for user to test
        proc.wait()
    except KeyboardInterrupt:
        print("\nStopping capture...")
        proc.terminate()
        time.sleep(1)

    # Check the log file
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = Path(f"~/opencapture/{today}/{today}.log").expanduser()

    if log_file.exists():
        print(f"\n=== Log file content ({log_file}) ===")
        with open(log_file, 'r') as f:
            content = f.read()
            print(content)

        # Check for grouping patterns
        print("\n=== Analysis ===")
        lines = content.split('\n')

        # Check for triple-newline separators (app groups)
        groups = content.split('\n\n\n')
        print(f"Found {len(groups)} app groups")

        # Check that events don't repeat app names
        for line in lines:
            if '⌨️' in line or '📷' in line:
                # These should NOT have app names after the emoji
                if ' | ' in line.split('] ', 1)[1]:
                    if line.split('] ', 1)[1].split(' | ')[0] not in ['⌨️', '📷']:
                        print(f"WARNING: Event line has app name: {line}")

        print("\nGrouping test complete!")
    else:
        print(f"Log file not found: {log_file}")

if __name__ == "__main__":
    test_log_grouping()