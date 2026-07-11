"""Write docs/data.json from the item store."""

import json
from datetime import datetime, timezone
from pathlib import Path

from taxonomy import TOPICS

ROOT = Path(__file__).parent
ITEMS = ROOT / "data" / "items.json"
OUT = ROOT / "docs" / "data.json"

SOURCE_LABELS = {
    "written-input": "Written Input",
    "cryptosec": "Staff Statements",
    "meetings": "Meetings",
    "newsroom": "Newsroom",
}


def load_items() -> list[dict]:
    if ITEMS.exists():
        return json.loads(ITEMS.read_text())
    return []


def save_items(items: list[dict]) -> None:
    ITEMS.parent.mkdir(exist_ok=True)
    ITEMS.write_text(json.dumps(items, indent=1, ensure_ascii=False))


def generate(items: list[dict], source_status: dict[str, str]) -> None:
    items = sorted(items, key=lambda x: (x["date"], x["id"]), reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_labels": SOURCE_LABELS,
        "source_status": source_status,  # source -> last successful scrape (ISO)
        "topics": TOPICS,
        "items": items,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"docs/data.json: {len(items)} items")
