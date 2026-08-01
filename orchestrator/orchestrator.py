"""
Orchestrator - Sense/Act Browser Automation Core
Bridge between Component ABC (Sensor via WebSocket) and Component XYZ (Actuator via HTTP API).
"""

import asyncio
import json
import logging
import time
import requests
from typing import Dict, Any, Optional
from websockets.server import serve

logging.basicConfig(level=logging.INFO, format="[Orchestrator] %(asctime)s - %(levelname)s - %(message)s")

XYZ_URL = "http://localhost:8001"
WS_PORT = 8000

class RateLimiter:
    """Enforces pacing and rate caps per account/session."""
    def __init__(self, max_actions_per_hour: int = 120, min_cooldown_sec: float = 2.0):
        self.max_actions_per_hour = max_actions_per_hour
        self.min_cooldown_sec = min_cooldown_sec
        self.action_history = []
        self.last_action_time = 0

    def can_perform_action(self) -> bool:
        now = time.time()
        # Clean history older than 1 hour (3600s)
        self.action_history = [t for t in self.action_history if now - t < 3600]
        
        if len(self.action_history) >= self.max_actions_per_hour:
            logging.warning("Action limit per hour reached!")
            return False
            
        if now - self.last_action_time < self.min_cooldown_sec:
            logging.warning("Action cooling down...")
            return False

        return True

    def record_action(self):
        now = time.time()
        self.action_history.append(now)
        self.last_action_time = now


class OrchestratorBridge:
    def __init__(self):
        self.connected_sensor = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.rate_limiter = RateLimiter()

        # Calibration offset (Chrome title bar / tab strip offset)
        self.offset_x = 0
        self.offset_y = 80  # Default estimate for Chrome window UI top bar

    async def register_sensor(self, websocket):
        self.connected_sensor = websocket
        logging.info("Component ABC Sensor connected to Orchestrator bridge.")

    async def send_sensor_command(self, action: str, payload: dict = None) -> dict:
        if not self.connected_sensor:
            raise RuntimeError("Sensor extension (Component ABC) is not connected.")

        request_id = str(int(time.time() * 1000))
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[request_id] = future

        msg = {
            "requestId": request_id,
            "action": action,
            "payload": payload or {}
        }

        await self.connected_sensor.send(json.dumps(msg))
        
        try:
            # Wait for response from extension content script
            response = await asyncio.wait_for(future, timeout=10.0)
            return response
        finally:
            self.pending_requests.pop(request_id, None)

    async def analyze_site(self, output_path: str = "site_analysis.json") -> dict:
        """Triggers Component ABC site analysis and saves structured JSON for XYZ reference."""
        logging.info("Requesting site analysis from Component ABC...")
        res = await self.send_sensor_command("analyze_site")
        report = res.get("report", {})
        if report:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            logging.info(f"Site analysis saved to '{output_path}'")
        return report


    def viewport_to_screen(self, rect: dict, window_geom: dict) -> tuple:
        """
        Converts element viewport relative bounds to absolute screen coordinates.
        Takes into account window position (screenX, screenY) and Chrome top UI offset.
        """
        screen_x = window_geom.get('screenX', 0)
        screen_y = window_geom.get('screenY', 0)
        dpr = window_geom.get('devicePixelRatio', 1.0)

        # Center point of element
        center_vx = rect['x'] + rect['width'] / 2.0
        center_vy = rect['y'] + rect['height'] / 2.0

        # Absolute screen location
        abs_x = screen_x + (center_vx * dpr) + self.offset_x
        abs_y = screen_y + (center_vy * dpr) + self.offset_y

        return int(abs_x), int(abs_y)

    def execute_actuator_click(self, x: int, y: int):
        if not self.rate_limiter.can_perform_action():
            logging.warning("Action blocked by rate limiter.")
            return False
        res = requests.post(f"{XYZ_URL}/click", json={"x": x, "y": y})
        self.rate_limiter.record_action()
        return res.status_code == 200

    def execute_actuator_type(self, text: str):
        if not self.rate_limiter.can_perform_action():
            logging.warning("Action blocked by rate limiter.")
            return False
        res = requests.post(f"{XYZ_URL}/type", json={"text": text})
        self.rate_limiter.record_action()
        return res.status_code == 200

    def execute_actuator_scroll(self, direction: str = "down", amount: int = 3):
        res = requests.post(f"{XYZ_URL}/scroll", json={"direction": direction, "amount": amount})
        return res.status_code == 200


orchestrator = OrchestratorBridge()

async def ws_handler(websocket, path):
    try:
        async for message in websocket:
            data = json.loads(message)
            req_id = data.get("requestId")

            if data.get("type") == "register":
                await orchestrator.register_sensor(websocket)
            elif req_id in orchestrator.pending_requests:
                orchestrator.pending_requests[req_id].set_result(data)
            elif data.get("type") == "notification":
                logging.info(f"Notification from ABC Sensor: {data.get('payload')}")
    except Exception as e:
        logging.error(f"WebSocket client disconnected or error: {e}")

async def main():
    logging.info(f"Starting Orchestrator WebSocket Server on ws://localhost:{WS_PORT}")
    async with serve(ws_handler, "localhost", WS_PORT):
        await asyncio.Future() # Run forever

if __name__ == "__main__":
    asyncio.run(main())
