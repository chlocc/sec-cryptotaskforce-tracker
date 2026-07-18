"""One-time (re-runnable) enrichment pass: adds a one-line takeaway and
1-3 topic tags (from the frozen taxonomy in taxonomy.py) to every item, and
further condenses the written-input bullets, which start as the SEC's own
(sometimes lengthy) key points.

Uses claude-opus-4-6 with adaptive thinking for the categorization judgment
call; concurrent with modest parallelism and per-item retry. Safe to re-run —
it overwrites topics/takeaway/key_points (written-input only) each time, and
saves incrementally so a partial run isn't lost.
"""

import argparse
import concurrent.futures
import json
import logging
import threading
import time
from pathlib import Path

import anthropic

from taxonomy import TOPICS

ROOT = Path(__file__).parent
ITEMS_PATH = ROOT / "data" / "items.json"
MODEL = "claude-opus-4-6"
CONCURRENCY = 4

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("enrich")

SYSTEM = (
    "You categorize and summarize SEC Crypto Task Force materials for a crypto-regulatory "
    "professional's tracker. You are precise, neutral, and never invent facts not supported "
    "by the source text."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "takeaway": {
            "type": "string",
            "description": "One sentence, 25 words or fewer: the single most important "
                            "thing a reader should know about this item.",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string", "enum": TOPICS},
            "description": "1 to 3 tags, most relevant first.",
        },
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-3 tightened bullets, each 25 words or fewer. Only re-write "
                            "these if instructed to condense; otherwise return the input "
                            "bullets unchanged.",
        },
    },
    "required": ["takeaway", "topics", "key_points"],
    "additionalProperties": False,
}

_client = None
_lock = threading.Lock()


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _prompt(item: dict) -> str:
    condense = item["source"] == "written-input"
    bullets = "\n".join(f"- {p}" for p in item["key_points"])
    instruction = (
        "Further condense these into 2-3 tighter bullets (they are already a summary; "
        "compress harder, keep only the load-bearing points)."
        if condense else
        "Return these key_points exactly as given, unchanged."
    )
    return (
        f"Source: {item['source']}\n"
        f"Title: {item['title']}\n"
        f"Author/Party: {item['author']}\n"
        f"Date: {item['date']}\n\n"
        f"Current key points:\n{bullets}\n\n"
        f"Available topic tags (choose 1-3, only from this list): {', '.join(TOPICS)}\n\n"
        f"{instruction}\n"
        "Also write a one-line takeaway."
    )


def _apply(item: dict, data: dict) -> None:
    item["takeaway"] = data["takeaway"].strip()
    # Anthropic's json_schema enum guarantees topics ⊆ TOPICS; OpenRouter's
    # free models have no such enforcement, so filter defensively either way.
    topics = [t for t in data["topics"] if t in TOPICS][:3]
    if not topics:
        log.warning("no valid topics for %s (got %r)", item["title"][:60], data["topics"])
    item["topics"] = topics
    if item["source"] == "written-input" and data.get("key_points"):
        item["key_points"] = [p.strip() for p in data["key_points"] if p.strip()]


def _enrich_openrouter(item: dict) -> dict | None:
    import openrouter

    schema_hint = (
        '{"takeaway": "one sentence, <=25 words", '
        f'"topics": ["1 to 3 tags from: {", ".join(TOPICS)}"], '
        '"key_points": ["bullet 1", "bullet 2", ...]}'
    )
    try:
        return openrouter.complete_json(SYSTEM, _prompt(item), schema_hint)
    except Exception as e:
        log.error("OpenRouter fallback also failed for %s: %s", item["title"][:60], e)
        return None


def enrich_one(item: dict, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            resp = client().messages.create(
                model=MODEL,
                max_tokens=2000,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": SCHEMA},
                },
                system=SYSTEM,
                messages=[{"role": "user", "content": _prompt(item)}],
            )
            if resp.stop_reason == "refusal":
                log.warning("refused: %s", item["title"][:60])
                return item
            body = next(b.text for b in resp.content if b.type == "text")
            _apply(item, json.loads(body))
            item["enriched_by"] = "claude"
            return item
        except anthropic.APIStatusError as e:
            log.warning("Anthropic enrichment failed for %s (%s) — falling back to OpenRouter",
                        item["title"][:60], e)
            data = _enrich_openrouter(item)
            if data:
                _apply(item, data)
                item["enriched_by"] = "openrouter"
            return item
        except Exception as e:
            if attempt == retries - 1:
                log.error("giving up on %s: %s", item["title"][:60], e)
                return item
            time.sleep(2 ** attempt)
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only enrich the first N items (for testing)")
    parser.add_argument("--force", action="store_true", help="re-enrich items that already have a takeaway")
    args = parser.parse_args()

    items = json.loads(ITEMS_PATH.read_text())
    by_id = {it["id"]: it for it in items}

    todo = [it for it in items if args.force or not it.get("takeaway")]
    if args.limit:
        todo = todo[:args.limit]
    log.info("enriching %d/%d items (model=%s, concurrency=%d)", len(todo), len(items), MODEL, CONCURRENCY)

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(enrich_one, it): it["id"] for it in todo}
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            by_id[result["id"]] = result
            done += 1
            if done % 10 == 0 or done == len(todo):
                log.info("progress: %d/%d — saving", done, len(todo))
                ITEMS_PATH.write_text(json.dumps(list(by_id.values()), indent=1, ensure_ascii=False))

    ITEMS_PATH.write_text(json.dumps(list(by_id.values()), indent=1, ensure_ascii=False))
    log.info("done")


if __name__ == "__main__":
    main()
