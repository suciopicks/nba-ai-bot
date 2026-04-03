import os
import time
import json
import hashlib
from datetime import datetime
def team_abbr_from_name(team_name):
    mapping = {
        "Atlanta Hawks": "atl",
        "Boston Celtics": "bos",
        "Brooklyn Nets": "bkn",
        "Charlotte Hornets": "cha",
        "Chicago Bulls": "chi",
        "Cleveland Cavaliers": "cle",
        "Dallas Mavericks": "dal",
        "Denver Nuggets": "den",
        "Detroit Pistons": "det",
        "Golden State Warriors": "gsw",
        "Houston Rockets": "hou",
        "Indiana Pacers": "ind",
        "LA Clippers": "lac",
        "Los Angeles Clippers": "lac",
        "Los Angeles Lakers": "lal",
        "Memphis Grizzlies": "mem",
        "Miami Heat": "mia",
        "Milwaukee Bucks": "mil",
        "Minnesota Timberwolves": "min",
        "New Orleans Pelicans": "nop",
        "New York Knicks": "nyk",
        "Oklahoma City Thunder": "okc",
        "Orlando Magic": "orl",
        "Philadelphia 76ers": "phi",
        "Phoenix Suns": "phx",
        "Portland Trail Blazers": "por",
        "Sacramento Kings": "sac",
        "San Antonio Spurs": "sas",
        "Toronto Raptors": "tor",
        "Utah Jazz": "uta",
        "Washington Wizards": "wsh",
    }
    return mapping.get(team_name)


def get_team_logo_url(game_string):
    try:
        away_team, home_team = [x.strip() for x in game_string.split("@")]
        home_abbr = team_abbr_from_name(home_team)
        if not home_abbr:
            return None
        return f"https://i.cdn.turner.com/nba/nba/.element/img/4.0/global/logos/512x512/bg.white/{home_abbr}.png"
    except Exception:
        return None
import requests

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

SPORT = "basketball_nba"
REGIONS = "us"
BOOKMAKERS = "draftkings,fanduel"
MARKETS = "player_points,player_rebounds,player_assists"
SENT_FILE = "sent_picks.json"


