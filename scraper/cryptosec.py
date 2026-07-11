"""Scraper for the Crypto@SEC staff statements page.

Single (non-paginated) table with columns:
Date (M/D/YY) | Speaker/Division | Statement (linked) | Summary.
The SEC-provided summary is carried through as the raw text; the pipeline
condenses long ones into bullets.
"""

import logging
from datetime import date, datetime

from bs4 import BeautifulSoup

from . import fetch
from .common import CUTOFF, absolute, record

log = logging.getLogger("tracker.cryptosec")

URL = "https://www.sec.gov/featured-topics/crypto-task-force/cryptosec"


def _parse_date(text: str) -> date | None:
    text = text.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def scrape() -> list[dict]:
    resp = fetch.get(URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    items = []
    for row in (table.find_all("tr") if table else []):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        d = _parse_date(cells[0].get_text(strip=True))
        if d is None or d < CUTOFF:
            continue
        link = cells[2].find("a")
        if not link:
            continue
        summary = cells[3].get_text(" ", strip=True)
        items.append(record(
            source="cryptosec",
            date_iso=d.isoformat(),
            title=link.get_text(" ", strip=True),
            author=cells[1].get_text(" ", strip=True),
            url=absolute(link["href"]),
            doc_url=absolute(link["href"]),
            key_points=[summary] if summary else [],
            summarized_by="sec",
        ))
    log.info("cryptosec: %d items since %s", len(items), CUTOFF)
    return items
