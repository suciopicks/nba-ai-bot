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

# Keep this limited or you can still burn requests / credits faster
MARKETS = ",".join([
    "h2h",
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_points_rebounds",
    "player_points_assists",
    "player_rebounds_assists",
    "player_points_rebounds_assists",
])

ODDS_FORMAT = "american"
DATE_FORMAT = "iso"

# Minimum edge between books before sending
EDGE_THRESHOLD = 6.0

# Main loop delay
SLEEP_SECONDS = 300

# Prevent duplicate spam
SEEN_FILE = "seen_plays.json"
SEEN_TTL_SECONDS = 6 * 60 * 60  # 6 hours


# -----------------------------
# DISCORD
# -----------------------------
def send_discord_embed(embed):
    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL")
        return False

    try:
        response = requests.post(
            WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=20
        )
        print(f"Discord status: {response.status_code}")
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Discord send error: {e}")
        return False


def send_play(play):
    title = f"🔥 {play['player']} — {play['market_name']}"
    description = (
        f"**Game:** {play['away_team']} @ {play['home_team']}\n"
        f"**Pick:** {play['over_under']} {play['line']}\n"
        f"**Best Book:** {play['best_book']} ({play['best_price']})\n"
        f"**Consensus Price:** {play['consensus_price']}\n"
        f"**Edge:** {play['edge']:.2f}%\n"
        f"**Favorite/Underdog:** {play['favorite_info']}\n"
        f"**Start:** {play['commence_time']}"
    )

    embed = {
        "title": title,
        "description": description,
        "color": 0x00FF00,
        "footer": {
            "text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }

    return send_discord_embed(embed)


# -----------------------------
# STORAGE
# -----------------------------
def load_seen():
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=2)


def cleanup_seen(seen):
    now = time.time()
    fresh = {}
    for k, ts in seen.items():
        if now - ts < SEEN_TTL_SECONDS:
            fresh[k] = ts
    return fresh


def make_play_key(play):
    raw = (
        f"{play['game_id']}|{play['player']}|{play['market_key']}|"
        f"{play['over_under']}|{play['line']}|{play['best_book']}"
    )
    return hashlib.md5(raw.encode()).hexdigest()


# -----------------------------
# API
# -----------------------------
def get_nba_odds():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds"

    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": DATE_FORMAT,
    }

    response = requests.get(url, params=params, timeout=30)

    print(f"Odds status: {response.status_code}")
    print(f"Requests remaining: {response.headers.get('x-requests-remaining')}")
    print(f"Requests used: {response.headers.get('x-requests-used')}")

    if response.status_code == 429:
        raise requests.HTTPError("429 Too Many Requests", response=response)

    response.raise_for_status()
    return response.json()


# -----------------------------
# HELPERS
# -----------------------------
def implied_prob(odds):
    odds = int(odds)
    if odds > 0:
        return 100 / (odds + 100) * 100
    return abs(odds) / (abs(odds) + 100) * 100


def american_to_decimal(odds):
    odds = int(odds)
    if odds > 0:
        return 1 + (odds / 100)
    return 1 + (100 / abs(odds))


def market_label(key):
    mapping = {
        "player_points": "Points",
        "player_rebounds": "Rebounds",
        "player_assists": "Assists",
        "player_threes": "3PT Made",
        "player_points_rebounds": "PR",
        "player_points_assists": "PA",
        "player_rebounds_assists": "RA",
        "player_points_rebounds_assists": "PRA",
    }
    return mapping.get(key, key)


def get_favorite_info(game):
    h2h_market = None

    for bookmaker in game.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market.get("key") == "h2h":
                h2h_market = market
                break
        if h2h_market:
            break

    if not h2h_market:
        return "N/A"

    outcomes = h2h_market.get("outcomes", [])
    if len(outcomes) < 2:
        return "N/A"

    sorted_outcomes = sorted(outcomes, key=lambda x: int(x["price"]))
    favorite = sorted_outcomes[0]
    underdog = sorted_outcomes[-1]

    return f"{favorite['name']} favored over {underdog['name']}"


