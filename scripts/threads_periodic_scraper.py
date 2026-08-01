"""
Periodic Threads Scraper using Component XYZ OS-Level Input Actuator

Automates the following sequence:
1. Opens Firefox browser -> navigates to threads.com
2. Performs human-like scrolling to dynamically load feed content
3. Selects all (Ctrl+A) and copies (Ctrl+C) feed text
4. Reads clipboard and saves to a new timestamped text file
5. Closes Firefox browser
6. (Optional) Repeats periodically at specified interval minutes

Usage:
  python scripts/threads_periodic_scraper.py               # Run once
  python scripts/threads_periodic_scraper.py --interval 30 # Run every 30 minutes
"""

import time
import os
import sys
import argparse
import datetime
import logging
import requests
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="[Threads-Scraper] %(asctime)s - %(levelname)s - %(message)s"
)

XYZ_URL = "http://localhost:8001"
OUTPUT_DIR = os.path.join(os.getcwd(), "scraped_threads")

def check_actuator_service() -> bool:
    """Verifies that Component XYZ Actuator service is online."""
    try:
        r = requests.get(f"{XYZ_URL}/health", timeout=3.0)
        r.raise_for_status()
        data = r.json()
        logging.info(f"Component XYZ Actuator online. Platform: {data.get('platform')}, Cursor: {data.get('pos')}")
        return True
    except Exception as err:
        logging.error(f"Cannot connect to Component XYZ Actuator at {XYZ_URL}: {err}")
        logging.error("Please start the Actuator service first: python component_xyz/actuator.py")
        return False

def get_clipboard_text() -> str:
    """Extracts text content from the OS system clipboard using tkinter."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        content = root.clipboard_get()
        root.destroy()
        return content
    except Exception as e:
        logging.warning(f"Could not read OS clipboard via Tkinter: {e}")
        return ""

def run_threads_scrape_cycle(num_scrolls: int = 7) -> Optional[str]:
    """
    Executes one complete automation cycle:
    Launch Firefox -> Open Threads -> Scroll Feed -> Copy -> Save File -> Close Firefox
    """
    platform = sys.platform
    super_key = "command" if platform == "darwin" else "super"
    close_keys = ["command", "q"] if platform == "darwin" else ["ctrl", "q"]

    logging.info("==================================================")
    logging.info("Starting Threads.com Automation Cycle via Component XYZ")
    logging.info("==================================================")

    # 1. Open Firefox & Navigate to Threads.com
    logging.info("Step 1: Opening OS Search Menu to launch Firefox with Threads.com...")
    requests.post(f"{XYZ_URL}/hotkey", json={"keys": [super_key]})
    time.sleep(1.2)

    target_url = "https://www.threads.com"
    logging.info(f"   -> Typing 'firefox {target_url}' and pressing Enter...")
    requests.post(f"{XYZ_URL}/type", json={"text": f"firefox {target_url}\n", "wpm_range": [50, 80]})
    
    logging.info("   -> Waiting 6 seconds for Firefox to launch and load page...")
    time.sleep(6.0)

    # 2. Focus Window and Scroll Feed
    logging.info("Step 2: Focusing browser window and scrolling feed...")
    # Move mouse to viewport center (600, 400) and click to gain focus
    requests.post(f"{XYZ_URL}/move", json={"x": 600, "y": 400, "duration_hint": 0.8})
    time.sleep(0.3)
    requests.post(f"{XYZ_URL}/click", json={"x": 600, "y": 400, "button": "left"})
    time.sleep(1.0)

    for i in range(1, num_scrolls + 1):
        logging.info(f"   -> Scroll pass {i}/{num_scrolls} (human pacing)...")
        requests.post(f"{XYZ_URL}/scroll", json={"direction": "down", "amount": 6})
        requests.post(f"{XYZ_URL}/wait", json={"min_s": 2.0, "max_s": 4.0})

    logging.info("   -> Feed scroll loading completed.")
    time.sleep(1.5)

    # 3. Select All (Ctrl+A) and Copy (Ctrl+C)
    logging.info("Step 3: Selecting all content (Ctrl+A) and copying to clipboard (Ctrl+C)...")
    select_all_key = "command" if platform == "darwin" else "ctrl"
    
    # Click on page body again to ensure active focus
    requests.post(f"{XYZ_URL}/click", json={"x": 600, "y": 400, "button": "left"})
    time.sleep(0.5)

    requests.post(f"{XYZ_URL}/hotkey", json={"keys": [select_all_key, "a"]})
    time.sleep(0.8)

    requests.post(f"{XYZ_URL}/hotkey", json={"keys": [select_all_key, "c"]})
    time.sleep(1.5)

    # 4. Read Clipboard and Save to Timestamped File
    logging.info("Step 4: Reading OS clipboard and saving scraped text file...")
    copied_text = get_clipboard_text()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"threads_feed_{timestamp_str}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"=== Threads Feed Export ===\n")
        f.write(f"Scraped At: {datetime.datetime.now().isoformat()}\n")
        f.write(f"URL: {target_url}\n")
        f.write(f"Content Length: {len(copied_text)} characters\n")
        f.write("=" * 40 + "\n\n")
        f.write(copied_text)

    logging.info(f"   [SUCCESS] Feed content saved to: {filepath} ({len(copied_text)} chars)")

    # 5. Close Firefox
    logging.info("Step 5: Closing Firefox application...")
    requests.post(f"{XYZ_URL}/hotkey", json={"keys": close_keys})
    time.sleep(2.0)

    logging.info("Cycle completed successfully.\n")
    return filepath

def main():
    parser = argparse.ArgumentParser(description="Periodic Threads.com Scraper using Component XYZ Actuator")
    parser.add_argument("--interval", type=int, default=0, help="Periodic interval in minutes (0 to run once)")
    parser.add_argument("--scrolls", type=int, default=7, help="Number of scroll passes per cycle (default: 7)")
    args = parser.parse_args()

    if not check_actuator_service():
        sys.exit(1)

    if args.interval <= 0:
        logging.info("Running single scraper execution cycle...")
        run_threads_scrape_cycle(num_scrolls=args.scrolls)
    else:
        logging.info(f"Starting periodic scraper daemon every {args.interval} minutes...")
        cycle_count = 0
        while True:
            cycle_count += 1
            logging.info(f"--- Starting Scheduled Execution Cycle #{cycle_count} ---")
            try:
                run_threads_scrape_cycle(num_scrolls=args.scrolls)
            except Exception as e:
                logging.error(f"Error during execution cycle #{cycle_count}: {e}")

            sleep_seconds = args.interval * 60
            logging.info(f"Sleeping for {args.interval} minutes ({sleep_seconds}s) until next run...")
            time.sleep(sleep_seconds)

if __name__ == "__main__":
    main()
