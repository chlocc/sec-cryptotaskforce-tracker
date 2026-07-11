"""Scraper for the Crypto Task Force meetings page.

Paginated table sorted newest-first: Date | Participants & Associated Materials
(a link to a short meeting memo PDF). The page itself carries no summary, so
the pipeline downloads each memo PDF and summarizes it.
"""

import logging
from datetime import date, datetime

from bs4 import BeautifulSoup

from . import fetch
from .common import CUTOFF, absolute, record

log = logging.getLogger("tracker.meetings")

BASE = "https://www.sec.gov/securities-topics/crypto-task-force/crypto-task-force-meetings"
MAX_PAGES = 40


def scrape() -> list[dict]:
    items = []
    for page in range(MAX_PAGES):
        resp = fetch.get(f"{BASE}?page={page}")
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        rows = table.find_all("tr")[1:] if table else []
        if not rows:
            break
        hit_cutoff = False
        for row in rows:
            t = row.find("time")
            if not t or not t.get("datetime"):
                continue
            d = datetime.fromisoformat(t["datetime"].replace("Z", "+00:00")).date()
            if d < CUTOFF:
                hit_cutoff = True
                continue
            link = row.find("a")
            if not link:
                continue
            participants = link.get_text(" ", strip=True)
            items.append(record(
                source="meetings",
                date_iso=d.isoformat(),
                title=f"Meeting with {participants}",
                author=participants,
                url=absolute(link["href"]),
                doc_url=absolute(link["href"]),
                summarized_by="pending",  # memo PDF summarized in the pipeline
            ))
        if hit_cutoff:
            break
    log.info("meetings: %d items since %s", len(items), CUTOFF)
    return items


def memo_text(doc_url: str, max_chars: int = 20000) -> str:
    """Download the meeting memo PDF and extract its text."""
    import fitz  # pymupdf

    resp = fetch.get(doc_url)
    with fitz.open(stream=resp.content, filetype="pdf") as doc:
        text = "\n".join(p.get_text() for p in doc)
    return text[:max_chars].strip()
