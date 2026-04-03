import os
import time
import requests

WEBHOOK_URL = os.getenv("WEBHOOK_URL")


def send_discord(message):
    print("TRYING TO SEND TO DISCORD")

    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL")
        return

    try:
        response = requests.post(
            WEBHOOK_URL,
            json={"content": message},
            timeout=15,
        )
        print("Discord status:", response.status_code)
        print("Discord response:", response.text)
    except Exception as e:
        print("DISCORD ERROR:", e)


if __name__ == "__main__":
    print("RUNNING MAIN")

    while True:
        try:
            send_discord("🔥 BOT TEST MESSAGE 🔥")
            print("Sleeping...")
            time.sleep(60)
        except Exception as e:
            print("ERROR:", e)
            time.sleep(30)
