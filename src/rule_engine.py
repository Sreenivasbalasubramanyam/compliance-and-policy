"""
rule_engine.py

Loads config/policy_rules.yaml and evaluates a synthetic transaction dataset
against each configured rule, producing structured "exceptions" (flags) for
transactions that trip a rule.

IMPORTANT: This is a portfolio demonstration of rule-engine mechanics, not a
production AML/compliance system. The rules, thresholds, and watchlist
referenced in config/policy_rules.yaml are explicitly illustrative /
fabricated - see the disclaimers in that file and in data/generate_transactions.py.
"""

import os
import sys
from dataclasses import dataclass, asdict
from datetime import timedelta
from typing import List

import pandas as pd
import yaml

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from watchlist_sample import FAKE_WATCHLIST_KEYWORDS  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config", "policy_rules.yaml")
DEFAULT_DATA_PATH = os.path.join(BASE_DIR, "data", "synthetic_transactions.csv")


@dataclass
class Exception_:
    rule_id: str
    rule_name: str
    severity: str
    transaction_id: str
    account_id: str
    timestamp: str
    reason: str


def load_rules(config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return {rule["rule_id"]: rule for rule in config["rules"]}


def load_transactions(data_path: str = DEFAULT_DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(data_path, parse_dates=["timestamp"])
    df = df.sort_values(["account_id", "timestamp"]).reset_index(drop=True)
    return df


# -----------------------------------------------------------------------------
# Individual rule evaluators
# -----------------------------------------------------------------------------

def _eval_structuring(df: pd.DataFrame, rule: dict) -> List[Exception_]:
    params = rule["params"]
    single_max = params["single_txn_max"]
    window = timedelta(hours=params["window_hours"])
    min_count = params["min_txn_count"]
    aggregate_min = params["aggregate_min"]
    txn_types = set(params["transaction_types"])

    exceptions = []
    candidates = df[(df["amount"] <= single_max) & (df["transaction_type"].isin(txn_types))]

    for account_id, group in candidates.groupby("account_id"):
        group = group.sort_values("timestamp")
        timestamps = group["timestamp"].tolist()
        amounts = group["amount"].tolist()
        txn_ids = group["transaction_id"].tolist()

        n = len(group)
        for i in range(n):
            window_end = timestamps[i] + window
            # collect all transactions within the window starting at i
            j = i
            window_amount = 0.0
            window_txn_ids = []
            while j < n and timestamps[j] <= window_end:
                window_amount += amounts[j]
                window_txn_ids.append(txn_ids[j])
                j += 1

            if len(window_txn_ids) >= min_count and window_amount >= aggregate_min:
                reason = (
                    f"{len(window_txn_ids)} sub-threshold cash transactions "
                    f"totaling ${window_amount:,.2f} within {params['window_hours']}h "
                    f"(each <= ${single_max:,.2f}), exceeding aggregate threshold "
                    f"of ${aggregate_min:,.2f}."
                )
                for txn_id in window_txn_ids:
                    ts = group.loc[group["transaction_id"] == txn_id, "timestamp"].iloc[0]
                    exceptions.append(
                        Exception_(
                            rule_id=rule["rule_id"],
                            rule_name=rule["name"],
                            severity=rule["severity"],
                            transaction_id=txn_id,
                            account_id=account_id,
                            timestamp=str(ts),
                            reason=reason,
                        )
                    )
                break  # avoid re-flagging overlapping windows repeatedly for the same account

    return exceptions


def _eval_large_transaction(df: pd.DataFrame, rule: dict) -> List[Exception_]:
    params = rule["params"]
    threshold = params["threshold_amount"]
    txn_types = set(params["transaction_types"])

    hits = df[(df["amount"] >= threshold) & (df["transaction_type"].isin(txn_types))]

    exceptions = []
    for _, row in hits.iterrows():
        reason = (
            f"Transaction amount ${row['amount']:,.2f} meets/exceeds the illustrative "
            f"large-transaction reporting threshold of ${threshold:,.2f} "
            f"(type: {row['transaction_type']})."
        )
        exceptions.append(
            Exception_(
                rule_id=rule["rule_id"],
                rule_name=rule["name"],
                severity=rule["severity"],
                transaction_id=row["transaction_id"],
                account_id=row["account_id"],
                timestamp=str(row["timestamp"]),
                reason=reason,
            )
        )
    return exceptions


def _eval_velocity(df: pd.DataFrame, rule: dict) -> List[Exception_]:
    params = rule["params"]
    window = timedelta(hours=params["window_hours"])
    max_count = params["max_transaction_count"]

    exceptions = []
    for account_id, group in df.groupby("account_id"):
        group = group.sort_values("timestamp")
        timestamps = group["timestamp"].tolist()
        txn_ids = group["transaction_id"].tolist()
        n = len(group)

        flagged_already = set()
        for i in range(n):
            window_end = timestamps[i] + window
            j = i
            window_txn_ids = []
            while j < n and timestamps[j] <= window_end:
                window_txn_ids.append(txn_ids[j])
                j += 1

            if len(window_txn_ids) > max_count:
                new_ids = [t for t in window_txn_ids if t not in flagged_already]
                if not new_ids:
                    continue
                reason = (
                    f"{len(window_txn_ids)} transactions within {params['window_hours']}h "
                    f"exceeds max allowed count of {max_count}."
                )
                for txn_id in new_ids:
                    ts = group.loc[group["transaction_id"] == txn_id, "timestamp"].iloc[0]
                    exceptions.append(
                        Exception_(
                            rule_id=rule["rule_id"],
                            rule_name=rule["name"],
                            severity=rule["severity"],
                            transaction_id=txn_id,
                            account_id=account_id,
                            timestamp=str(ts),
                            reason=reason,
                        )
                    )
                    flagged_already.add(txn_id)
    return exceptions


def _eval_watchlist(df: pd.DataFrame, rule: dict) -> List[Exception_]:
    """
    Naive keyword screening against an OBVIOUSLY FAKE sample watchlist
    (see src/watchlist_sample.py: FAKE_WATCHLIST_KEYWORDS). This is
    NOT representative of real sanctions/watchlist screening.
    """
    case_sensitive = rule["params"].get("case_sensitive", False)
    keywords = FAKE_WATCHLIST_KEYWORDS if case_sensitive else [k.lower() for k in FAKE_WATCHLIST_KEYWORDS]

    exceptions = []
    for _, row in df.iterrows():
        name = row["counterparty_name"]
        compare_name = name if case_sensitive else str(name).lower()
        for kw in keywords:
            if kw in compare_name:
                reason = f"Counterparty name '{name}' matches fake sample watchlist keyword '{kw}'."
                exceptions.append(
                    Exception_(
                        rule_id=rule["rule_id"],
                        rule_name=rule["name"],
                        severity=rule["severity"],
                        transaction_id=row["transaction_id"],
                        account_id=row["account_id"],
                        timestamp=str(row["timestamp"]),
                        reason=reason,
                    )
                )
                break
    return exceptions


RULE_EVALUATORS = {
    "structuring_threshold": _eval_structuring,
    "large_transaction_reporting_threshold": _eval_large_transaction,
    "velocity_rule": _eval_velocity,
    "watchlist_keyword_screening": _eval_watchlist,
}


def run_rule_engine(
    df: pd.DataFrame = None,
    rules: dict = None,
    data_path: str = DEFAULT_DATA_PATH,
    config_path: str = DEFAULT_CONFIG_PATH,
) -> List[dict]:
    """Evaluate every transaction against every configured rule. Returns a list of
    exception dicts (rule_id, rule_name, severity, transaction_id, account_id,
    timestamp, reason)."""
    if df is None:
        df = load_transactions(data_path)
    if rules is None:
        rules = load_rules(config_path)

    all_exceptions: List[Exception_] = []
    for rule_id, rule in rules.items():
        evaluator = RULE_EVALUATORS.get(rule["name"])
        if evaluator is None:
            continue
        all_exceptions.extend(evaluator(df, rule))

    return [asdict(e) for e in all_exceptions]


if __name__ == "__main__":
    exceptions = run_rule_engine()
    print(f"Total exceptions flagged: {len(exceptions)}")
    for rule_name in RULE_EVALUATORS:
        count = sum(1 for e in exceptions if e["rule_name"] == rule_name)
        print(f"  {rule_name}: {count}")
