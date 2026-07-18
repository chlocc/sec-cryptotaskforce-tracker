"""OpenRouter fallback client.

Used only when the Anthropic API call fails (e.g. out of credit) — free-tier
OpenRouter models are lower quality than Claude Opus, so this is a fallback
path, never the primary one. See summarize.py and enrich.py for call sites.
"""

import json
import logging
import os
import time

import httpx

log = logging.getLogger("tracker.openrouter")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Free-tier OpenRouter models rotate over time — if this one starts erroring
# or disappears, check https://openrouter.ai/models?max_price=0 and set
# OPENROUTER_MODEL in .env to override.
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it:free"


def _extract_json(text: str | None) -> dict:
    if not text:
        raise RuntimeError("OpenRouter response had no content (model may have used its "
                            "reasoning budget without producing final output)")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first, rest = text.split("\n", 1)
            text = rest if first.strip().lower() in ("json", "") else text
    return json.loads(text)


def complete_json(system: str, user: str, schema_hint: str) -> dict:
    """Ask a free OpenRouter model for a JSON object matching schema_hint.

    Raises on any failure (missing key, network, non-2xx, unparseable JSON) —
    callers are already in a fallback path with nothing further to fall back to.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"{user}\n\nRespond with ONLY a JSON object matching this shape "
                    f"— no markdown fences, no commentary:\n{schema_hint}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    }

    # Free-tier models are served by rotating upstream providers that
    # frequently 429 with a short retry_after — worth one or two retries
    # since this call site only fires a handful of times a day.
    last_exc = None
    for attempt in range(3):
        resp = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=120,
        )
        if resp.status_code == 429 and attempt < 2:
            wait = float(resp.headers.get("Retry-After", 2 ** (attempt + 2)))
            log.warning("OpenRouter rate-limited, retrying in %.0fs", wait)
            time.sleep(wait)
            continue
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            last_exc = e
            break
        body = resp.json()
        text = body["choices"][0]["message"]["content"]
        return _extract_json(text)
    raise last_exc
