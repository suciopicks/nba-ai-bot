print("🔥 BOT IS LIVE 🔥")

import os
import time
from datetime import datetime

import requests

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

sent_plays = set()


def implied_prob(odds):
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def model_prob(projection, line):
    diff = projection - line
    prob = 0.5 + (diff * 0.035)
    return max(0.25, min(0.80, prob))


def calc_edge(model_p, vegas_p):
    return (model_p - vegas_p) * 100


def get_props():
    return [
        {
            "player": "Donovan Mitchell",
            "line": 25.5,
            "odds": -120,
            "projection": 28.2,
        },
        {
            "player": "Nikola Jokic",
            "line": 10.5,
            "odds": -115,
            "projection": 11.6,
        },
        {
            "player": "Christian Braun",
            "line": 12.5,
            "odds": -110,
            "projection": 10.2,
        },
    ]


def send_discord(message):
    print("TRYING TO SEND TO DISCORD")

    if not WEBHOOK_URL:
        print("❌ Missing WEBHOOK_URL")
        return

    print("✅ Webhook found:", WEBHOOK_URL[:30])

    response = requests.post(
        WEBHOOK_URL,
        json={"content": message},
        timeout=15,
    )

    print("Discord status:", response.status_code)
    print("Discord response:", response.text)


def run_bot():
    print("🚀 run_bot started")

    props = get_props()
    plays = []

    for p in props:
        vegas_p = implied_prob(p["odds"])
        model_p = model_prob(p["projection"], p["line"])
        edge = calc_edge(model_p, vegas_p)

        play_key = f"{p['player']}_{p['line']}"

        if edge >= 6 and play_key not in sent_plays:
            sent_plays.add(play_key)
            plays.append(
                {
                    "player": p["player"],
                    "line": p["line"],
                    "projection": round(p["projection"], 1),
                    "edge": round(edge, 1),
                    "model": round(model_p * 100, 1),
                    "vegas": round(vegas_p * 100, 1),
                }
            )

    if not plays:
        print("No plays found. Sending test message.")
        send_discord("✅ Bot is running, but no plays")
        return

    message = f"🔥 **PRO NBA PICKS** — {datetime.now().strftime('%I:%M %p')}\n\n"

    for p in plays:
        message += (
            f"{p['player']} OVER {p['line']}\n"
            f"Projection: {p['projection']}\n"
            f"Edge: +{p['edge']}%\n"
            f"Model: {p['model']}% | Vegas: {p['vegas']}%\n\n"
        )

    send_discord(message)



  if __name__ == "__main__":
      print("RUNNING MAIN")

    while True:
        try:
            send_discord("🔥 BOT TEST MESSAGE 🔥")

            run_bot()

            print("Sleeping...")
            time.sleep(60)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(30)

    
