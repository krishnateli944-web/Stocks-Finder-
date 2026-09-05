import requests
import os
import json
import argparse
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

WATCHLIST_FILE = "watchlist.txt"
SEEN_FILE = "seen_announcements.json"
TELEGRAM_MSG_LIMIT = 3500

GOOD_NEWS_KEYWORDS = [
    "order", "contract", "award", "bags", "wins", "bagging",
    "financial result", "results",
]

BAD_NEWS_KEYWORDS = [
    "resign", "resignation", "default", "fraud", "raid", "sebi",
    "investigation", "downgrade", "loss", "postpone", "delay",
    "insolvency", "bankrupt", "qualified opinion", "show cause",
    "penalty", "fine", "litigation", "strike", "lockout", "suspend",
    "auditor", "cbi", "ed ", "search and seizure",
]


def get_nse_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "*/*",
    })
    session.get("https://www.nseindia.com", timeout=10)
    return session


def get_announcements(session):
    url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def load_list(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r") as f:
        return set(json.load(f))


def save_seen(seen_set):
    trimmed = list(seen_set)[-500:]
    with open(SEEN_FILE, "w") as f:
        json.dump(trimmed, f)


def make_key(item):
    return f"{item.get('symbol','')}|{item.get('an_dt','')}|{item.get('desc','')[:50]}"


def matches_any(text, keywords):
    text_l = text.lower()
    return any(k in text_l for k in keywords)


def send_telegram_alert(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    r = requests.post(url, data=payload, timeout=10)
    return r.ok


def send_batched(lines):
    if not lines:
        return
    header = f"📰 *Market News Alerts* — {datetime.now(IST).strftime('%d-%b-%Y %H:%M')} IST\n\n"
    chunk = header
    for line in lines:
        if len(chunk) + len(line) > TELEGRAM_MSG_LIMIT:
            send_telegram_alert(chunk)
            chunk = ""
        chunk += line + "\n\n"
    if chunk.strip():
        send_telegram_alert(chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", action="store_true", help="Save raw announcements to JSON file")
    args = parser.parse_args()

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing")
        return

    watchlist = load_list(WATCHLIST_FILE)
    seen = load_seen()

    try:
        session = get_nse_session()
        announcements = get_announcements(session)
    except Exception as e:
        print(f"NSE announcements fetch fail hui: {e}")
        return

    # Save raw announcements for external analysis
    if args.output_json:
        with open("raw_announcements.json", "w") as f:
            json.dump(announcements, f, indent=2)
        print(f"Saved {len(announcements)} raw announcements to raw_announcements.json")

    good_news_lines = []
    bad_news_lines = []

    for item in announcements:
        key = make_key(item)
        if key in seen:
            continue
        seen.add(key)

        symbol = item.get("symbol", "?")
        desc = item.get("desc", "")
        attachment_text = item.get("attchmntText", "") or ""
        full_text = f"{desc} {attachment_text}"

        if symbol.upper() in watchlist and matches_any(full_text, BAD_NEWS_KEYWORDS):
            bad_news_lines.append(
                f"🚨 *URGENT — {symbol}* (tumhari holding)\n{desc}\n{attachment_text[:200]}"
            )
        elif matches_any(full_text, GOOD_NEWS_KEYWORDS):
            good_news_lines.append(
                f"💰 *{symbol}*\n{desc}\n{attachment_text[:150]}"
            )

    save_seen(seen)

    if bad_news_lines:
        send_batched(bad_news_lines)
        print(f"{len(bad_news_lines)} urgent watchlist alert(s) bheja")

    if good_news_lines:
        send_batched(good_news_lines)
        print(f"{len(good_news_lines)} market-wide good-news alert(s) bheja")

    if not bad_news_lines and not good_news_lines:
        print("Is run mein koi naya relevant announcement nahi mila")


if __name__ == "__main__":
    main()
