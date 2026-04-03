print("🔥 BOT IS LIVE 🔥")
import os
import requests
import time
from datetime import datetime

# =========================
# ENV VARIABLES (IMPORTANT)
# =========================
https://discord.com/api/webhooks/1489528498707107902/c5JMwhIiw8MKPzuljVGxDrkYuLXfQOK7W4kxywI6OoGXWN5DIdGFfiFGxLRQF-iaY0L5 = os.getenv(https://discord.com/api/webhooks/1489528498707107902/c5JMwhIiw8MKPzuljVGxDrkYuLXfQOK7W4kxywI6OoGXWN5DIdGFfiFGxLRQF-iaY0L5)
5a9123660cf89f2e909112bb43254ea0 = os.getenv(5a9123660cf89f2e909112bb43254ea0)

# =========================
# TRACK SENT PLAYS
# =========================
sent_plays = set()

# =========================
# BASIC PROBABILITY MODELS
# =========================
def implied_prob(odds):
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def model_prob(projection, line):
    diff = projection - line
    prob = 0.5 + (diff * 0.035)
    return max(0.25, min(0.80, prob))


# =========================
# EDGE CALCULATION
# =========================
def calc_edge(model_p, vegas_p):
    return (model_p - vegas_p) * 100


# =========================
# FETCH ODDS (PLACEHOLDER)
# =========================
def get_props():
    """
    Replace this with real Odds API later.
    For now, sample data to test bot.
    """
    return [
        {
            "player": "Donovan Mitchell",
            "line": 25.5,
            "odds": -120,
            "projection": 28.2
        },
        {
            "player": "Nikola Jokic",
            "line": 10.5,
            "odds": -115,
            "projection": 11.6
        },
        {
            "player": "Christian Braun",
            "line": 12.5,
            "odds": -110,
            "projection": 10.2
        }
    ]


# =========================
# DISCORD SENDER
# =========================
def send_discord(message):
    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL")
        return

    requests.post(WEBHOOK_URL, json={"content": message})


# =========================
# BOT LOGIC
# =========================
def run_bot():
    props = get_props()
    plays = []

    for p in props:

        vegas_p = implied_prob(p["odds"])
        model_p = model_prob(p["projection"], p["line"])

        edge = calc_edge(model_p, vegas_p)

        play_key = f"{p['player']}_{p['line']}"

        # FILTER (PRO LEVEL)
        if edge >= 6 and play_key not in sent_plays:
            sent_plays.add(play_key)

            plays.append({
                "player": p["player"],
                "line": p["line"],
                "projection": round(p["projection"], 1),
                "edge": round(edge, 1),
                "model": round(model_p * 100, 1),
                "vegas": round(vegas_p * 100, 1)
            })

    if not plays:
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


# =========================
# LIVE LOOP
# =========================
if __name__ == "__main__":
    while True:
        run_bot(send_discord("✅ Bot is alive and connected"))
        time.sleep(300)  # runs every 5 minutes
