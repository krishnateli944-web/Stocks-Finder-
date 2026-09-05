import os
import argparse
import json
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

IST = timezone(timedelta(hours=5, minutes=30))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SCAN_CLAUSES = {
    "VCP / Trend Template Breakout": (
        "( {cash} ( market cap > 20000 and daily avg true range( 14 ) < 10 days ago avg true range( 14 ) "
        "and daily avg true range( 14 ) / daily close < 0.08 and daily close > weekly max( 52 , daily close ) * 0.75 "
        "and daily ema( daily close , 50 ) > daily ema( daily close , 150 ) "
        "and daily ema( daily close , 150 ) > daily ema( daily close , 200 ) "
        "and daily close > daily ema( daily close , 50 ) and daily close > 10 "
        "and daily close * daily volume > 1000000 ) )"
    ),
}

TELEGRAM_MSG_LIMIT = 3500


def get_csrf_and_session():
    session = requests.Session()
    resp = session.get(
        "https://chartink.com/screener/",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    soup = BeautifulSoup(resp.content, "html.parser")
    token = soup.find("meta", {"name": "csrf-token"})["content"]
    return session, token


def run_scan(session, csrf_token, scan_clause):
    url = "https://chartink.com/screener/process"
    headers = {
        "Referer": "https://chartink.com/screener/",
        "x-csrf-token": csrf_token,
        "User-Agent": "Mozilla/5.0",
    }
    payload = {"scan_clause": scan_clause}
    resp = session.post(url, headers=headers, data=payload, timeout=20)
    resp.raise_for_status()
    return resp.json().get("data", [])


def send_telegram_alert(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    r = requests.post(url, data=payload, timeout=10)
    return r.ok


def send_alerts_batched(lines):
    header = f"📊 *Chartink Scan Alerts* — {datetime.now(IST).strftime('%d-%b-%Y %H:%M')} IST\n\n"
    chunk = header
    for line in lines:
        if len(chunk) + len(line) > TELEGRAM_MSG_LIMIT:
            send_telegram_alert(chunk)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        send_telegram_alert(chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", action="store_true", help="Save raw scan results to JSON file")
    args = parser.parse_args()

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing")
        return

    session, csrf = get_csrf_and_session()

    all_lines = []
    all_results = {}
    for scan_name, clause in SCAN_CLAUSES.items():
        try:
            results = run_scan(session, csrf, clause)
            if results:
                all_lines.append(f"*{scan_name}* — {len(results)} match")
                all_results[scan_name] = results
                for stock in results:
                    sym = stock.get("nsecode", "?")
                    price = stock.get("close", "?")
                    pct = stock.get("per_chg", "?")
                    all_lines.append(f"  • {sym} — ₹{price} ({pct}%)")
        except Exception as e:
            print(f"Scan '{scan_name}' fail hua: {e}")

    # Save raw results for external analysis
    if args.output_json:
        with open("raw_scan_results.json", "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"Saved scan results to raw_scan_results.json")

    if all_lines:
        send_alerts_batched(all_lines)
        print("Alert bhej diya")
    else:
        print("Is run mein koi match nahi mila")


if __name__ == "__main__":
    main()
    
