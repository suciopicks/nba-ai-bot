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

MARKETS = ",".join([
    "h2h",
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
    try:
        with open(SENT_FILE, "w") as f:
            json.dump(sorted(list(picks)), f)
    except Exception as e:
        print(f"SAVE FILE ERROR: {e}", flush=True)


sent_picks = load_sent_picks()


# -----------------------------
# DISCORD
# -----------------------------
def send_discord_embed(embed):
    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL", flush=True)
        return False

    try:
        response = requests.post(
            WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=20,
        )

        print(f"Discord status: {response.status_code}", flush=True)
        print(f"Discord response: {response.text}", flush=True)

        if response.status_code in (200, 204):
            print("Discord embed sent successfully.", flush=True)
            return True
        else:
            print("Failed to send Discord embed.", flush=True)
            return False

    except Exception as e:
        print(f"DISCORD ERROR: {e}", flush=True)
        return False


def send_startup_test():
    embed = {
        "title": "SucioBot😷 TEST",
        "description": "✅ Bot is online and running",
        "color": 0x00FF00,
        "footer": {
            "text": datetime.now().strftime("%Y-%m-%d %I:%M %p")
        }
    }
    return send_discord_embed(embed)


# -----------------------------
# API
# -----------------------------
def get_events():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events"
    params = {"apiKey": ODDS_API_KEY}
    response = requests.get(url, params=params, timeout=20)
    print(f"Events status: {response.status_code}", flush=True)
    print(f"Events remaining requests: {response.headers.get('x-requests-remaining')}", flush=True)
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
    print(f"Props status for {event_id}: {response.status_code}", flush=True)
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


def smart_projection(line, market_key):
    if market_key == "player_points":
        return round(line * 1.08, 1)
    if market_key == "player_rebounds":
        return round(line * 1.10, 1)
    if market_key == "player_assists":
        return round(line * 1.07, 1)
    if market_key == "player_threes":
        return round(line * 1.09, 1)
    if market_key == "player_blocks":
        return round(line * 1.12, 1)
    if market_key == "player_steals":
        return round(line * 1.12, 1)
    if market_key == "player_turnovers":
        return round(line * 1.06, 1)
    if market_key == "player_blocks_steals":
        return round(line * 1.10, 1)
    if market_key == "player_points_assists":
        return round(line * 1.06, 1)
    if market_key == "player_points_rebounds":
        return round(line * 1.07, 1)
    if market_key == "player_rebounds_assists":
        return round(line * 1.08, 1)
    if market_key == "player_points_rebounds_assists":
        return round(line * 1.06, 1)
    if market_key == "player_fantasy_points":
        return round(line * 1.05, 1)
    return round(line * 1.05, 1)


def model_probability(line, projection):
    diff = projection - line
    prob = 0.50 + (diff * 0.04)
    return max(0.25, min(0.80, prob))


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


def extract_favorite_underdog(event):
    away_team = event.get("away_team", "Away")
    home_team = event.get("home_team", "Home")

    team_probs = {
        away_team: [],
        home_team: [],
    }

    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market.get("key") != "h2h":
                continue

            for outcome in market.get("outcomes", []):
                team_name = outcome.get("name")
                price = outcome.get("price")

                if team_name in team_probs and price is not None:
                    team_probs[team_name].append(implied_prob(price))

    away_avg = (
        sum(team_probs[away_team]) / len(team_probs[away_team])
        if team_probs[away_team] else None
    )
    home_avg = (
        sum(team_probs[home_team]) / len(team_probs[home_team])
        if team_probs[home_team] else None
    )

    if away_avg is None or home_avg is None:
        return "N/A", "N/A"

    if away_avg > home_avg:
        return away_team, home_team

    return home_team, away_team


# -----------------------------
# MARKET / MODEL ENGINE
# -----------------------------
def collect_market_candidates(event):
    grouped = {}
    game = f"{event.get('away_team', 'Away')} @ {event.get('home_team', 'Home')}"
    game_date = event.get("commence_time", "")
    favorite, underdog = extract_favorite_underdog(event)

    for bookmaker in event.get("bookmakers", []):
        book_name = bookmaker.get("title", "Book")

        for market in bookmaker.get("markets", []):
            market_key = market.get("key")

            if market_key == "h2h":
                continue

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
        if len(books) < 1:
            continue

        best = max(books, key=lambda x: x["odds"])
        avg_prob = sum(b["implied_prob"] for b in books) / len(books)
        best_prob = best["implied_prob"]

        projection = smart_projection(line, market_key)
        model_prob = model_probability(line, projection)

        discrepancy = round((model_prob - best_prob) * 100, 1)
        
        print(f"{player} {side} {line} | proj={projection} | model={round(model_prob*100,1)}% | book={round(best_prob*100,1)}% | edge={discrepancy}%", flush=True)

        if discrepancy < 7.0:
            continue

        # prioritize strong stat types
        if market_key not in ["player_points_rebounds_assists", "player_points_assists", "player_points_rebounds"]:
            continue

        tag = "🔥 MAX PLAY" if discrepancy >= 8 else "✅ STRONG"

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
            "projection": projection,
            "model_prob": round(model_prob * 100, 1),
            "best_book": best["book"],
            "best_odds": best["odds"],
            "best_implied": round(best_prob * 100, 1),
            "market_avg_implied": round(avg_prob * 100, 1),
            "discrepancy": discrepancy,
            "books_compared": len(books),
            "game": game,
            "favorite": favorite,
            "underdog": underdog,
            "tag": tag,
        })

    plays.sort(key=lambda x: x["discrepancy"], reverse=True)
    return plays


