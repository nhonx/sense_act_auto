"""
Component XYZ - OS-Level Input Controller (Actuator)
Cross-platform hardware input generation (Linux, Windows, macOS) using direct OS events.
"""

import time
import math
import random
import sys
import os
import logging
from typing import Tuple, List, Optional
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="[Component XYZ] %(asctime)s - %(levelname)s - %(message)s")

# Import platform specific libraries
CURRENT_OS = sys.platform

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.001
except ImportError:
    pyautogui = None

try:
    from pynput.mouse import Controller as MouseController, Button as MouseButton
    from pynput.keyboard import Controller as KeyboardController, Key
    pynput_mouse = MouseController()
    pynput_keyboard = KeyboardController()
except ImportError:
    pynput_mouse = None
    pynput_keyboard = None

try:
    import evdev
    from evdev import UInput, ecodes as e
    key_codes = set()
    for k in dir(e):
        if k.startswith('KEY_') or k.startswith('BTN_'):
            val = getattr(e, k)
            if isinstance(val, int) and 0 <= val < 0x200:
                key_codes.add(val)
    uinput_dev = UInput({
        e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL],
        e.EV_KEY: list(key_codes)
    }, name='SenseAct-Hardware-Input')
    logging.info("Kernel uinput device successfully created.")
except Exception as uinput_err:
    uinput_dev = None
    logging.info(f"uinput driver not active (fallback to pynput/pyautogui): {uinput_err}")

# Bezier Curve Generator for Human-like movement
def generate_bezier_path(start: Tuple[int, int], end: Tuple[int, int], num_points: int = 40) -> List[Tuple[float, float]]:
    x1, y1 = start
    x2, y2 = end

    distance = math.hypot(x2 - x1, y2 - y1)
    if distance < 5:
        return [(float(x2), float(y2))]

    # Generate random control points for cubic Bezier curve
    offset = min(distance * 0.3, 150)
    
    # Control point 1
    ctrl1_x = x1 + (x2 - x1) * 0.25 + random.uniform(-offset, offset)
    ctrl1_y = y1 + (y2 - y1) * 0.25 + random.uniform(-offset, offset)

    # Control point 2
    ctrl2_x = x1 + (x2 - x1) * 0.75 + random.uniform(-offset, offset)
    ctrl2_y = y1 + (y2 - y1) * 0.75 + random.uniform(-offset, offset)

    path = []
    # 10-20% chance of small overshoot
    overshoot = random.random() < 0.15
    target_x, target_y = end

    if overshoot:
        overshoot_dist = random.uniform(5, 18)
        angle = math.atan2(y2 - y1, x2 - x1)
        overshoot_x = x2 + math.cos(angle) * overshoot_dist
        overshoot_y = y2 + math.sin(angle) * overshoot_dist
    else:
        overshoot_x, overshoot_y = target_x, target_y

    for i in range(num_points + 1):
        t = i / num_points
        # Ease in-out (cubic easing)
        if t < 0.5:
            eased_t = 4 * t * t * t
        else:
            eased_t = 1 - math.pow(-2 * t + 2, 3) / 2

        # Cubic Bezier equation
        px = (1 - eased_t)**3 * x1 + 3 * (1 - eased_t)**2 * eased_t * ctrl1_x + 3 * (1 - eased_t) * eased_t**2 * ctrl2_x + eased_t**3 * overshoot_x
        py = (1 - eased_t)**3 * y1 + 3 * (1 - eased_t)**2 * eased_t * ctrl1_y + 3 * (1 - eased_t) * eased_t**2 * ctrl2_y + eased_t**3 * overshoot_y

        # Micro-jitter noise (1-2 px)
        if 0 < i < num_points:
            px += random.uniform(-1.5, 1.5)
            py += random.uniform(-1.5, 1.5)

        path.append((px, py))

    # Add correction path if overshot
    if overshoot:
        corr_steps = random.randint(5, 10)
        for j in range(1, corr_steps + 1):
            ct = j / corr_steps
            cx = overshoot_x + (target_x - overshoot_x) * ct
            cy = overshoot_y + (target_y - overshoot_y) * ct
            path.append((cx, cy))

    return path


