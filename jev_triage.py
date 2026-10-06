"""Prototype: TypeSafe Jev triage for tracker items (not wired into run_daily).

One Jev request per item asks, in parallel over the same state:
  - materiality: a Score on 4 concrete levels (routine -> official SEC action)
  - one Noul per taxonomy topic (multi-label, replaces the LLM tag call)

Jev returns probabilities, not text, so it can't replace the takeaway or
bullet summaries — only the classification half of enrich.py.

Evaluation mode (default) scores every item in data/items.json, compares
Jev's tags against the existing LLM tags, and writes data/jev_eval.json.
Nothing in items.json or docs/ is modified.

    python3 jev_triage.py            # all items
    python3 jev_triage.py --limit 10 # quick smoke test

Needs TYPESAFE_API_KEY in .env (https://console.typesafe.ai/).
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import run_daily  # noqa: E402

run_daily.load_env()

from typesafe_sdk import AsyncTypeSafeClient, Noul, Score  # noqa: E402

from taxonomy import TOPICS  # noqa: E402

ITEMS_PATH = ROOT / "data" / "items.json"
OUT_PATH = ROOT / "data" / "jev_eval.json"
MODEL = "jev-1.13.0"  # pinned so thresholds tuned here don't drift with jev-latest
CONCURRENCY = 8
TOPIC_THRESHOLD = 0.5

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("jev")

SOURCE_LABELS = {
    "written-input": "Public written input submitted to the SEC Crypto Task Force",
    "cryptosec": "SEC staff statement, order, or no-action letter on crypto",
    "meetings": "Memo of a meeting between the Crypto Task Force and outside parties",
    "newsroom": "SEC newsroom item: speech, statement, or announcement",
}

TOPIC_DEFS = {
    "Security Status": "whether a crypto asset or transaction is a security (Howey, investment contracts, network maturity)",
    "Tokenization": "tokenized securities or real-world assets, on-chain registries, transfer agents for tokens",
    "Trading & Market Structure": "exchanges, ATSs, trading venues, market making, listing standards",
    "Custody": "safekeeping of crypto assets, qualified custodians, key management",
    "Broker-Dealer Registration": "broker-dealer rules, net capital, customer protection rules for crypto",
    "DeFi Protocols": "decentralized finance protocols, smart contracts, DAOs, front-ends",
    "Clearing & Settlement": "clearing agencies, settlement finality, DVP, collateral",
    "Crypto ETPs": "exchange-traded products holding crypto, listing of crypto ETFs",
    "Stablecoins": "payment stablecoins, stablecoin reserves and treatment",
    "Safe Harbor & Exemptions": "safe harbors, exemptive relief, no-action relief, token offering exemptions",
    "Investor Protection": "fraud, disclosure to retail investors, consumer and investor safeguards",
    "Compliance Technology": "RegTech, on-chain compliance, identity verification, surveillance tools",
    "Regulatory Framework": "overall SEC approach to crypto, jurisdiction with CFTC, legislation, rulemaking agenda",
    "Public Offerings": "registered or exempt offerings of crypto assets, disclosure for token sales",
}

MATERIALITY = Score(
    instructions=(
        "For a crypto-regulatory lawyer scanning this tracker, how much does the item "
        "`title` (with `summary`) matter? Judge the item's regulatory weight, not how "
        "well it is written."
    ),
    criteria=[
        "Routine: a courtesy meeting memo listing attendees and generic topics, a short or "
        "form-letter comment, or a personal opinion with no specific request",
        "Incremental: restates known industry positions or covers topics already widely "
        "discussed, with no concrete new proposal and no SEC action",
        "Substantive: a detailed, specific request or proposal (rule text, exemption design, "
        "interpretive question) from a significant market participant, or a commissioner or "
        "staff speech signaling a policy direction",
        "Official action: the SEC or its staff issues a statement, order, no-action letter, "
        "exemption, proposed or final rule, or formal policy that changes what market "
        "participants may do",
    ],
)


def questions() -> dict:
    qs = {"materiality": MATERIALITY}
    for topic in TOPICS:
        qs[f"topic:{topic}"] = Noul(
            instructions=(
                f"Is \"{topic}\" ({TOPIC_DEFS[topic]}) a main subject of this item — "
                "something the `summary` actually discusses, not just a passing mention?"
            ),
        )
    return qs


def state(item: dict) -> dict:
    return {
        "source": SOURCE_LABELS[item["source"]],
        "title": item["title"],
        "author": item["author"],
        "date": item["date"],
        "summary": item["key_points"],
    }


async def triage(client: AsyncTypeSafeClient, item: dict) -> dict:
    resp = await client.system_one(state(item), questions(), model=MODEL)
    m = resp.scores["materiality"]
    topic_p = {t: resp.nouls[f"topic:{t}"].noul for t in TOPICS}
    ranked = sorted(topic_p, key=topic_p.get, reverse=True)
    picked = [t for t in ranked if topic_p[t] >= TOPIC_THRESHOLD][:3] or ranked[:1]
    return {
        "id": item["id"],
        "materiality": round(m.score, 2),
        "materiality_confidence": round(m.confidence, 2),
        "topic_probs": {t: round(p, 3) for t, p in topic_p.items()},
        "jev_topics": picked,
        "input_tokens": resp.usage.input_tokens if resp.usage else None,
    }


async def run(items: list[dict]) -> list[dict]:
    sem = asyncio.Semaphore(CONCURRENCY)
    async with AsyncTypeSafeClient() as client:
        async def one(it):
            async with sem:
                try:
                    return await triage(client, it)
                except Exception as e:
                    log.error("failed %s: %s", it["title"][:60], e)
                    return None
        results = await asyncio.gather(*(one(it) for it in items))
    return [r for r in results if r]


def report(items: list[dict], results: list[dict]) -> dict:
    by_id = {it["id"]: it for it in items}
    tp = fp = fn = exact = top1_hit = 0
    per_topic = {t: Counter() for t in TOPICS}
    for r in results:
        old, new = set(by_id[r["id"]].get("topics") or []), set(r["jev_topics"])
        tp += len(old & new); fp += len(new - old); fn += len(old - new)
        exact += old == new
        top1_hit += bool(r["jev_topics"]) and r["jev_topics"][0] in old
        for t in TOPICS:
            per_topic[t]["tp" if t in old and t in new else "fp" if t in new else "fn" if t in old else "tn"] += 1
    n = len(results)
    buckets = Counter(round(r["materiality"]) for r in results)
    tokens = sum(r["input_tokens"] or 0 for r in results)
    summary = {
        "items": n,
        "topic_precision_vs_llm": round(tp / max(tp + fp, 1), 3),
        "topic_recall_vs_llm": round(tp / max(tp + fn, 1), 3),
        "exact_tag_set_match": round(exact / max(n, 1), 3),
        "jev_top_tag_in_llm_tags": round(top1_hit / max(n, 1), 3),
        "materiality_histogram": {str(k): buckets[k] for k in range(4)},
        "input_tokens": tokens,
        "est_cost_usd": round(tokens * 0.042 / 1e6, 4),
        "per_topic": {t: dict(c) for t, c in per_topic.items()},
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    items = json.loads(ITEMS_PATH.read_text())
    todo = items[: args.limit] if args.limit else items
    log.info("triaging %d items with %s", len(todo), MODEL)
    results = asyncio.run(run(todo))
    summary = report(items, results)

    by_id = {it["id"]: it for it in items}
    for r in results:
        it = by_id[r["id"]]
        r.update(source=it["source"], date=it["date"], title=it["title"], llm_topics=it.get("topics"))
    OUT_PATH.write_text(json.dumps({"summary": summary, "results": results}, indent=1, ensure_ascii=False))

    print(json.dumps({k: v for k, v in summary.items() if k != "per_topic"}, indent=1))
    ranked = sorted(results, key=lambda r: r["materiality"], reverse=True)
    print("\nMost material:")
    for r in ranked[:8]:
        print(f"  {r['materiality']:.2f}  [{r['source']}] {r['title'][:90]}")
    print("\nLeast material:")
    for r in ranked[-8:]:
        print(f"  {r['materiality']:.2f}  [{r['source']}] {r['title'][:90]}")
    print(f"\nwrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
