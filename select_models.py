import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
CATALOG_PATH = ROOT / "product_catalog.json"
WATCHLIST_PATH = ROOT / "watchlist.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_targets(values, devices):
    selected = []
    for value in values:
        for token in value.split(","):
            token = token.strip()
            if not token:
                continue
            if token.lower() == "all":
                selected.extend(devices)
            elif token.isdigit() and 1 <= int(token) <= len(devices):
                selected.append(devices[int(token) - 1])
            elif token in devices:
                selected.append(token)
            else:
                raise ValueError(f"Unknown model number or SKU: {token}")
    return list(dict.fromkeys(selected))


def print_models(devices, catalog, selected):
    for index, sku in enumerate(devices, start=1):
        marker = "[x]" if sku in selected else "[ ]"
        label = str(catalog.get(sku, sku)).replace("\u00a0", " ")
        print(f"{index:>2}. {marker} {label} ({sku})")


def main():
    parser = argparse.ArgumentParser(
        description="List or select Apple TRX models to monitor"
    )
    parser.add_argument(
        "--set",
        nargs="+",
        metavar="NUMBER_OR_SKU",
        help="replace the watchlist, for example: --set 30 32",
    )
    parser.add_argument(
        "--clear", action="store_true", help="clear the watchlist"
    )
    args = parser.parse_args()

    config = load_json(CONFIG_PATH, {})
    catalog = load_json(CATALOG_PATH, {})
    devices = list(dict.fromkeys(config.get("devices", [])))
    selected = set(load_json(WATCHLIST_PATH, []))

    if args.clear:
        selected = set()
        save_json(WATCHLIST_PATH, [])
        print("Watchlist cleared")
    elif args.set is not None:
        selected = set(resolve_targets(args.set, devices))
        ordered = [sku for sku in devices if sku in selected]
        save_json(WATCHLIST_PATH, ordered)
        print(f"Selected {len(ordered)} model(s)")

    print_models(devices, catalog, selected)


if __name__ == "__main__":
    main()
