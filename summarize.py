"""Anthropic-powered gist summarizer.

Each item gets 2-4 short bullet key points from its source document (meeting
memo PDF or speech/statement page). Uses claude-opus-4-7 with adaptive
thinking — these calls read full source documents, so comprehension quality
matters more than in the tag-classification step. Structured output
(json_schema) guarantees a parseable bullet list.
"""

import logging

import anthropic

log = logging.getLogger("tracker.summarize")

MODEL = "claude-opus-4-7"

SYSTEM = (
    "You summarize SEC Crypto Task Force materials for a regulatory professional. "
    "Produce 2-4 bullet key points, each 30 words or fewer, in a neutral, precise register. "
    "Attribute positions to their holders (e.g. 'The commenter argued...', "
    "'Commissioner Peirce stated...'); never present a party's view as fact. "
    "Only state what the source text supports; do not invent details. "
    "No hype, no editorializing on policy merits."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["key_points"],
    "additionalProperties": False,
}

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


def gist(kind: str, title: str, meta: str, text: str) -> list[str]:
    """Summarize source text into 2-4 bullets. Raises on unrecoverable API errors."""
    import json

    prompt = (
        f"Source type: {kind}\nTitle: {title}\n{meta}\n\n"
        f"Source text:\n{text}\n\n"
        "Return the key points as JSON."
    )
    response = client().messages.create(
        model=MODEL,
        max_tokens=4000,  # adaptive thinking counts toward this cap
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        log.warning("summarization refused for %r", title)
        return []
    body = next((b.text for b in response.content if b.type == "text"), "")
    points = json.loads(body)["key_points"]
    return [p.strip() for p in points if p.strip()][:4]


def needs_condensing(points: list[str]) -> bool:
    """SEC-provided text is kept verbatim unless it's too long to scan."""
    if len(points) > 4:
        return True
    return any(len(p.split()) > 60 for p in points)
