import os
import time
import json
import hashlib
from datetime import datetime
import requests

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

SPORT = "basketball_nba"
REGIONS = "us"
BOOKMAKERS = "draftkings,fanduel,betmgm,caesars"

# Added PA / PR / PRA + more props
MARKETS = ",".join([
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_blocks",
    "player_steals",
    "player_turnovers",
    "player_blocks_steals",
    "player_points_assists",
    "player_points_rebounds",
    "player_rebounds_assists",
    "player_points_rebounds_assists",
    "player_fantasy_points",
])

SENT_FILE = "sent_picks.json"


# -----------------------------
# SENT PICK STORAGE
# -----------------------------
def load_sent_picks():
    try:
        with open(SENT_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_sent_picks(picks):
    with open(SENT_FILE, "w") as f:
        json.dump(sorted(list(picks)), f)


sent_picks = load_sent_picks()


# -----------------------------
# DISCORD
# -----------------------------
def send_discord_embed(embed):
    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL", flush=True)
        return

    try:
        response = requests.post(
            WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=20,
        )
        print(f"Discord status: {response.status_code}", flush=True)
    except Exception as e:
        print(f"DISCORD ERROR: {e}", flush=True)


# -----------------------------
# API
# -----------------------------
def get_events():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events"
    params = {"apiKey": ODDS_API_KEY}
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def get_event_props(event_id):
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": "american",
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


# -----------------------------
# HELPERS
# -----------------------------
def implied_prob(odds):
    odds = int(odds)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def market_label(key):
    mapping = {
        "player_points": "PTS",
        "player_rebounds": "REB",
        "player_assists": "AST",
        "player_threes": "3PM",
        "player_blocks": "BLK",
        "player_steals": "STL",
        "player_turnovers": "TOV",
        "player_blocks_steals": "B+S",
        "player_points_assists": "PA",
        "player_points_rebounds": "PR",
        "player_rebounds_assists": "RA",
        "player_points_rebounds_assists": "PRA",
        "player_fantasy_points": "FP",
    }
    return mapping.get(key, key)


def make_pick_key(player, market_key, side, line, game_date):
    raw = f"{player}|{market_key}|{side}|{line}|{game_date}"
    return hashlib.md5(raw.encode()).hexdigest()


# -----------------------------
# MARKET COMPARISON ENGINE
# -----------------------------
def collect_market_candidates(event):
    """
    Build groups by player + market + side + line.
    Then compare prices across books for the exact same outcome.
    """
    grouped = {}
    game = f"{event.get('away_team', 'Away')} @ {event.get('home_team', 'Home')}"
    game_date = event.get("commence_time", "")

    for bookmaker in event.get("bookmakers", []):
        book_name = bookmaker.get("title", "Book")

        for market in bookmaker.get("markets", []):
            market_key = market.get("key")
            outcomes = market.get("outcomes", [])

            for outcome in outcomes:
                player = outcome.get("description")
                side = outcome.get("name")
                line = outcome.get("point")
                odds = outcome.get("price")

                if not player or line is None or odds is None:
                    continue

                group_key = (player, market_key, side, float(line))
                grouped.setdefault(group_key, []).append({
                    "book": book_name,
                    "odds": int(odds),
                    "implied_prob": implied_prob(int(odds)),
                })

    plays = []

    for (player, market_key, side, line), books in grouped.items():
        if len(books) < 2:
            continue

        # Best bettor-friendly odds:
        # for negative odds, closer to zero is better (e.g. -105 better than -130)
        # for positive odds, bigger is better (e.g. +110 better than +100)
        best = max(books, key=lambda x: x["odds"])
        avg_prob = sum(b["implied_prob"] for b in books) / len(books)
        best_prob = best["implied_prob"]

        # "Discrepancy" here = consensus market implied probability minus
        # the implied probability of the best available price.
        discrepancy = round((avg_prob - best_prob) * 100, 1)

        if discrepancy < 2.0:
            continue

        tag = "🔥 MAX PLAY" if discrepancy >= 5 else "✅ STRONG"

        key = make_pick_key(player, market_key, side, line, game_date)
        if key in sent_picks:
            continue

        plays.append({
            "key": key,
            "player": player,
            "stat": market_label(market_key),
            "market_key": market_key,
            "side": side,
            "line": line,
            "best_book": best["book"],
            "best_odds": best["odds"],
            "best_implied": round(best_prob * 100, 1),
            "market_avg_implied": round(avg_prob * 100, 1),
            "discrepancy": discrepancy,
            "books_compared": len(books),
            "game": game,
            "tag": tag,
        })

    plays.sort(key=lambda x: x["discrepancy"], reverse=True)
    return plays


# -----------------------------
# MAIN
# -----------------------------
def run_bot():
    print("Running bot...", flush=True)

    if not ODDS_API_KEY:
        print("Missing ODDS_API_KEY", flush=True)
        return

    events = get_events()
    all_plays = []

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        try:
            event_props = get_event_props(event_id)
            plays = collect_market_candidates(event_props)
            all_plays.extend(plays)
            time.sleep(1)
        except Exception as e:
            print(f"Event error: {e}", flush=True)

    all_plays.sort(key=lambda x: x["discrepancy"], reverse=True)

    if not all_plays:
        print("No qualifying plays found.", flush=True)
        return

    for play in all_plays:
        if play["discrepancy"] >= 5:
            color = 0x00FF00
        elif play["discrepancy"] >= 3:
            color = 0x0099FF
        else:
            color = 0xFF9900

        if play["stat"] in ["PTS", "PA", "PR", "PRA"]:
            emoji = "🏀"
        elif play["stat"] in ["REB", "RA", "B+S"]:
            emoji = "💪"
        elif play["stat"] in ["AST"]:
            emoji = "🎯"
        else:
            emoji = "📊"

        embed = {
            "title": f"SucioBot😷 {play['tag']} {emoji}",
            "description": f"**{play['player']} {play['side']} {play['line']} {play['stat']}**",
            "color": color,
            "fields": [
                {"name": "📍 Best Book", "value": play["best_book"], "inline": True},
                {"name": "💰 Best Odds", "value": str(play["best_odds"]), "inline": True},
                {"name": "📚 Books Compared", "value": str(play["books_compared"]), "inline": True},
                {"name": "🎯 Best Implied %", "value": f"{play['best_implied']}%", "inline": True},
                {"name": "📈 Market Avg %", "value": f"{play['market_avg_implied']}%", "inline": True},
                {"name": "⚡ Discrepancy", "value": f"+{play['discrepancy']}%", "inline": True},
                {"name": "🏟️ Game", "value": play["game"], "inline": False},
            ],
            "footer": {
                "text": datetime.now().strftime("%I:%M %p")
            }
        }

        send_discord_embed(embed)
        sent_picks.add(play["key"])
        time.sleep(1)

    save_sent_picks(sent_picks)


if __name__ == "__main__":
    while True:
        try:
            run_bot()
            time.sleep(300)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            time.sleep(30)
