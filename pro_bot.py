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
BOOKMAKERS = "draftkings,fanduel"

MARKETS = ",".join([
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_points_rebounds_assists",
])

ODDS_FORMAT = "american"
DATE_FORMAT = "iso"

EDGE_THRESHOLD = 6.0
SLEEP_SECONDS = 300

SEEN_FILE = "seen_plays.json"
SEEN_TTL_SECONDS = 6 * 60 * 60


def send_discord_embed(embed):
    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL", flush=True)
        return False

    try:
        response = requests.post(
            WEBHOOK_URL,
            json={"embeds": [embed]},
            timeout=20
        )
        print(f"Discord status: {response.status_code}", flush=True)
        print(f"Discord response: {response.text}", flush=True)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Discord send error: {e}", flush=True)
        return False


def send_play(play):
    embed = {
        "title": f"🔥 {play['player']} — {play['market_name']}",
        "description": (
            f"**Game:** {play['away_team']} @ {play['home_team']}\n"
            f"**Pick:** {play['side']} {play['line']}\n"
            f"**Best Book:** {play['best_book']} ({play['best_price']})\n"
            f"**Consensus:** {play['consensus_price']}\n"
            f"**Edge:** {play['edge']:.2f}%\n"
            f"**Start:** {play['commence_time']}"
        ),
        "color": 0x00FF00,
        "footer": {
            "text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }
    return send_discord_embed(embed)


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
    cleaned = {}
    for key, ts in seen.items():
        if now - ts < SEEN_TTL_SECONDS:
            cleaned[key] = ts
    return cleaned


def make_play_key(play):
    raw = (
        f"{play['game_id']}|{play['player']}|{play['market_key']}|"
        f"{play['side']}|{play['line']}|{play['best_book']}"
    )
    return hashlib.md5(raw.encode()).hexdigest()


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

    print(f"Odds status: {response.status_code}", flush=True)
    print(f"Response text: {response.text}", flush=True)
    print(f"Requests remaining: {response.headers.get('x-requests-remaining')}", flush=True)
    print(f"Requests used: {response.headers.get('x-requests-used')}", flush=True)

    response.raise_for_status()
    return response.json()


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
    labels = {
        "player_points": "Points",
        "player_rebounds": "Rebounds",
        "player_assists": "Assists",
    }
    return labels.get(key, key)


def group_outcomes_by_player(game):
    grouped = {}

    for bookmaker in game.get("bookmakers", []):
        book_name = bookmaker.get("title", "Unknown Book")

        for market in bookmaker.get("markets", []):
            market_key = market.get("key")

            for outcome in market.get("outcomes", []):
                player = outcome.get("description")
                side = outcome.get("name")
                line = outcome.get("point")
                price = outcome.get("price")

                if not player or side not in ("Over", "Under"):
                    continue
                if line is None or price is None:
                    continue

                bucket_key = (player, market_key, side, float(line))
                grouped.setdefault(bucket_key, []).append({
                    "bookmaker": book_name,
                    "price": int(price),
                })

    return grouped


def estimate_consensus_american(prices):
    decimals = [american_to_decimal(p["price"]) for p in prices]
    avg_decimal = sum(decimals) / len(decimals)

    if avg_decimal >= 2:
        return f"+{int((avg_decimal - 1) * 100)}"
    return str(int(-100 / (avg_decimal - 1)))


def find_best_edges(game):
    plays = []
    grouped = group_outcomes_by_player(game)

    for (player, market_key, side, line), prices in grouped.items():
        if len(prices) < 2:
            continue

        best = max(prices, key=lambda x: x["price"])

        implied_probs = [implied_prob(p["price"]) for p in prices]
        consensus_prob = sum(implied_probs) / len(implied_probs)
        best_prob = implied_prob(best["price"])
        edge = consensus_prob - best_prob

        if edge < EDGE_THRESHOLD:
            continue

        play = {
            "game_id": game.get("id"),
            "home_team": game.get("home_team"),
            "away_team": game.get("away_team"),
            "commence_time": game.get("commence_time"),
            "player": player,
            "market_key": market_key,
            "market_name": market_label(market_key),
            "side": side,
            "line": line,
            "best_book": best["bookmaker"],
            "best_price": best["price"],
            "consensus_price": estimate_consensus_american(prices),
            "edge": edge,
        }
        plays.append(play)

    return plays


def run_bot():
    seen = cleanup_seen(load_seen())

    try:
        games = get_nba_odds()
        print(f"Games returned: {len(games)}", flush=True)

        all_plays = []
        for game in games:
            all_plays.extend(find_best_edges(game))

        all_plays.sort(key=lambda x: x["edge"], reverse=True)

        sent_count = 0
        for play in all_plays:
            play_key = make_play_key(play)

            if play_key in seen:
                continue

            if send_play(play):
                seen[play_key] = time.time()
                sent_count += 1
                time.sleep(1.5)

        save_seen(seen)
        print(f"Sent plays: {sent_count}", flush=True)

    except requests.HTTPError as e:
        print(f"HTTP error: {e}", flush=True)
        time.sleep(120)

    except Exception as e:
        print(f"Unexpected error: {e}", flush=True)
        time.sleep(120)


if __name__ == "__main__":
    print("Webhook:", WEBHOOK_URL, flush=True)
    print("API Key:", ODDS_API_KEY, flush=True)

    while True:
        try:
            print(f"\n--- Bot cycle started at {datetime.now()} ---", flush=True)
            run_bot()
            print(f"Sleeping {SLEEP_SECONDS} seconds...\n", flush=True)
            time.sleep(SLEEP_SECONDS)
        except Exception as e:
            print(f"MAIN LOOP ERROR: {e}", flush=True)
            time.sleep(60)
