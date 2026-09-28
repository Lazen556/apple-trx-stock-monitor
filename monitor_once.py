import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "stock_state.json"
WATCHLIST_PATH = ROOT / "watchlist.json"
ALERT_STATE_PATH = ROOT / "alert_state.json"
CATALOG_PATH = ROOT / "product_catalog.json"
STATUS_PATH = ROOT / "current_status.json"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleTRXStockMonitor/1.0"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def request_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.apple.com/my/shop/buy-iphone/iphone-18-pro",
        },
    )
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def find_store(payload, store_number, store_name):
    stores = payload.get("body", {}).get("stores", [])
    for store in stores:
        if str(store.get("storeNumber", "")) == str(store_number):
            return store
        if store_name.lower() in str(store.get("storeName", "")).lower():
            return store
    return None


def get_product_status(store, sku):
    availability = store.get("partsAvailability", {}).get(sku, {})
    title = availability.get("messageTypes", {}).get("regular", {}).get(
        "storePickupProductTitle", sku
    )
    quote = availability.get("pickupSearchQuote", "")
    display = str(availability.get("pickupDisplay", "")).lower()
    # storePickEligible can remain true while the pickup quote still says unavailable.
    available = display == "available"
    return {
        "sku": sku,
        "title": title,
        "quote": quote,
        "available": available,
    }


def send_discord(webhook_url, message):
    body = json.dumps(
        {"content": message, "username": "Apple TRX Stock Monitor"}
    ).encode("utf-8")
    request = Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Discord returned HTTP {response.status}")


def main():
    config = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {})
    watchlist = set(load_json(WATCHLIST_PATH, []))
    alert_state = load_json(ALERT_STATE_PATH, {})
    catalog = load_json(CATALOG_PATH, {})
    current_status = load_json(STATUS_PATH, {})
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    country = config.get("country", "MY")
    location = config["location"]
    store_number = config["store_number"]
    store_name = config.get("store_name", "")
    devices = list(dict.fromkeys(config.get("devices", [])))
    if not devices:
        raise RuntimeError("config.json has no devices")

    next_state = dict(state)
    next_alert_state = dict(alert_state)
    next_catalog = dict(catalog)
    next_status = dict(current_status)
    errors = 0
    newly_available = []

    for index, sku in enumerate(devices, start=1):
        url = (
            f"https://www.apple.com/{country.lower()}/shop/retail/pickup-message"
            f"?pl=true&parts.0={quote(sku, safe='')}&location={quote(location, safe='')}"
        )
        key = f"{store_number}|{sku}"
        try:
            payload = request_json(url)
            store = find_store(payload, store_number, store_name)
            if store is None:
                raise RuntimeError(f"store {store_number}/{store_name} not found")
            result = get_product_status(store, sku)
            available = result["available"]
            next_state[key] = available
            next_catalog[sku] = result["title"]
            next_status[sku] = {
                "title": result["title"],
                "available": available,
                "quote": result["quote"],
            }
            status = "AVAILABLE" if available else "unavailable"
            print(
                f"[{index}/{len(devices)}] {result['title']} ({sku}) -> {status}; {result['quote']}"
            )
            if not available or sku not in watchlist:
                next_alert_state[key] = False
            elif not bool(alert_state.get(key, False)):
                newly_available.append(result)
                next_alert_state[key] = True
        except Exception as error:
            errors += 1
            print(f"[{index}/{len(devices)}] {sku} -> ERROR: {error}")
        if index < len(devices):
            time.sleep(1.5)

    if newly_available:
        if not webhook_url:
            raise RuntimeError(
                "Missing DISCORD_WEBHOOK_URL. Add it under GitHub Settings > Secrets and variables > Actions."
            )
        lines = [
            "🚨 Apple Malaysia The Exchange TRX 有货",
            "https://www.apple.com/my/shop/buy-iphone/iphone-18-pro",
        ]
        for item in newly_available:
            lines.append(f"• {item['title']} ({item['sku']})")
        send_discord(webhook_url, "\n".join(lines))
        print(f"Discord notification sent for {len(newly_available)} item(s)")
    else:
        print("No new availability transition")

    with STATE_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(next_state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    with ALERT_STATE_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(next_alert_state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    with CATALOG_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(next_catalog, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    with STATUS_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(next_status, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    if errors == len(devices):
        raise RuntimeError("All inventory requests failed")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr)
        sys.exit(1)
