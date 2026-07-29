"""
watchlist_sample.py

A single, shared source of truth for the OBVIOUSLY FAKE sample "watchlist"
used by both the synthetic data generator (data/generate_transactions.py)
and the rule engine (src/rule_engine.py).

DISCLAIMER: This is a fabricated, illustrative list of made-up entity names
for demonstration purposes only. It is NOT a real sanctions or watchlist
data source (not OFAC's SDN list, not a UN list, not any real government or
institutional watchlist) and must not be treated as one.
"""

FAKE_WATCHLIST_KEYWORDS = [
    "shadowport trading fake llc",
    "northwind fictitious holdings",
    "example sanctioned test co",
    "faux global remit demo",
]
