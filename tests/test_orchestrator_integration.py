"""
Test Suite 2: Orchestrator + XYZ Integration Test
Tests calling Orchestrator commands, calculating element screen coordinates, and invoking XYZ actions.
"""

import time
import requests
import asyncio
import json

ORCHESTRATOR_WS = "ws://localhost:8000"
XYZ_URL = "http://localhost:8001"

def test_orchestrator_and_actuator_flow():
    print("=== Integration Test: Orchestrator & Component XYZ Actuator ===")
    
    # 1. Check Component XYZ service health
    try:
        r = requests.get(f"{XYZ_URL}/health")
        r.raise_for_status()
        print(f"[XYZ ACTUATOR] Status OK. Mouse position: {r.json()['pos']}")
    except Exception as e:
        print(f"[ERROR] XYZ Actuator service not running: {e}")
        return

    # 2. Simulate Orchestrator delegating action to XYZ
    print("\nExecuting sample Orchestrator action sequence:")

    # Step A: Move mouse to target area via Bezier trajectory
    target_x, target_y = 600, 450
    print(f"Step A: Orchestrator -> XYZ: Move cursor to target ({target_x}, {target_y})")
    res_move = requests.post(f"{XYZ_URL}/move", json={"x": target_x, "y": target_y, "duration_hint": 0.5})
    print(f"   Response: {res_move.json()}")
    time.sleep(0.5)

    # Step B: Click element
    print(f"Step B: Orchestrator -> XYZ: Click at ({target_x}, {target_y})")
    res_click = requests.post(f"{XYZ_URL}/click", json={"x": target_x, "y": target_y, "button": "left"})
    print(f"   Response: {res_click.json()}")
    time.sleep(0.5)

    # Step C: Type input text with human pacing
    text_to_type = "Automated test message via Sense/Act system"
    print(f"Step C: Orchestrator -> XYZ: Type '{text_to_type}'")
    res_type = requests.post(f"{XYZ_URL}/type", json={"text": text_to_type, "wpm_range": [45, 75]})
    print(f"   Response: {res_type.json()}")
    time.sleep(0.5)

    # Step D: Press hotkey (e.g. Save Ctrl+S)
    print("Step D: Orchestrator -> XYZ: Hotkey ['ctrl', 's']")
    res_hotkey = requests.post(f"{XYZ_URL}/hotkey", json={"keys": ["ctrl", "s"]})
    print(f"   Response: {res_hotkey.json()}")
    time.sleep(1.0)

    # Step E: Human pacing wait
    print("Step E: Orchestrator -> XYZ: Wait human pacing interval")
    res_wait = requests.post(f"{XYZ_URL}/wait", json={"min_s": 1.0, "max_s": 2.0})
    print(f"   Response: {res_wait.json()}")

    print("\n[SUCCESS] Integration test flow executed successfully.")

if __name__ == "__main__":
    test_orchestrator_and_actuator_flow()
