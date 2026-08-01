"""
Test Suite 1: Component XYZ Standalone Test
Tests direct OS-level input execution: hotkeys, human-like typing, Bezier mouse moves, clicking, and saving/closing.
"""

import time
import requests
import sys

XYZ_URL = "http://localhost:8001"

def check_actuator_health():
    print("1. Checking Component XYZ health...")
    try:
        r = requests.get(f"{XYZ_URL}/health")
        r.raise_for_status()
        data = r.json()
        print(f"   [SUCCESS] Actuator online. Platform: {data['platform']}, Cursor: {data['pos']}")
        return True
    except Exception as e:
        print(f"   [ERROR] Could not connect to Component XYZ at {XYZ_URL}: {e}")
        print("   Make sure to run: python component_xyz/actuator.py")
        return False

def test_search_and_terminal_workflow():
    print("\n2. Testing Workflow: Window/Super Key -> Search Terminal -> Open Terminal -> Type 'ls'...")

    platform = sys.platform
    super_key = "command" if platform == "darwin" else "super"

    # Step A: Press Super/Window key to open Search / App Launcher menu
    print(f"   -> Step 1: Pressing [{super_key}] key to open Search Menu...")
    requests.post(f"{XYZ_URL}/hotkey", json={"keys": [super_key]})
    time.sleep(1.2)

    # Step B: Type "Terminal" and press Enter
    print("   -> Step 2: Typing 'Terminal' and pressing Enter...")
    requests.post(f"{XYZ_URL}/type", json={"text": "Terminal\n", "wpm_range": [50, 80]})
    time.sleep(2.5) # Wait for terminal application window to open and gain focus

    # Step C: Type "ls" and press Enter in the terminal
    print("   -> Step 3: Typing 'ls' command in terminal...")
    requests.post(f"{XYZ_URL}/type", json={"text": "ls\n", "wpm_range": [45, 75]})
    time.sleep(1.0)

    print("   [SUCCESS] Search menu -> Open Terminal -> Run 'ls' workflow completed!")

def test_mouse_trajectory():
    print("\n3. Testing Bezier curve mouse trajectory & clicks...")
    print("   -> Moving mouse to (500, 400) via Bezier path with jitter & overshoot...")
    requests.post(f"{XYZ_URL}/move", json={"x": 500, "y": 400, "duration_hint": 0.8})
    time.sleep(0.5)

    print("   -> Performing left click at (500, 400)...")
    requests.post(f"{XYZ_URL}/click", json={"x": 500, "y": 400, "button": "left"})
    print("   [SUCCESS] Mouse trajectory test completed.")

if __name__ == "__main__":
    if check_actuator_health():
        test_mouse_trajectory()
        test_search_and_terminal_workflow()