class ActuatorController:
    def __init__(self):
        logging.info(f"Actuator initialized on platform: {CURRENT_OS}")

    def get_position(self) -> Tuple[int, int]:
        if pynput_mouse:
            pos = pynput_mouse.position
            return int(pos[0]), int(pos[1])
        if pyautogui:
            pos = pyautogui.position()
            return pos.x, pos.y
        return 0, 0

    def move_to(self, target_x: int, target_y: int, duration_hint: float = 0.8):
        start_x, start_y = self.get_position()
        dist = math.hypot(target_x - start_x, target_y - start_y)
        if dist < 3:
            return

        num_points = max(25, int(dist / 10))
        points = generate_bezier_path((start_x, start_y), (target_x, target_y), num_points=num_points)

        total_duration = max(0.6, min(2.5, duration_hint * (dist / 250)))
        step_delay = max(0.015, total_duration / len(points))

        curr_x, curr_y = start_x, start_y
        for px, py in points:
            ix, iy = int(px), int(py)
            dx = ix - curr_x
            dy = iy - curr_y
            curr_x, curr_y = ix, iy

            if uinput_dev and (dx != 0 or dy != 0):
                uinput_dev.write(e.EV_REL, e.REL_X, dx)
                uinput_dev.write(e.EV_REL, e.REL_Y, dy)
                uinput_dev.syn()
            if pynput_mouse:
                pynput_mouse.position = (ix, iy)
            if pyautogui:
                pyautogui.moveTo(ix, iy)
            time.sleep(step_delay)

        if uinput_dev:
            final_dx = target_x - curr_x
            final_dy = target_y - curr_y
            if final_dx != 0 or final_dy != 0:
                uinput_dev.write(e.EV_REL, e.REL_X, final_dx)
                uinput_dev.write(e.EV_REL, e.REL_Y, final_dy)
                uinput_dev.syn()

        if pynput_mouse:
            pynput_mouse.position = (int(target_x), int(target_y))
        if pyautogui:
            pyautogui.moveTo(int(target_x), int(target_y))

    def click(self, x: int, y: int, button: str = "left", double: bool = False):
        self.move_to(x, y)
        time.sleep(random.uniform(0.05, 0.15))

        btn_code = e.BTN_RIGHT if (uinput_dev and button == "right") else (e.BTN_LEFT if uinput_dev else None)

        if uinput_dev and btn_code:
            uinput_dev.write(e.EV_KEY, btn_code, 1)
            uinput_dev.syn()
            time.sleep(random.uniform(0.04, 0.12))
            uinput_dev.write(e.EV_KEY, btn_code, 0)
            uinput_dev.syn()
        elif pynput_mouse:
            btn = MouseButton.right if button == "right" else MouseButton.left
            pynput_mouse.press(btn)
            time.sleep(random.uniform(0.04, 0.12))
            pynput_mouse.release(btn)
        elif pyautogui:
            if double:
                pyautogui.doubleClick(button=button)
            else:
                pyautogui.mouseDown(button=button)
                time.sleep(random.uniform(0.03, 0.12))
                pyautogui.mouseUp(button=button)

    def _type_char_uinput(self, c: str) -> bool:
        if not uinput_dev:
            return False

        if c == '\n':
            uinput_dev.write(e.EV_KEY, e.KEY_ENTER, 1)
            uinput_dev.syn()
            time.sleep(0.03)
            uinput_dev.write(e.EV_KEY, e.KEY_ENTER, 0)
            uinput_dev.syn()
            return True

        if c == ' ':
            uinput_dev.write(e.EV_KEY, e.KEY_SPACE, 1)
            uinput_dev.syn()
            time.sleep(0.03)
            uinput_dev.write(e.EV_KEY, e.KEY_SPACE, 0)
            uinput_dev.syn()
            return True

        is_upper = c.isupper()
        code_attr = 'KEY_' + c.upper()
        if hasattr(e, code_attr):
            code = getattr(e, code_attr)
            if is_upper:
                uinput_dev.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
                uinput_dev.syn()
                time.sleep(0.02)

            uinput_dev.write(e.EV_KEY, code, 1)
            uinput_dev.syn()
            time.sleep(0.03)
            uinput_dev.write(e.EV_KEY, code, 0)
            uinput_dev.syn()
            time.sleep(0.02)

            if is_upper:
                uinput_dev.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
                uinput_dev.syn()
                time.sleep(0.02)
            return True

        if c == '-':
            uinput_dev.write(e.EV_KEY, e.KEY_MINUS, 1)
            uinput_dev.syn()
            time.sleep(0.02)
            uinput_dev.write(e.EV_KEY, e.KEY_MINUS, 0)
            uinput_dev.syn()
            return True

        if c == '_':
            uinput_dev.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
            uinput_dev.write(e.EV_KEY, e.KEY_MINUS, 1)
            uinput_dev.syn()
            time.sleep(0.02)
            uinput_dev.write(e.EV_KEY, e.KEY_MINUS, 0)
            uinput_dev.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
            uinput_dev.syn()
            return True

        if c == '/':
            uinput_dev.write(e.EV_KEY, e.KEY_SLASH, 1)
            uinput_dev.syn()
            time.sleep(0.02)
            uinput_dev.write(e.EV_KEY, e.KEY_SLASH, 0)
            uinput_dev.syn()
            return True

        return False

    def type_text(self, text: str, wpm_range: Tuple[int, int] = (35, 75), simulate_typos: bool = False):
        min_wpm, max_wpm = wpm_range
        avg_cps = (random.uniform(min_wpm, max_wpm) * 5) / 60.0
        base_delay = 1.0 / max(1.0, avg_cps)

        for i, char in enumerate(text):
            if simulate_typos and random.random() < 0.04 and char.isalpha():
                wrong_char = chr(ord(char) + random.choice([-1, 1]))
                if not self._type_char_uinput(wrong_char):
                    if pynput_keyboard:
                        pynput_keyboard.type(wrong_char)
                    elif pyautogui:
                        pyautogui.write(wrong_char)
                time.sleep(random.uniform(0.1, 0.25))

                if uinput_dev:
                    uinput_dev.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
                    uinput_dev.syn()
                    time.sleep(0.03)
                    uinput_dev.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
                    uinput_dev.syn()
                elif pynput_keyboard:
                    pynput_keyboard.press(Key.backspace)
                    pynput_keyboard.release(Key.backspace)
                elif pyautogui:
                    pyautogui.press('backspace')
                time.sleep(random.uniform(0.08, 0.2))

            typed = self._type_char_uinput(char)
            if not typed:
                if pynput_keyboard:
                    pynput_keyboard.type(char)
                elif pyautogui:
                    pyautogui.write(char)

            delay = random.gauss(base_delay, base_delay * 0.35)
            delay = max(0.02, min(0.6, delay))

            if char in " .,\n":
                delay += random.uniform(0.15, 0.45)

            time.sleep(delay)



    def scroll(self, direction: str = "down", amount: int = 3, style: str = "inertial"):
        clicks = amount if direction == "up" else -amount
        steps = random.randint(3, 7)
        clicks_per_step = clicks / steps

        for i in range(steps):
            if pyautogui:
                pyautogui.scroll(int(clicks_per_step))
            time.sleep(0.03 + (i * 0.015) + random.uniform(0.01, 0.03))

    def wait_human(self, min_s: float = 1.0, max_s: float = 5.0):
        mean = (min_s + max_s) / 2.0
        sigma = 0.5
        delay = random.lognormvariate(math.log(mean), sigma)
        delay = max(min_s, min(max_s * 2, delay))
        time.sleep(delay)

    def hotkey(self, keys: List[str]):
        time.sleep(random.uniform(0.05, 0.15))
        if uinput_dev:
            mapped_codes = []
            for k in keys:
                k_lower = k.lower()
                if k_lower in ('win', 'super', 'meta', 'command'):
                    mapped_codes.append(e.KEY_LEFTMETA)
                elif k_lower in ('ctrl', 'control'):
                    mapped_codes.append(e.KEY_LEFTCTRL)
                elif k_lower == 'alt':
                    mapped_codes.append(e.KEY_LEFTALT)
                elif k_lower == 'shift':
                    mapped_codes.append(e.KEY_LEFTSHIFT)
                elif k_lower in ('enter', 'return'):
                    mapped_codes.append(e.KEY_ENTER)
                elif k_lower == 'space':
                    mapped_codes.append(e.KEY_SPACE)
                else:
                    attr = 'KEY_' + k.upper()
                    if hasattr(e, attr):
                        mapped_codes.append(getattr(e, attr))

            for code in mapped_codes:
                uinput_dev.write(e.EV_KEY, code, 1)
                uinput_dev.syn()
                time.sleep(0.04)
            time.sleep(0.08)
            for code in reversed(mapped_codes):
                uinput_dev.write(e.EV_KEY, code, 0)
                uinput_dev.syn()
                time.sleep(0.04)
        elif pynput_keyboard:
            key_objs = []
            for k in keys:
                k_lower = k.lower()
                if k_lower in ('win', 'super', 'meta', 'command'):
                    key_objs.append(Key.cmd)
                elif k_lower in ('ctrl', 'control'):
                    key_objs.append(Key.ctrl)
                elif k_lower == 'alt':
                    key_objs.append(Key.alt)
                elif k_lower == 'shift':
                    key_objs.append(Key.shift)
                elif k_lower in ('enter', 'return'):
                    key_objs.append(Key.enter)
                else:
                    key_objs.append(k)
            for k in key_objs:
                pynput_keyboard.press(k)
            time.sleep(0.08)
            for k in reversed(key_objs):
                pynput_keyboard.release(k)
        elif pyautogui:
            pyautogui.hotkey(*keys)