# -----------------------------
# MAIN BOT RUN
# -----------------------------
def run_bot():
    print("Running bot...", flush=True)

    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL", flush=True)
        return

    if not ODDS_API_KEY:
        print("Missing ODDS_API_KEY", flush=True)
        return

    try:
        events = get_events()
        print(f"Found {len(events)} events", flush=True)
    except Exception as e:
        print(f"GET EVENTS ERROR: {e}", flush=True)
        return

    all_plays = []

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        try:
            event_props = get_event_props(event_id)
            plays = collect_market_candidates(event_props)
            print(f"Event {event_id} -> {len(plays)} plays", flush=True)
            all_plays.extend(plays)
            time.sleep(1)
        except Exception as e:
            print(f"Event error ({event_id}): {e}", flush=True)

    all_plays.sort(key=lambda x: x["discrepancy"], reverse=True)

    if not all_plays:
        print("No qualifying plays found.", flush=True)
        return

    print(f"Total plays found: {len(all_plays)}", flush=True)

    for play in all_plays:
        if play["discrepancy"] >= 8:
            color = 0x00FF00
        elif play["discrepancy"] >= 6:
            color = 0x0099FF
        else:
            color = 0xFF9900

        if play["stat"] in ["PTS", "PA", "PR", "PRA", "FP"]:
            emoji = "🏀"
        elif play["stat"] in ["REB", "RA", "B+S", "BLK", "STL"]:
            emoji = "💪"
        elif play["stat"] in ["AST", "3PM"]:
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
                {"name": "📊 Projection", "value": str(play["projection"]), "inline": True},
                {"name": "🧠 Model %", "value": f"{play['model_prob']}%", "inline": True},
                {"name": "🎯 Best Implied %", "value": f"{play['best_implied']}%", "inline": True},
                {"name": "📈 Market Avg %", "value": f"{play['market_avg_implied']}%", "inline": True},
                {"name": "⚡ Discrepancy", "value": f"+{play['discrepancy']}%", "inline": True},
                {"name": "📚 Books Compared", "value": str(play["books_compared"]), "inline": True},
                {"name": "⭐ Favorite", "value": play["favorite"], "inline": True},
                {"name": "🐶 Underdog", "value": play["underdog"], "inline": True},
                {"name": "🏟️ Game", "value": play["game"], "inline": False},
            ],
            "footer": {
                "text": datetime.now().strftime("%I:%M %p")
            }
        }

        sent_ok = send_discord_embed(embed)
        if sent_ok:
            sent_picks.add(play["key"])
            save_sent_picks(sent_picks)

        time.sleep(1)


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    print("Bot starting...", flush=True)

    # sends one test message immediately when the script starts
    send_startup_test()

    while True:
        try:
            run_bot()
            print("Sleeping 300 seconds...", flush=True)
            time.sleep(300)  # every 5 minutes
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            time.sleep(30)
