"""
generate_transactions.py

Generates a SYNTHETIC financial transaction dataset for a transaction
compliance monitoring / rule engine demonstration project.

IMPORTANT DISCLAIMER:
    - Every transaction, account, and counterparty name produced by this
      script is entirely FABRICATED for portfolio demonstration purposes.
    - No real customer, account, or transaction records are used.
    - A small number of "watchlist" counterparty names are deliberately
      planted (see FAKE_WATCHLIST_KEYWORDS) purely to demonstrate keyword
      screening logic. This is an OBVIOUSLY FAKE sample list and bears no
      relationship to any real sanctions/watchlist data source (not OFAC,
      not UN, not any government or institutional list).
    - The vast majority of generated transactions are randomized "clean"
      background noise; a deliberately small, clearly-commented subset of
      transactions is crafted to trip each rule in
      config/policy_rules.yaml, so the rule engine has real positives to
      catch alongside a much larger set of true negatives.

Usage:
    python data/generate_transactions.py --accounts 150 --days 14 --seed 7
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from watchlist_sample import FAKE_WATCHLIST_KEYWORDS  # noqa: E402 - obviously fake sample watchlist, NOT a real sanctions/watchlist data source

CLEAN_COUNTERPARTY_NAMES = [
    "Acme Retail Corp", "Blue Harbor Supplies", "Riverside Grocers",
    "Metro Utilities Co", "Sunrise Bakery", "Greenfield Logistics",
    "Cedar Point Electronics", "Harbor View Realty", "Palmdale Auto Parts",
    "Everett Consulting Group", "Lakeside Medical Supply", "Union Hardware",
    "Bright Path Insurance", "Maple Street Cafe", "Falcon Freight Inc",
    "Crestwood Dental Group", "Silver Creek Farms", "Ironclad Security LLC",
    "Willow Bend Textiles", "Northgate Pharmacy",
]

TRANSACTION_TYPES = ["cash_deposit", "cash_withdrawal", "wire_transfer", "ach_transfer", "card_payment"]


def _rand_txn_id():
    return f"TXN-{uuid.uuid4().hex[:10].upper()}"


def generate_transactions(n_accounts: int = 150, n_days: int = 14, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    accounts = [f"ACCT-{1000 + i}" for i in range(n_accounts)]
    start_date = datetime(2026, 6, 1)

    rows = []

    # --- 1. Background "clean" traffic -------------------------------------------------
    # Draw a per-account-day transaction count directly from a tight Poisson(2) instead of
    # uniformly scattering a fixed total pool of transactions across accounts/days - the
    # latter produces extreme-value outliers (a handful of ordinary accounts randomly
    # collide into double-digit daily counts just by chance across ~n_accounts*n_days
    # buckets), which would falsely trip the velocity rule on "clean" accounts. Capping
    # the per-day draw keeps background noise clearly separated from the deliberately
    # crafted velocity-spike accounts injected in section 4 below.
    for acct in accounts:
        for day_offset in range(n_days):
            daily_count = min(int(rng.poisson(lam=2.0)), 6)
            for _ in range(daily_count):
                seconds_offset = rng.integers(0, 24 * 3600)
                ts = start_date + timedelta(days=int(day_offset), seconds=int(seconds_offset))
                txn_type = rng.choice(TRANSACTION_TYPES, p=[0.18, 0.12, 0.15, 0.25, 0.30])
                amount = round(float(rng.gamma(shape=2.0, scale=350)), 2)
                counterparty = rng.choice(CLEAN_COUNTERPARTY_NAMES)
                rows.append(
                    {
                        "transaction_id": _rand_txn_id(),
                        "account_id": acct,
                        "timestamp": ts.isoformat(),
                        "amount": amount,
                        "counterparty_name": counterparty,
                        "transaction_type": txn_type,
                    }
                )

    # --- 2. Structuring pattern: 3-4 sub-threshold cash txns within 24h, ------------------
    #        aggregating above the $10,000 illustrative threshold, on a handful of accounts.
    structuring_accounts = rng.choice(accounts, size=4, replace=False)
    for acct in structuring_accounts:
        base_day = int(rng.integers(1, n_days - 1))
        base_ts = start_date + timedelta(days=base_day, hours=9)
        n_parts = int(rng.integers(3, 5))
        part_amounts = rng.uniform(3200, 8800, size=n_parts).round(2)
        for i, amt in enumerate(part_amounts):
            ts = base_ts + timedelta(hours=int(rng.integers(0, 20)) if i > 0 else 0)
            rows.append(
                {
                    "transaction_id": _rand_txn_id(),
                    "account_id": acct,
                    "timestamp": ts.isoformat(),
                    "amount": float(amt),
                    "counterparty_name": rng.choice(CLEAN_COUNTERPARTY_NAMES),
                    "transaction_type": "cash_deposit",
                }
            )

    # --- 3. Large single transactions at/above the illustrative CTR-style threshold --------
    large_txn_accounts = rng.choice(accounts, size=6, replace=False)
    for acct in large_txn_accounts:
        day_offset = int(rng.integers(0, n_days))
        ts = start_date + timedelta(days=day_offset, hours=int(rng.integers(8, 18)))
        amount = round(float(rng.uniform(10000, 45000)), 2)
        txn_type = rng.choice(["cash_deposit", "wire_transfer", "cash_withdrawal"])
        rows.append(
            {
                "transaction_id": _rand_txn_id(),
                "account_id": acct,
                "timestamp": ts.isoformat(),
                "amount": amount,
                "counterparty_name": rng.choice(CLEAN_COUNTERPARTY_NAMES),
                "transaction_type": txn_type,
            }
        )

    # --- 4. Velocity spikes: an account with 10-15 transactions in a single day -------------
    velocity_accounts = rng.choice(accounts, size=3, replace=False)
    for acct in velocity_accounts:
        day_offset = int(rng.integers(0, n_days))
        base_ts = start_date + timedelta(days=day_offset)
        n_burst = int(rng.integers(10, 16))
        for _ in range(n_burst):
            ts = base_ts + timedelta(minutes=int(rng.integers(0, 23 * 60)))
            rows.append(
                {
                    "transaction_id": _rand_txn_id(),
                    "account_id": acct,
                    "timestamp": ts.isoformat(),
                    "amount": round(float(rng.gamma(shape=2.0, scale=150)), 2),
                    "counterparty_name": rng.choice(CLEAN_COUNTERPARTY_NAMES),
                    "transaction_type": rng.choice(TRANSACTION_TYPES),
                }
            )

    # --- 5. Watchlist keyword hits: transactions to/from a FAKE sample watchlist name --------
    watchlist_accounts = rng.choice(accounts, size=5, replace=False)
    for acct in watchlist_accounts:
        day_offset = int(rng.integers(0, n_days))
        ts = start_date + timedelta(days=day_offset, hours=int(rng.integers(8, 18)))
        counterparty = rng.choice(FAKE_WATCHLIST_KEYWORDS)
        # randomize capitalization to demonstrate case-insensitive matching
        if rng.random() < 0.5:
            counterparty = counterparty.title()
        rows.append(
            {
                "transaction_id": _rand_txn_id(),
                "account_id": acct,
                "timestamp": ts.isoformat(),
                "amount": round(float(rng.uniform(500, 6000)), 2),
                "counterparty_name": counterparty,
                "transaction_type": rng.choice(["wire_transfer", "ach_transfer"]),
            }
        )

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic transaction data.")
    parser.add_argument("--accounts", type=int, default=150)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    df = generate_transactions(n_accounts=args.accounts, n_days=args.days, seed=args.seed)

    out_path = args.out
    if out_path is None:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synthetic_transactions.csv")

    df.to_csv(out_path, index=False)
    print(f"Generated {len(df)} synthetic transactions -> {out_path}")
    print(f"Accounts: {df['account_id'].nunique()}, date range: {df['timestamp'].min()} to {df['timestamp'].max()}")


if __name__ == "__main__":
    main()
