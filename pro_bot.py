import os
import time
import requests
from datetime import datetime

WEBHOOK_URL = os.getenv("WEBHOOK_URL")


def send_discord(content=None, embed=None):
    print("TRYING TO SEND TO DISCORD", flush=True)

    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL", flush=True)
        return

    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            timeout=15,
        )
        print(f"Discord status: {response.status_code}", flush=True)
        print(f"Discord response: {response.text}", flush=True)
    except Exception as e:
        print(f"DISCORD ERROR: {e}", flush=True)


def build_pick_embed(player, stat, line, projection, edge, confidence, odds, tag):
    return {
        "title": f"{tag} NBA PROP ALERT",
        "description": f"**{player} OVER {line} {stat}**",
        "fields": [
            {"name": "Projection", "value": str(projection), "inline": True},
            {"name": "Edge", "value": f"+{edge}%", "inline": True},
            {"name": "Confidence", "value": f"{confidence}%", "inline": True},
            {"name": "Odds", "value": odds, "inline": True},
            {"name": "Market", "value": "PrizePicks / Sportsbook", "inline": True},
            {"name": "Time", "value": datetime.now().strftime("%I:%M %p"), "inline": True},
        ],
        "footer": {
            "text": "AI NBA Props Bot"
        }
    }


def get_sample_picks():
    return [
        {
            "player": "Donovan Mitchell",
            "stat": "PTS",
            "line": 25.5,
            "projection": 28.4,
            "edge": 7.2,
            "confidence": 63,
            "odds": "-125",
            "tag": "🔥 MAX PLAY",
        },
        {
            "player": "Nikola Jokic",
            "stat": "AST",
            "line": 10.5,
            "projection": 11.8,
            "edge": 6.1,
            "confidence": 60,
            "odds": "-115",
            "tag": "✅ STRONG",
        },
    ]


def run_bot():
    print("RUNNING MAIN", flush=True)

    picks = get_sample_picks()

    if not picks:
        send_discord(content="No strong props found right now.")
        return

    send_discord(content="📊 **AI NBA PICKS ARE IN**")

    for pick in picks:
        embed = build_pick_embed(
            player=pick["player"],
            stat=pick["stat"],
            line=pick["line"],
            projection=pick["projection"],
            edge=pick["edge"],
            confidence=pick["confidence"],
            odds=pick["odds"],
            tag=pick["tag"],
        )
        send_discord(embed=embed)
        time.sleep(1)


if __name__ == "__main__":
    while True:
        try:
            run_bot()
            print("Sleeping...", flush=True)
            time.sleep(300)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            time.sleep(30)
