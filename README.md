# SEC Crypto Task Force Tracker

A static website that tracks and summarizes updates from the SEC Crypto Task Force,
refreshed daily by a Python pipeline. Covers items dated **January 1, 2026 onward** from
four SEC pages:

| Feed | Source | Summary method |
|---|---|---|
| Written Input | [crypto-task-force-written-input](https://www.sec.gov/featured-topics/crypto-task-force/crypto-task-force-written-input) | SEC-provided key points (Claude condenses overly long ones) |
| Staff Statements | [Crypto@SEC](https://www.sec.gov/featured-topics/crypto-task-force/cryptosec) | SEC-provided summaries (Claude condenses overly long ones) |
| Meetings | [crypto-task-force-meetings](https://www.sec.gov/securities-topics/crypto-task-force/crypto-task-force-meetings) | Meeting memo PDF summarized by Claude (2–4 bullets) |
| Newsroom | [crypto-newsroom](https://www.sec.gov/about/crypto-task-force/crypto-newsroom) | Linked speech/statement page summarized by Claude (2–4 bullets) |

The site is a single reverse-chronological feed with source tabs, clickable topic-tag
filtering, and keyword search. Every item also gets a one-line takeaway and 1–3 tags
from a fixed 14-topic taxonomy (`taxonomy.py`), assigned by `claude-opus-4-6` — see
`enrich.py`.

## Setup

Requires Python 3.11 (`/Library/Frameworks/Python.framework/Versions/3.11/bin/python3`).

```bash
pip install requests beautifulsoup4 pymupdf anthropic
```

Create `.env` in the project root (gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Running

```bash
python3 run_daily.py              # daily incremental run: scrape → summarize new → regenerate → git commit/push
python3 run_daily.py --backfill   # explicit alias (dedupe makes every run incremental)
python3 run_daily.py --no-git     # skip the commit/push step
```

The pipeline is idempotent — already-seen items (keyed by a stable hash of
source + URL + title) are skipped. Gist summarization uses `claude-opus-4-7`
(adaptive thinking, medium effort). Every new item is then enriched with a one-line
takeaway and 1–3 topic tags via `claude-opus-4-6` (adaptive thinking, medium
effort) — for written input this pass also further condenses the SEC's own
bullets into 2–3 tighter ones. Both steps use structured JSON output.

To re-run enrichment over existing items (e.g. after editing `taxonomy.py`):

```bash
python3 enrich.py --force            # re-enrich everything
python3 enrich.py --limit 5          # test on a handful first
```

Preview locally:

```bash
cd docs && python3 -m http.server 8000   # → http://localhost:8000
```

## Architecture

```
run_daily.py           orchestrator: scrape → dedupe → summarize → enrich → generate → git publish
scraper/fetch.py       throttled requests session (SEC fair-access User-Agent)
scraper/common.py      record schema, 2026-01-01 cutoff, stable IDs
scraper/*.py           one scraper per SEC page (stop crawling at the cutoff)
summarize.py           Anthropic API gist summarizer (2–4 attributed bullets)
taxonomy.py            frozen 14-topic universal taxonomy
enrich.py              per-item takeaway + topic tags (+ tighter written-input bullets)
generate_site.py       data/items.json → docs/data.json
docs/                  static frontend (GitHub Pages root) (index.html, style.css, app.js, data.json)
data/items.json        canonical item store (also serves as the dedupe state)
```

**Failure handling:** if a source page fails to fetch or a previously non-empty
source suddenly parses to zero rows (layout drift), the pipeline keeps prior data
and logs a warning rather than publishing an emptied feed. Items whose document
can't be summarized are flagged `thin` and shown with a "see source" note.

## Deployment (GitHub Pages)

Already live: the repo deploys to GitHub Pages from the `main` branch, `/docs`
folder. `run_daily.py` auto-commits and pushes on each run, so the Pages site
updates automatically.

## Daily schedule

Mirror the Daily Crypto Brief setup: a scheduled task that runs
`python3 run_daily.py` once a day. The run is quiet — no notifications; the
site just refreshes.