def group_outcomes_by_player(game):
    grouped = {}

    for bookmaker in game.get("bookmakers", []):
        book_name = bookmaker.get("title", "Unknown Book")

        for market in bookmaker.get("markets", []):
            key = market.get("key")

            if key == "h2h":
                continue

            for outcome in market.get("outcomes", []):
                player = outcome.get("description")
                side = outcome.get("name")  # Over / Under
                line = outcome.get("point")
                price = outcome.get("price")

                if player is None or line is None or price is None or side not in ("Over", "Under"):
                    continue

                bucket_key = (player, key, side, float(line))
                grouped.setdefault(bucket_key, []).append({
                    "bookmaker": book_name,
                    "price": int(price),
                })

    return grouped


def find_best_edges(game):
    plays = []
    grouped = group_outcomes_by_player(game)
    favorite_info = get_favorite_info(game)

    for (player, market_key, side, line), prices in grouped.items():
        if len(prices) < 2:
            continue

        # Best payout number for bettor
        best = max(prices, key=lambda x: x["price"])

        implied_probs = [implied_prob(p["price"]) for p in prices]
        consensus_prob = sum(implied_probs) / len(implied_probs)
        best_prob = implied_prob(best["price"])

        edge = consensus_prob - best_prob

        if edge < EDGE_THRESHOLD:
            continue

        consensus_decimal = sum(american_to_decimal(p["price"]) for p in prices) / len(prices)

        # crude convert back to approximate american display
        if consensus_decimal >= 2:
            consensus_american = int((consensus_decimal - 1) * 100)
            consensus_american = f"+{consensus_american}"
        else:
            consensus_american = int(-100 / (consensus_decimal - 1))
            consensus_american = str(consensus_american)

        play = {
            "game_id": game.get("id"),
            "home_team": game.get("home_team"),
            "away_team": game.get("away_team"),
            "commence_time": game.get("commence_time"),
            "player": player,
            "market_key": market_key,
            "market_name": market_label(market_key),
            "over_under": side,
            "line": line,
            "best_book": best["bookmaker"],
            "best_price": best["price"],
            "consensus_price": consensus_american,
            "edge": edge,
            "favorite_info": favorite_info,
        }
        plays.append(play)

    return plays


# -----------------------------
# MAIN
# -----------------------------
def run_bot():
    seen = cleanup_seen(load_seen())

    try:
        games = get_nba_odds()
        print(f"Games returned: {len(games)}")

        all_plays = []

        for game in games:
            plays = find_best_edges(game)
            all_plays.extend(plays)

        all_plays.sort(key=lambda x: x["edge"], reverse=True)

        sent_count = 0
        for play in all_plays:
            key = make_play_key(play)
            if key in seen:
                continue

            ok = send_play(play)
            if ok:
                seen[key] = time.time()
                sent_count += 1
                time.sleep(1.5)  # small pause so Discord isn't spammed too fast

        save_seen(seen)
        print(f"Sent plays: {sent_count}")

    except requests.HTTPError as e:
        response = getattr(e, "response", None)
        if response is not None and response.status_code == 429:
            print("Hit 429 rate limit. Sleeping 15 minutes.")
            time.sleep(900)
        else:
            print(f"HTTP error: {e}")
            time.sleep(120)

    except Exception as e:
        print(f"Unexpected error: {e}")
        time.sleep(120)


if __name__ == "__main__":
    print("Webhook:", WEBHOOK_URL)
    print("API Key:", ODDS_API_KEY)

    while True:
        print(f"\n--- Bot cycle started at {datetime.now()} ---")
        run_bot()
        print(f"Sleeping {SLEEP_SECONDS} seconds...\n")
        time.sleep(SLEEP_SECONDS)
