#!/usr/bin/env python3
"""SEC Crypto Task Force Tracker — daily pipeline.

Scrape the four SEC pages, summarize anything new (items dated 2026-01-01 or
later), regenerate docs/data.json, and — when run inside a git repo — commit
and push. Idempotent: already-seen items are skipped.

Usage:
    python3 run_daily.py             # daily incremental run
    python3 run_daily.py --backfill  # same logic; kept as an explicit alias
    python3 run_daily.py --no-git    # skip the commit/push step
"""

import argparse
import concurrent.futures
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tracker")


def load_env():
    """Load ANTHROPIC_API_KEY from ./.env if not already in the environment."""
    import os
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def summarize_pending(items: list[dict]) -> None:
    """Fill in key points for meeting memos and newsroom pages."""
    import summarize
    from scraper import meetings, newsroom

    pending = [it for it in items if it["summarized_by"] == "pending"]
    for i, it in enumerate(pending, 1):
        log.info("summarizing %d/%d: [%s] %s", i, len(pending), it["source"], it["title"][:70])
        try:
            if it["source"] == "meetings":
                text = meetings.memo_text(it["doc_url"])
                kind, meta = "Crypto Task Force meeting memorandum", f"Date: {it['date']}\nParticipants: {it['author']}"
            else:
                text = newsroom.page_text(it["doc_url"])
                kind, meta = "SEC crypto newsroom item (speech/statement/announcement)", f"Date: {it['date']}\nSpeaker: {it['author']}"
            if len(text) < 200:
                raise ValueError(f"too little text ({len(text)} chars)")
            points = summarize.gist(kind, it["title"], meta, text)
            if points:
                it["key_points"] = points
                it["summarized_by"] = "claude"
            else:
                raise ValueError("empty summary")
        except Exception as e:
            log.warning("could not summarize %s (%s)", it["url"], e)
            it["thin"] = True
            it["summarized_by"] = "none"
            it["key_points"] = it["key_points"] or [
                "Summary unavailable — see the source document on sec.gov."
            ]


def condense_long_sec_summaries(items: list[dict]) -> None:
    """Condense SEC-provided text that is too long to scan."""
    import summarize

    targets = [it for it in items
               if it["summarized_by"] == "sec" and summarize.needs_condensing(it["key_points"])]
    for i, it in enumerate(targets, 1):
        log.info("condensing %d/%d: [%s] %s", i, len(targets), it["source"], it["title"][:70])
        try:
            kind = ("public written input to the SEC Crypto Task Force"
                    if it["source"] == "written-input" else "SEC staff statement / order summary")
            meta = f"Date: {it['date']}\nFrom: {it['author']}"
            text = "SEC-provided key points/summary:\n- " + "\n- ".join(it["key_points"])
            points = summarize.gist(kind, it["title"], meta, text)
            if points:
                it["key_points"] = points
                it["summarized_by"] = "claude"
        except Exception as e:
            log.warning("could not condense %s (%s) — keeping SEC text", it["url"], e)


def enrich_new_items(items: list[dict]) -> None:
    """Takeaway + topic tags (+ tighter written-input bullets) for newly added items."""
    if not items:
        return
    import enrich

    log.info("enriching %d new items with %s", len(items), enrich.MODEL)
    with concurrent.futures.ThreadPoolExecutor(max_workers=enrich.CONCURRENCY) as pool:
        list(pool.map(enrich.enrich_one, items))  # enrich_one mutates in place


def git_publish() -> None:
    if not (ROOT / ".git").exists():
        log.info("not a git repo — skipping commit/push")
        return
    subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=True)
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        log.info("no changes to commit")
        return
    msg = f"Update tracker data {datetime.now(timezone.utc).date().isoformat()}"
    subprocess.run(["git", "-C", str(ROOT), "commit", "-m", msg], check=True)
    push = subprocess.run(["git", "-C", str(ROOT), "push"])
    if push.returncode != 0:
        log.warning("git push failed — commit is local only")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true",
                        help="explicit alias; the pipeline always processes unseen items since 2026-01-01")
    parser.add_argument("--no-git", action="store_true", help="skip git commit/push")
    args = parser.parse_args()

    load_env()

    import generate_site
    from scraper import cryptosec, meetings, newsroom, written_input

    existing = generate_site.load_items()
    seen = {it["id"] for it in existing}
    by_id = {it["id"]: it for it in existing}

    status_file = ROOT / "data" / "source_status.json"
    source_status = json.loads(status_file.read_text()) if status_file.exists() else {}

    new_items, added_per_source = [], {}
    for name, scraper in [("written-input", written_input),
                          ("cryptosec", cryptosec),
                          ("meetings", meetings),
                          ("newsroom", newsroom)]:
        try:
            scraped = scraper.scrape()
            if not scraped:
                # A previously non-empty source returning nothing means layout
                # drift or an outage — keep prior data, don't publish an empty feed.
                if any(it["source"] == name for it in existing):
                    log.warning("%s returned 0 rows — keeping prior data", name)
                    continue
            source_status[name] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            fresh = [it for it in scraped if it["id"] not in seen]
            # Refresh SEC-provided key points on already-seen items (SEC sometimes edits)
            for it in scraped:
                if it["id"] in seen and it["summarized_by"] == "sec":
                    prev = by_id[it["id"]]
                    if prev["summarized_by"] == "sec":
                        prev["key_points"] = it["key_points"]
            new_items.extend(fresh)
            added_per_source[name] = len(fresh)
        except Exception as e:
            log.error("scrape failed for %s: %s — keeping prior data", name, e)

    log.info("new items: %s", added_per_source or "none")

    summarize_pending(new_items)
    condense_long_sec_summaries(new_items)
    enrich_new_items(new_items)

    all_items = existing + new_items
    generate_site.save_items(all_items)
    status_file.parent.mkdir(exist_ok=True)
    status_file.write_text(json.dumps(source_status, indent=1))
    generate_site.generate(all_items, source_status)

    if not args.no_git:
        git_publish()

    total_new = sum(added_per_source.values())
    thin = sum(1 for it in new_items if it.get("thin"))
    log.info("done: %d new items (%d thin), %d total", total_new, thin, len(all_items))


if __name__ == "__main__":
    main()
