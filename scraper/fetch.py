"""Shared HTTP fetching for sec.gov pages and documents."""

import logging
import time

import requests

USER_AGENT = "SEC-CTF-Tracker (+https://github.com/chlocc/sec-cryptotaskforce-tracker)"
THROTTLE_SECONDS = 0.6

log = logging.getLogger("tracker.fetch")

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
_last_request_at = 0.0


def get(url: str, *, retries: int = 3, timeout: int = 30) -> requests.Response:
    """GET with throttling (SEC fair-access) and simple retry on 5xx/network errors."""
    global _last_request_at
    for attempt in range(retries):
        wait = THROTTLE_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = _session.get(url, timeout=timeout)
            _last_request_at = time.monotonic()
            if resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} from {url}")
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            if attempt == retries - 1:
                raise
            backoff = 2 ** attempt
            log.warning("fetch failed (%s), retrying in %ss: %s", e, backoff, url)
            time.sleep(backoff)
    raise RuntimeError("unreachable")
