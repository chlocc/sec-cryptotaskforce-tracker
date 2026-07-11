"""Scraper for the Crypto Task Force written input page.

The SEC page is a paginated Drupal views table sorted newest-first with
columns: Date | Written Input (author + linked letter) | Topic(s) | Key Points.
The SEC already provides bulleted key points, which we carry through.
"""

import logging
from datetime import date, datetime

from bs4 import BeautifulSoup

from . import fetch
from .common import CUTOFF, absolute, record

log = logging.getLogger("tracker.written_input")

BASE = "https://www.sec.gov/featured-topics/crypto-task-force/crypto-task-force-written-input"
MAX_PAGES = 60


def _row_date(row) -> date | None:
    t = row.find("time")
    if t and t.get("datetime"):
        return datetime.fromisoformat(t["datetime"].replace("Z", "+00:00")).date()
    return None


def _key_points(cell) -> list[str]:
    points = [li.get_text(" ", strip=True) for li in cell.find_all("li")]
    points = [p for p in points if p]
    if not points:
        text = cell.get_text(" ", strip=True)
        if text:
            points = [text]
    return points


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
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            d = _row_date(row)
            if d is None:
                continue
            if d < CUTOFF:
                hit_cutoff = True
                continue
            link = cells[1].find("a")
            if not link:
                continue
            # Author is the text in the cell before the linked letter title
            author = cells[1].get_text("|", strip=True).split("|")[0].strip()
            title = link.get_text(" ", strip=True)
            topics = [t.strip() for t in cells[2].get_text(strip=True).split(",") if t.strip()]
            items.append(record(
                source="written-input",
                date_iso=d.isoformat(),
                title=title,
                author=author,
                topics=topics,
                url=absolute(link["href"]),
                doc_url=absolute(link["href"]),
                key_points=_key_points(cells[3]),
                summarized_by="sec",
            ))
        if hit_cutoff:
            break
    log.info("written-input: %d items since %s", len(items), CUTOFF)
    return items