# Flask HTTP API Server for Actuator Service
app = Flask(__name__)
actuator = ActuatorController()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "platform": CURRENT_OS, "pos": actuator.get_position()})

@app.route('/move', methods=['POST'])
def move():
    data = request.json or {}
    x = data.get('x')
    y = data.get('y')
    duration = data.get('duration_hint', 0.5)
    if x is None or y is None:
        return jsonify({"error": "x and y required"}), 400
    actuator.move_to(int(x), int(y), duration_hint=float(duration))
    return jsonify({"status": "moved", "target": [x, y]})

@app.route('/click', methods=['POST'])
def click():
    data = request.json or {}
    x = data.get('x')
    y = data.get('y')
    button = data.get('button', 'left')
    double = data.get('double', False)
    if x is None or y is None:
        return jsonify({"error": "x and y required"}), 400
    actuator.click(int(x), int(y), button=button, double=double)
    return jsonify({"status": "clicked", "target": [x, y], "button": button})

@app.route('/type', methods=['POST'])
def type_text():
    data = request.json or {}
    text = data.get('text', '')
    wpm = tuple(data.get('wpm_range', [35, 75]))
    typos = data.get('simulate_typos', False)
    actuator.type_text(text, wpm_range=wpm, simulate_typos=typos)
    return jsonify({"status": "typed", "len": len(text)})

@app.route('/scroll', methods=['POST'])
def scroll():
    data = request.json or {}
    direction = data.get('direction', 'down')
    amount = data.get('amount', 3)
    actuator.scroll(direction=direction, amount=int(amount))
    return jsonify({"status": "scrolled", "direction": direction, "amount": amount})

@app.route('/wait', methods=['POST'])
def wait():
    data = request.json or {}
    min_s = data.get('min_s', 1.0)
    max_s = data.get('max_s', 5.0)
    actuator.wait_human(float(min_s), float(max_s))
    return jsonify({"status": "waited"})

@app.route('/hotkey', methods=['POST'])
def hotkey():
    data = request.json or {}
    keys = data.get('keys', [])
    if not keys:
        return jsonify({"error": "keys list required"}), 400
    actuator.hotkey(keys)
    return jsonify({"status": "hotkey_pressed", "keys": keys})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8001))
    logging.info(f"Starting Component XYZ Actuator Service on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
