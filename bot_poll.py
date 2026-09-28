import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
WATCHLIST_PATH = ROOT / "watchlist.json"
STATE_PATH = ROOT / "discord_state.json"
CATALOG_PATH = ROOT / "product_catalog.json"
STATUS_PATH = ROOT / "current_status.json"
API_ROOT = "https://discord.com/api/v10"
USER_AGENT = "AppleTRXStockMonitor/1.0"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def discord_request(token, method, path, payload=None, query=None):
    url = f"{API_ROOT}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    body = None
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=25) as response:
        raw = response.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


def message_id(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def send_message(token, channel_id, content):
    if len(content) > 1900:
        content = content[:1890] + "…"
    return discord_request(
        token,
        "POST",
        f"/channels/{channel_id}/messages",
        {"content": content},
    )


def split_messages(lines):
    chunks = []
    current = ""
    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) > 1900:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def product_label(sku, catalog):
    return catalog.get(sku, sku).replace("\u00a0", " ")


def render_list(devices, watched, catalog):
    lines = ["**Apple TRX 监测型号**", "发送 `!watch 编号` 选择，发送 `!mute 编号` 静音。"]
    for index, sku in enumerate(devices, start=1):
        marker = "✅" if sku in watched else "▫️"
        lines.append(f"{index}. {marker} {product_label(sku, catalog)} — `{sku}`")
    return split_messages(lines)


def parse_targets(tokens, devices):
    targets = []
    for token in tokens:
        for part in token.split(","):
            part = part.strip()
            if not part:
                continue
            if part.lower() == "all":
                targets.extend(devices)
                continue
            if part.isdigit():
                index = int(part)
                if 1 <= index <= len(devices):
                    targets.append(devices[index - 1])
                continue
            if part in devices:
                targets.append(part)
    return list(dict.fromkeys(targets))


def help_messages():
    return [
        "**Apple TRX 监测指令**",
        "`!list` 查看全部型号和当前选择",
        "`!status` 查看全部型号当前库存（不提醒）",
        "`!watch 1 3` 选择第 1、3 个型号",
        "`!mute 1 3` 静音第 1、3 个型号",
        "`!selected` 查看正在监测的型号",
        "`!clear` 清空选择，全部免打扰",
        "`!help` 查看帮助",
    ]


def main():
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        print("Discord bot secrets are not configured; command polling skipped")
        return

    config = load_json(CONFIG_PATH, {})
    devices = list(dict.fromkeys(config.get("devices", [])))
    watched = set(load_json(WATCHLIST_PATH, []))
    watched.intersection_update(devices)
    state = load_json(STATE_PATH, {"last_message_id": ""})
    catalog = load_json(CATALOG_PATH, {})
    statuses = load_json(STATUS_PATH, {})
    last_id = str(state.get("last_message_id", ""))
    query = {"limit": "100"}
    if last_id:
        query["after"] = last_id
    messages = discord_request(
        token,
        "GET",
        f"/channels/{channel_id}/messages",
        query=query,
    ) or []

    if not last_id:
        latest = max((message_id(item.get("id")) for item in messages), default=0)
        created = send_message(
            token,
            channel_id,
            "✅ Apple TRX Bot 已连接。发送 `!help` 查看指令，发送 `!list` 选择要监测的型号。",
        )
        created_id = message_id((created or {}).get("id"))
        state["last_message_id"] = str(created_id or latest) if (created_id or latest) else ""
        save_json(STATE_PATH, state)
        print("Discord bot initialized; send commands after this run")
        return

    for item in sorted(messages, key=lambda value: message_id(value.get("id"))):
        author = item.get("author", {})
        if author.get("bot"):
            continue
        content = str(item.get("content", "")).strip()
        if not content.startswith("!"):
            continue
        parts = content.split()
        command = parts[0].lower()
        targets = parse_targets(parts[1:], devices)

        if command == "!help":
            for response in help_messages():
                send_message(token, channel_id, response)
        elif command == "!list":
            for response in render_list(devices, watched, catalog):
                send_message(token, channel_id, response)
        elif command == "!status":
            if not statuses:
                send_message(token, channel_id, "还没有库存检查记录，请等待下一次 Actions 运行。")
            else:
                status_lines = ["**Apple TRX 全量库存（仅查询，不提醒）**"]
                for index, sku in enumerate(devices, start=1):
                    item = statuses.get(sku, {})
                    marker = "🟢 有货" if item.get("available") else "⚪ 无货"
                    title = item.get("title", product_label(sku, catalog))
                    status_lines.append(f"{index}. {marker} {title} — `{sku}`")
                for response in split_messages(status_lines):
                    send_message(token, channel_id, response)
        elif command == "!selected":
            selected = [
                f"{index}. {product_label(sku, catalog)} — `{sku}`"
                for index, sku in enumerate(devices, start=1)
                if sku in watched
            ]
            if selected:
                for response in split_messages(["**当前监测中**"] + selected):
                    send_message(token, channel_id, response)
            else:
                send_message(token, channel_id, "当前没有选择型号，全部免打扰。发送 `!list` 开始选择。")
        elif command == "!watch":
            if not targets:
                send_message(token, channel_id, "用法：`!watch 1 3`，编号可以从 `!list` 查看。")
            else:
                watched.update(targets)
                names = ", ".join(product_label(sku, catalog) for sku in targets)
                send_message(token, channel_id, f"✅ 已加入监测：{names}")
        elif command == "!mute":
            if not targets:
                send_message(token, channel_id, "用法：`!mute 1 3`，或发送 `!clear` 全部静音。")
            else:
                watched.difference_update(targets)
                names = ", ".join(product_label(sku, catalog) for sku in targets)
                send_message(token, channel_id, f"🔕 已静音：{names}")
        elif command == "!clear":
            watched.clear()
            send_message(token, channel_id, "🔕 已清空选择，全部型号免打扰。")
        else:
            send_message(token, channel_id, "不认识这个指令，发送 `!help` 查看可用指令。")

    latest = max(
        [message_id(item.get("id")) for item in messages] + [message_id(last_id)]
    )
    state["last_message_id"] = str(latest) if latest else last_id
    save_json(STATE_PATH, state)
    save_json(WATCHLIST_PATH, [sku for sku in devices if sku in watched])
    print(f"Discord commands processed: {len(messages)} message(s); selected={len(watched)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr)
        sys.exit(1)
