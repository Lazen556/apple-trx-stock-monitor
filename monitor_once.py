import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "stock_state.json"
WATCHLIST_PATH = ROOT / "watchlist.json"
ALERT_STATE_PATH = ROOT / "alert_state.json"
CATALOG_PATH = ROOT / "product_catalog.json"
STATUS_PATH = ROOT / "current_status.json"
REPORT_STATE_PATH = ROOT / "report_state.json"
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


def send_wecom(webhook_url, message):
    body = json.dumps(
        {"msgtype": "markdown", "markdown": {"content": message}},
        ensure_ascii=False,
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
        result = json.loads(response.read().decode("utf-8"))
    if int(result.get("errcode", -1)) != 0:
        raise RuntimeError(f"WeCom returned: {result}")


def send_notification(discord_url, wecom_url, message):
    sent_to = []
    if discord_url:
        send_discord(discord_url, message)
        sent_to.append("Discord")
    if wecom_url:
        send_wecom(wecom_url, message)
        sent_to.append("WeCom")
    if not sent_to:
        raise RuntimeError(
            "Missing notification webhook. Configure DISCORD_WEBHOOK_URL or WECOM_WEBHOOK_URL."
        )
    print(f"Notification sent to {', '.join(sent_to)}")


def build_selected_report(selected_skus, cycle_results, store_name):
    checked_count = sum(1 for sku in selected_skus if sku in cycle_results)
    available_count = sum(
        1 for sku in selected_skus if cycle_results.get(sku, {}).get("available")
    )
    failed_count = len(selected_skus) - checked_count
    if checked_count == 0:
        first_line = f"❓ 查询失败｜0/{len(selected_skus)} 个已选型号取得结果"
    elif available_count:
        first_line = f"🟢 有货｜{available_count}/{len(selected_skus)} 个已选型号"
    else:
        first_line = f"⚪ 无货｜0/{len(selected_skus)} 个已选型号"
    if failed_count and checked_count:
        first_line += f"｜{failed_count} 个查询失败"

    checked_at = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime(
        "%Y-%m-%d %H:%M MYT"
    )
    lines = [
        first_line,
        f"Apple Malaysia · {store_name}",
        f"更新时间：{checked_at}",
        "",
        "详细信息：",
    ]
    for index, sku in enumerate(selected_skus, start=1):
        item = cycle_results.get(sku)
        if item is None:
            lines.append(f"{index}. ❓ 查询失败｜{sku}")
            continue
        marker = "🟢 有货" if item["available"] else "⚪ 无货"
        quote_text = item.get("quote") or "Apple 未提供提货说明"
        lines.append(f"{index}. {marker}｜{item['title']}")
        lines.append(f"   SKU：{sku}｜提货：{quote_text}")
    lines.extend(
        [
            "",
            "购买页面：https://www.apple.com/my/shop/buy-iphone/iphone-18-pro",
        ]
    )
    return "\n".join(lines)


def main():
    config = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {})
    watchlist = set(load_json(WATCHLIST_PATH, []))
    alert_state = load_json(ALERT_STATE_PATH, {})
    catalog = load_json(CATALOG_PATH, {})
    current_status = load_json(STATUS_PATH, {})
    report_state = load_json(
        REPORT_STATE_PATH, {"last_report_at": 0, "watchlist_signature": ""}
    )
    discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    wecom_webhook_url = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
    report_interval_minutes = max(
        1, int(os.environ.get("REPORT_INTERVAL_MINUTES", "30"))
    )

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
    cycle_results = {}
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
            cycle_results[sku] = result
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

    selected_skus = [sku for sku in devices if sku in watchlist]
    watchlist_signature = ",".join(selected_skus)
    now = int(time.time())
    last_report_at = int(report_state.get("last_report_at", 0) or 0)
    report_due = bool(selected_skus) and (
        watchlist_signature != str(report_state.get("watchlist_signature", ""))
        or now - last_report_at >= report_interval_minutes * 60
    )

    if report_due:
        message = build_selected_report(selected_skus, cycle_results, store_name)
        send_notification(discord_webhook_url, wecom_webhook_url, message)
        report_state = {
            "last_report_at": now,
            "watchlist_signature": watchlist_signature,
        }
        print(
            f"Periodic selected-model report sent for {len(selected_skus)} item(s); "
            f"interval={report_interval_minutes}m"
        )
    elif newly_available:
        lines = [
            f"🟢 有货｜{len(newly_available)} 个已选型号刚刚到货",
            f"Apple Malaysia · {store_name}",
            "",
            "详细信息：",
        ]
        for index, item in enumerate(newly_available, start=1):
            lines.append(f"{index}. 🟢 有货｜{item['title']}")
            lines.append(
                f"   SKU：{item['sku']}｜提货：{item.get('quote') or 'Apple 未提供提货说明'}"
            )
        lines.extend(
            [
                "",
                "购买页面：https://www.apple.com/my/shop/buy-iphone/iphone-18-pro",
            ]
        )
        send_notification(
            discord_webhook_url, wecom_webhook_url, "\n".join(lines)
        )
        print(f"Immediate availability alert sent for {len(newly_available)} item(s)")
    else:
        print("No notification due this run")

    if not selected_skus:
        report_state = {"last_report_at": 0, "watchlist_signature": ""}

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

    with REPORT_STATE_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report_state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    if errors == len(devices):
        raise RuntimeError("All inventory requests failed")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr)
        sys.exit(1)
