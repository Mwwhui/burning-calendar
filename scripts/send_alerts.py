"""Send the newest fire alerts to Telegram (optional; run by scripts/update_daily.py).

Does nothing unless these are set in .env (never commit them):

    TELEGRAM_BOT_TOKEN   token of a bot made with @BotFather
    TELEGRAM_CHAT_ID     the chat or channel that receives the alerts
    ALERT_AREAS          optional, comma-separated area ids to follow (e.g. "mys,idn/riau");
                         empty = warnings anywhere

Each data update is sent once (its `generated` stamp is remembered in
data/processed/alerts_sent.json).

    python scripts/send_alerts.py            # send if configured
    python scripts/send_alerts.py --dry-run  # print the message instead
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERTS = ROOT / "web" / "public" / "data" / "alerts.json"
SENT = ROOT / "data" / "processed" / "alerts_sent.json"
SITE = os.environ.get("SITE_URL", "http://localhost:3000")


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def select(alerts: list[dict], areas: list[str]) -> list[dict]:
    if not areas:
        return [a for a in alerts if a["level"] == "warning"]
    return [a for a in alerts if any(w == "" or a["areaId"] == w or a["areaId"].startswith(w + "/") for w in areas)]


def message(data: dict, chosen: list[dict], max_items: int = 15) -> str:
    lines = [f"Burning Calendar alerts, data to {data.get('lastDay')}: {len(chosen)}"]
    for a in chosen[:max_items]:
        mark = "WARNING" if a["level"] == "warning" else "watch"
        lines.append(f"\n[{mark}] {a['name']}: {a['title']}\n{a['detail']}\n{SITE}/{a['areaId']}/" if a["areaId"]
                     else f"\n[{mark}] {a['name']}: {a['title']}\n{a['detail']}")
    if len(chosen) > max_items:
        lines.append(f"\n…and {len(chosen) - max_items} more in the app.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    load_env()
    if not ALERTS.exists():
        print("no alerts.json yet")
        return 0
    data = json.loads(ALERTS.read_text(encoding="utf-8"))
    areas = [x.strip() for x in os.environ.get("ALERT_AREAS", "").split(",") if x.strip()]
    chosen = select(data.get("alerts", []), areas)
    text = message(data, chosen)
    if args.dry_run:
        print(text)
        return 0
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env): nothing sent")
        return 0
    sent = json.loads(SENT.read_text(encoding="utf-8")) if SENT.exists() else {}
    if sent.get("generated") == data.get("generated"):
        print("alerts of this update were already sent")
        return 0
    if not chosen:
        print("no alerts to send")
        return 0
    import requests

    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"}, timeout=30)
    if not r.ok:
        print(f"Telegram error {r.status_code}: {r.text[:200]}")
        return 1
    SENT.write_text(json.dumps({"generated": data.get("generated")}), encoding="utf-8")
    print(f"sent {len(chosen)} alerts to Telegram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
