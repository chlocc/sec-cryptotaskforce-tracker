"""Scraper for the Crypto Task Force newsroom page.

Paginated table sorted newest-first: Date ("Jun 02, 2026") | Title (linked
speech/statement page) | Speaker. No summary on the listing page, so the
pipeline fetches each linked page and summarizes its main text.
"""

import logging
from datetime import date, datetime

from bs4 import BeautifulSoup

from . import fetch
from .common import CUTOFF, absolute, record

log = logging.getLogger("tracker.newsroom")

BASE = "https://www.sec.gov/about/crypto-task-force/crypto-newsroom"
MAX_PAGES = 20


def _parse_date(text: str) -> date | None:
    text = text.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


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
            if len(cells) < 3:
                continue
            d = _parse_date(cells[0].get_text(strip=True))
            if d is None:
                continue
            if d < CUTOFF:
                hit_cutoff = True
                continue
            link = cells[1].find("a")
            if not link:
                continue
            items.append(record(
                source="newsroom",
                date_iso=d.isoformat(),
                title=link.get_text(" ", strip=True),
                author=cells[2].get_text(" ", strip=True),
                url=absolute(link["href"]),
                doc_url=absolute(link["href"]),
                summarized_by="pending",  # linked page summarized in the pipeline
            ))
        if hit_cutoff:
            break
    log.info("newsroom: %d items since %s", len(items), CUTOFF)
    return items


def page_text(url: str, max_chars: int = 20000) -> str:
    """Fetch a newsroom speech/statement page and extract its main text."""
    resp = fetch.get(url)
    if url.lower().endswith(".pdf") or resp.headers.get("Content-Type", "").startswith("application/pdf"):
        import fitz
        with fitz.open(stream=resp.content, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)[:max_chars].strip()
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main") or soup.body or soup
    for tag in main.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()
    return main.get_text("\n", strip=True)[:max_chars]
