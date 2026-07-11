"""Shared record helpers for all scrapers."""

import hashlib
from datetime import date

CUTOFF = date(2026, 1, 1)
SEC = "https://www.sec.gov"


def make_id(source: str, url: str, title: str = "") -> str:
    return hashlib.sha1(f"{source}|{url}|{title}".encode()).hexdigest()[:16]


def absolute(href: str) -> str:
    if href.startswith("http"):
        return href
    return SEC + href


def record(*, source, date_iso, title, url, author="", topics=None,
           key_points=None, thin=False, date_approximate=False,
           summarized_by="", doc_url=""):
    return {
        "id": make_id(source, url, title),
        "source": source,
        "date": date_iso,
        "title": title,
        "author": author,
        "topics": topics or [],  # overwritten by enrich.py with the frozen taxonomy
        "takeaway": "",  # filled in by enrich.py
        "url": url,
        "doc_url": doc_url,
        "key_points": key_points or [],
        "thin": thin,
        "date_approximate": date_approximate,
        "summarized_by": summarized_by,
    }
