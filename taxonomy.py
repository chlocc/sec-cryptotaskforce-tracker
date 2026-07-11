"""Fixed universal topic taxonomy, applied across all four sources.

Discovered once via claude-opus-4-6 over the full corpus (2026-07-11) and
frozen here so tags stay stable as new items arrive daily. Re-derive only
if the corpus's subject matter shifts enough that the tag set stops fitting
(e.g. a wave of items about a topic with no home here).
"""

TOPICS = [
    "Security Status",
    "Tokenization",
    "Trading & Market Structure",
    "Custody",
    "Broker-Dealer Registration",
    "DeFi Protocols",
    "Clearing & Settlement",
    "Crypto ETPs",
    "Stablecoins",
    "Safe Harbor & Exemptions",
    "Investor Protection",
    "Compliance Technology",
    "Regulatory Framework",
    "Public Offerings",
]