def load_sent_picks():
    try:
        with open(SENT_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_sent_picks(sent_keys):
    with open(SENT_FILE, "w") as f:
        json.dump(sorted(list(sent_keys)), f)


sent_picks = load_sent_picks()


def send_discord_embed(embed):
    if not WEBHOOK_URL:
        print("Missing WEBHOOK_URL", flush=True)
        return

    payload = {
        "embeds": [embed]
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=20)
        print(f"Discord status: {response.status_code}", flush=True)
    except Exception as e:
        print(f"DISCORD ERROR: {e}", flush=True)


def american_implied_prob(odds):
    if odds is None:
        return None
    odds = int(odds)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def get_events():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events"
    params = {"apiKey": ODDS_API_KEY}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def get_event_props(event_id):
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": "american",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def fake_projection_from_line(line, market_key):
    # placeholder projection logic until you add your own model
    if market_key == "player_points":
        return round(line + 1.8, 1)
    if market_key == "player_rebounds":
        return round(line + 0.9, 1)
    if market_key == "player_assists":
        return round(line + 0.7, 1)
    return round(line + 0.5, 1)


def model_probability(line, projection):
    diff = projection - line
    prob = 0.50 + (diff * 0.045)
    return max(0.25, min(0.80, prob))


def pick_key(bookmaker, player, market, side, line):
    raw = f"{bookmaker}|{player}|{market}|{side}|{line}"
    return hashlib.md5(raw.encode()).hexdigest()


def build_embed(play):
    return {
        "title": f"{play['tag']} NBA PROP",
        "description": f"**{play['player']} {play['side']} {play['line']} {play['stat']}**",
        "fields": [
            {"name": "Book", "value": play["bookmaker"], "inline": True},
            {"name": "Odds", "value": str(play["odds"]), "inline": True},
            {"name": "Projection", "value": str(play["projection"]), "inline": True},
            {"name": "Edge", "value": f"+{play['edge']}%", "inline": True},
            {"name": "Model", "value": f"{play['model_prob']}%", "inline": True},
            {"name": "Vegas", "value": f"{play['vegas_prob']}%", "inline": True},
            {"name": "Game", "value": play["game"], "inline": False},
            {"name": "Time", "value": datetime.now().strftime("%I:%M %p"), "inline": True},
        ],
        "footer": {"text": "AI NBA Props Bot"},
    }


def market_label(market_key):
    return {
        "player_points": "PTS",
        "player_rebounds": "REB",
        "player_assists": "AST",
    }.get(market_key, market_key)


def analyze_event(event):
    plays = []
    game_name = f"{event.get('away_team', 'Away')} @ {event.get('home_team', 'Home')}"

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

                projection = fake_projection_from_line(float(line), market_key)
                model_prob = model_probability(float(line), projection)
                vegas_prob = american_implied_prob(int(odds))

                if vegas_prob is None:
                    continue

                edge = round((model_prob - vegas_prob) * 100, 1)

                if edge < 6:
                    continue

                key = pick_key(book_name, player, market_key, side, line)
                if key in sent_picks:
                    continue

                tag = "🔥 MAX PLAY" if edge >= 8 else "✅ STRONG"

                plays.append({
                    "key": key,
                    "player": player,
                    "side": side,
                    "line": line,
                    "stat": market_label(market_key),
                    "odds": odds,
                    "projection": projection,
                    "model_prob": round(model_prob * 100, 1),
                    "vegas_prob": round(vegas_prob * 100, 1),
                    "edge": edge,
                    "bookmaker": book_name,
                    "tag": tag,
                    "game": game_name,
                })

    plays.sort(key=lambda x: x["edge"], reverse=True)
    return plays[:3]


def run_bot():
    print("Running bot...", flush=True)

    events = get_events()
    all_plays = []

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        try:
            event_props = get_event_props(event_id)
            all_plays.extend(analyze_event(event_props))
            time.sleep(1)
        except Exception as e:
            print(f"Event error: {e}", flush=True)

    all_plays.sort(key=lambda x: x["edge"], reverse=True)

    if not all_plays:
        print("No plays found.", flush=True)
        return

    grouped = {
        "PTS": [],
        "REB": [],
        "AST": [],
    }

    for play in all_plays:
        if play["stat"] in grouped:
            grouped[play["stat"]].append(play)

    sections = []

    for stat_name, plays in grouped.items():
        if not plays:
            continue

        section = f"## {stat_name}\n\n"

        for play in plays:
            emoji = "🏀" if play["stat"] == "PTS" else "💪" if play["stat"] == "REB" else "🎯"

            section += (
                f"{play['tag']} {emoji}\n"
                f"**{play['player']} {play['side']} {play['line']} {play['stat']}**\n"
                f"📍 Book: {play['bookmaker']}\n"
                f"💰 Odds: {play['odds']}\n"
                f"📊 Projection: {play['projection']}\n"
                f"📈 Model: {play['model_prob']}%\n"
                f"🎯 Vegas: {play['vegas_prob']}%\n"
                f"⚡ Discrepancy: +{play['edge']}%\n"
                f"🏟️ Game: {play['game']}\n\n"
            )

        sections.append(section)

    full_text = "".join(sections)

    chunks = []
    current_chunk = ""

    for section in sections:
        if len(current_chunk) + len(section) > 3500:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = section
        else:
            current_chunk += section

    if current_chunk:
        chunks.append(current_chunk)

    for i, chunk in enumerate(chunks):
        top_edge = all_plays[0]["edge"]

        if top_edge >= 9:
            color = 0x00FF00
        elif top_edge >= 7:
            color = 0x0099FF
        else:
            color = 0xFF9900
            
        logo_url = get_team_logo_url(play["game"])

        embed = {
            "title": "SucioBot😷" if i == 0 else "SucioBot😷 (cont.)",
            "description": chunk,
            "color": color,
            "footer": {
                "text": f"Updated {datetime.now().strftime('%I:%M %p')}"
            }
        }
        
        if logo_url:
            embed["thumbnail"] = {"url": logo_url}
            
        send_discord_embed(embed)
        time.sleep(1)

    for play in all_plays:
        sent_picks.add(play["key"])

    save_sent_picks(sent_picks)


if __name__ == "__main__":
    while True:
        try:
            run_bot()
            print("Sleeping...", flush=True)
            time.sleep(300)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            time.sleep(30)
