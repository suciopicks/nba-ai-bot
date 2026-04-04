import os
import sys
import time
import json
import hashlib
from datetime import datetime

import requests

# 🚫 KILL SWITCH
if os.getenv("BOT_ENABLED", "true").lower() != "true":
    print("Bot is disabled. Exiting...")
    sys.exit(0)

SPORT = "basketball_nba"
REGIONS = "us"
BOOKMAKERS = "draftkings,fanduel,betmgm,caesars"
MARKETS = ",".join([
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_points_rebounds_assists",
])

ODDS_FORMAT = "american"
DATE_FORMAT = "iso"

EDGE_THRESHOLD = 2.0
SLEEP_SECONDS = 300
EVENT_DELAY_SECONDS = 2
DISCORD_DELAY_SECONDS = 1.5
MAX_EVENTS_PER_CYCLE = 10

SEEN_FILE = "seen_plays.json"
SEEN_TTL_SECONDS = 6 * 60 * 60


def get_webhook_url():
    return os.getenv("WEBHOOK_URL")


def get_odds_api_key():
    return os.getenv("ODDS_API_KEY")


def send_discord_embed(embed):
    webhook_url = get_webhook_url()

    if not webhook_url:
        print("❌ Missing WEBHOOK_URL", flush=True)
        return False

    try:
        response = requests.post(
            webhook_url,
            json={"embeds": [embed]},
            timeout=20
        )
        print(f"Discord status: {response.status_code}", flush=True)
        if response.text:
            print(f"Discord response: {response.text[:500]}", flush=True)
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
            f"**Consensus Price:** {play['consensus_price']}\n"
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
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump(seen, f, indent=2)
    except Exception as e:
        print(f"Error saving seen plays: {e}", flush=True)


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


def estimate_consensus_american(prices):
    decimals = [american_to_decimal(p["price"]) for p in prices]
    avg_decimal = sum(decimals) / len(decimals)

    if avg_decimal >= 2:
        return f"+{int((avg_decimal - 1) * 100)}"

    return str(int(-100 / (avg_decimal - 1)))


def market_label(key):
    labels = {
        "player_points": "Points",
        "player_rebounds": "Rebounds",
        "player_assists": "Assists",
        "player_points_rebounds_assists": "PRA",
    }
    return labels.get(key, key)


def get_events():
    odds_api_key = get_odds_api_key()

    print("🔑 ODDS_API_KEY loaded:", bool(odds_api_key), flush=True)
    print("🔑 Key length:", len(odds_api_key) if odds_api_key else 0, flush=True)

    if not odds_api_key:
        print("❌ ERROR: ODDS_API_KEY is missing", flush=True)
        return []

    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events"
    params = {
        "apiKey": odds_api_key,
        "dateFormat": DATE_FORMAT,
    }

    try:
        response = requests.get(url, params=params, timeout=30)

        print("🌐 Events request URL:", response.url, flush=True)
        print("📡 Events status:", response.status_code, flush=True)
        print(
            f"📊 Events requests remaining: {response.headers.get('x-requests-remaining')}",
            flush=True
        )
        print(
            f"📊 Events requests used: {response.headers.get('x-requests-used')}",
            flush=True
        )

        if response.text:
            print(f"📝 Events response: {response.text[:500]}", flush=True)

        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        print(f"❌ Events HTTP error: {e}", flush=True)
        return []
    except Exception as e:
        print(f"❌ Events general error: {e}", flush=True)
        return []


def get_event_props(event_id):
    odds_api_key = get_odds_api_key()

    if not odds_api_key:
        print("❌ ERROR: ODDS_API_KEY missing before props request", flush=True)
        return None

    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds"
    params = {
        "apiKey": odds_api_key,
        "regions": REGIONS,
        "markets": MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": ODDS_FORMAT,
        "dateFormat": DATE_FORMAT,
    }

    response = requests.get(url, params=params, timeout=30)

    print(f"Props status for {event_id}: {response.status_code}", flush=True)
    if response.text:
        print(f"Props response text for {event_id}: {response.text[:500]}", flush=True)
    print(
        f"Props requests remaining: {response.headers.get('x-requests-remaining')}",
        flush=True
    )
    print(
        f"Props requests used: {response.headers.get('x-requests-used')}",
        flush=True
    )

    response.raise_for_status()
    return response.json()


def group_outcomes_by_player(event_odds):
    grouped = {}

    for bookmaker in event_odds.get("bookmakers", []):
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


def find_best_edges(event_odds):
    plays = []
    grouped = group_outcomes_by_player(event_odds)

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
            "game_id": event_odds.get("id"),
            "home_team": event_odds.get("home_team"),
            "away_team": event_odds.get("away_team"),
            "commence_time": event_odds.get("commence_time"),
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
    print("Cycle env check - WEBHOOK_URL:", bool(get_webhook_url()), flush=True)
    print("Cycle env check - ODDS_API_KEY:", bool(get_odds_api_key()), flush=True)

    seen = cleanup_seen(load_seen())

    try:
        events = get_events()
        print(f"Events returned: {len(events)}", flush=True)

        if not events:
            save_seen(seen)
            print("No events found.", flush=True)
            return

        events = events[:MAX_EVENTS_PER_CYCLE]
        print(f"Scanning first {len(events)} events this cycle...", flush=True)

        all_plays = []

        for event in events:
            event_id = event.get("id")
            if not event_id:
                continue

            try:
                event_odds = get_event_props(event_id)

                if not event_odds:
                    continue

                plays = find_best_edges(event_odds)
                all_plays.extend(plays)
                time.sleep(EVENT_DELAY_SECONDS)

            except requests.HTTPError as e:
                print(f"HTTP error on event {event_id}: {e}", flush=True)
                time.sleep(3)
            except Exception as e:
                print(f"Unexpected event error on {event_id}: {e}", flush=True)
                time.sleep(3)

        all_plays.sort(key=lambda x: x["edge"], reverse=True)

        sent_count = 0

        for play in all_plays:
            play_key = make_play_key(play)

            if play_key in seen:
                continue

            if send_play(play):
                seen[play_key] = time.time()
                sent_count += 1
                time.sleep(DISCORD_DELAY_SECONDS)

        save_seen(seen)
        print(f"Total plays found: {len(all_plays)}", flush=True)
        print(f"Sent plays: {sent_count}", flush=True)

    except requests.HTTPError as e:
        response = getattr(e, "response", None)

        if response is not None and response.status_code == 429:
            print("Hit 429 rate limit. Sleeping 15 minutes.", flush=True)
            time.sleep(900)
        else:
            print(f"HTTP error: {e}", flush=True)
            time.sleep(120)

    except Exception as e:
        print(f"Unexpected error: {e}", flush=True)
        time.sleep(120)


if __name__ == "__main__":
    while True:
        try:
            print(f"\n--- Bot cycle started at {datetime.now()} ---", flush=True)
            print("Startup check - WEBHOOK_URL:", bool(get_webhook_url()), flush=True)
            print("Startup check - ODDS_API_KEY:", bool(get_odds_api_key()), flush=True)

            run_bot()

            print(f"Sleeping {SLEEP_SECONDS} seconds...\n", flush=True)
            time.sleep(SLEEP_SECONDS)

        except Exception as e:
            print(f"MAIN LOOP ERROR: {e}", flush=True)
            time.sleep(60)
