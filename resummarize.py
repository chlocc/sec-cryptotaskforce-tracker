"""One-off: re-summarize meeting/newsroom items with the current summarize.MODEL,
then clear their takeaways so a follow-up enrich.py run regenerates them from
the new bullets. Saves incrementally.

Usage: python3 resummarize.py [--limit N]
"""

import argparse
import concurrent.futures
import json
import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import run_daily  # noqa: E402

run_daily.load_env()

import summarize  # noqa: E402
from scraper import meetings, newsroom  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("resummarize")

ITEMS_PATH = ROOT / "data" / "items.json"
_lock = threading.Lock()


def redo(item: dict) -> dict:
    try:
        if item["source"] == "meetings":
            text = meetings.memo_text(item["doc_url"])
            kind, meta = "Crypto Task Force meeting memorandum", f"Date: {item['date']}\nParticipants: {item['author']}"
        else:
            text = newsroom.page_text(item["doc_url"])
            kind, meta = "SEC crypto newsroom item (speech/statement/announcement)", f"Date: {item['date']}\nSpeaker: {item['author']}"
        points = summarize.gist(kind, item["title"], meta, text)
        if points:
            item["key_points"] = points
            item["summarized_by"] = summarize.MODEL
            item["takeaway"] = ""  # regenerate via enrich.py from the new bullets
            item["thin"] = False
        log.info("done: [%s] %s", item["source"], item["title"][:60])
    except Exception as e:
        log.warning("failed (keeping old summary): %s (%s)", item["title"][:60], e)
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    items = json.loads(ITEMS_PATH.read_text())
    by_id = {it["id"]: it for it in items}
    todo = [it for it in items if it["source"] in ("meetings", "newsroom")]
    if args.limit:
        todo = todo[:args.limit]
    log.info("re-summarizing %d items with %s", len(todo), summarize.MODEL)

    done = 0
    # Low concurrency: each worker fetches from sec.gov (throttled) then calls the API
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(redo, todo):
            by_id[result["id"]] = result
            done += 1
            if done % 10 == 0 or done == len(todo):
                log.info("progress %d/%d — saving", done, len(todo))
                ITEMS_PATH.write_text(json.dumps(list(by_id.values()), indent=1, ensure_ascii=False))

    ITEMS_PATH.write_text(json.dumps(list(by_id.values()), indent=1, ensure_ascii=False))
    log.info("all done — now run: python3 enrich.py   (regenerates cleared takeaways)")


if __name__ == "__main__":
    main()
