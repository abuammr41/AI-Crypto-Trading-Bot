"""
run_loop.py
-----------
Ye script main.py ko baar baar chalati rehti hai (har CHECK_INTERVAL_SECONDS baad).
Isko ek dafa start karo, phir ye khud chalti rahegi jab tak band na karo (Ctrl+C se).

Agar kisi cycle mein error aa jaye, poori loop nahi rukti — sirf us cycle
ko log kar ke agle cycle ka wait karti hai.
"""

import time
import traceback
from datetime import datetime

import config
import main as bot_main


def run_forever():
    print("=" * 60)
    print("Trading bot loop shuru ho raha hai.")
    print(f"Har {config.CHECK_INTERVAL_SECONDS // 60} minute mein ek check-in hoga.")
    print("Rokne ke liye Ctrl+C dabao, ya PAUSE.txt file bana do.")
    print("=" * 60)

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n--- Cycle start: {timestamp} ---")

        try:
            bot_main.run_cycle()
        except KeyboardInterrupt:
            print("\nUser ne Ctrl+C dabaya. Bot ruk raha hai.")
            break
        except Exception as e:
            # Koi bhi anjaani error aaye, loop ko nahi rukna chahiye
            print(f"[LOOP ERROR] {e}")
            traceback.print_exc()

        print(f"--- Cycle khatam. Agla check {config.CHECK_INTERVAL_SECONDS // 60} minute baad. ---")

        try:
            time.sleep(config.CHECK_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nUser ne Ctrl+C dabaya. Bot ruk raha hai.")
            break


if __name__ == "__main__":
    run_forever()
