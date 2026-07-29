import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rule_engine import load_rules, run_rule_engine  # noqa: E402
from watchlist_sample import FAKE_WATCHLIST_KEYWORDS  # noqa: E402

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "policy_rules.yaml")


@pytest.fixture
def rules():
    return load_rules(CONFIG_PATH)


def _txn(txn_id, account_id, ts, amount, counterparty, txn_type):
    return {
        "transaction_id": txn_id,
        "account_id": account_id,
        "timestamp": ts,
        "amount": amount,
        "counterparty_name": counterparty,
        "transaction_type": txn_type,
    }


def _to_df(rows):
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# -----------------------------------------------------------------------------
# structuring_threshold
# -----------------------------------------------------------------------------

def test_structuring_rule_fires_on_crafted_transaction(rules):
    base = datetime(2026, 6, 1, 9, 0)
    rows = [
        _txn("T1", "ACCT-STRUCT", base, 4500, "Acme Retail Corp", "cash_deposit"),
        _txn("T2", "ACCT-STRUCT", base + timedelta(hours=2), 4200, "Acme Retail Corp", "cash_deposit"),
        _txn("T3", "ACCT-STRUCT", base + timedelta(hours=5), 4000, "Acme Retail Corp", "cash_deposit"),
    ]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    struct_exceptions = [e for e in exceptions if e["rule_name"] == "structuring_threshold"]
    assert len(struct_exceptions) == 3
    assert all(e["account_id"] == "ACCT-STRUCT" for e in struct_exceptions)


def test_structuring_rule_does_not_fire_on_clean_transaction(rules):
    base = datetime(2026, 6, 1, 9, 0)
    rows = [
        _txn("T1", "ACCT-CLEAN", base, 500, "Acme Retail Corp", "cash_deposit"),
        _txn("T2", "ACCT-CLEAN", base + timedelta(days=2), 600, "Acme Retail Corp", "cash_deposit"),
    ]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    struct_exceptions = [e for e in exceptions if e["rule_name"] == "structuring_threshold"]
    assert len(struct_exceptions) == 0


# -----------------------------------------------------------------------------
# large_transaction_reporting_threshold
# -----------------------------------------------------------------------------

def test_large_transaction_rule_fires_on_crafted_transaction(rules):
    base = datetime(2026, 6, 1, 10, 0)
    rows = [_txn("T1", "ACCT-LARGE", base, 15000, "Acme Retail Corp", "wire_transfer")]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    large_exceptions = [e for e in exceptions if e["rule_name"] == "large_transaction_reporting_threshold"]
    assert len(large_exceptions) == 1
    assert large_exceptions[0]["transaction_id"] == "T1"


def test_large_transaction_rule_does_not_fire_on_clean_transaction(rules):
    base = datetime(2026, 6, 1, 10, 0)
    rows = [_txn("T1", "ACCT-CLEAN", base, 2500, "Acme Retail Corp", "wire_transfer")]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    large_exceptions = [e for e in exceptions if e["rule_name"] == "large_transaction_reporting_threshold"]
    assert len(large_exceptions) == 0


# -----------------------------------------------------------------------------
# velocity_rule
# -----------------------------------------------------------------------------

def test_velocity_rule_fires_on_crafted_transaction(rules):
    base = datetime(2026, 6, 1, 8, 0)
    rows = [
        _txn(f"T{i}", "ACCT-VELOCITY", base + timedelta(minutes=30 * i), 100 + i, "Acme Retail Corp", "card_payment")
        for i in range(12)
    ]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    velocity_exceptions = [e for e in exceptions if e["rule_name"] == "velocity_rule"]
    assert len(velocity_exceptions) > 0
    assert all(e["account_id"] == "ACCT-VELOCITY" for e in velocity_exceptions)


def test_velocity_rule_does_not_fire_on_clean_transaction(rules):
    base = datetime(2026, 6, 1, 8, 0)
    rows = [
        _txn(f"T{i}", "ACCT-CLEAN", base + timedelta(hours=3 * i), 100 + i, "Acme Retail Corp", "card_payment")
        for i in range(4)
    ]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    velocity_exceptions = [e for e in exceptions if e["rule_name"] == "velocity_rule"]
    assert len(velocity_exceptions) == 0


# -----------------------------------------------------------------------------
# watchlist_keyword_screening
# -----------------------------------------------------------------------------

def test_watchlist_rule_fires_on_crafted_transaction(rules):
    base = datetime(2026, 6, 1, 11, 0)
    watchlisted_name = FAKE_WATCHLIST_KEYWORDS[0].title()
    rows = [_txn("T1", "ACCT-WATCH", base, 1200, watchlisted_name, "wire_transfer")]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    watch_exceptions = [e for e in exceptions if e["rule_name"] == "watchlist_keyword_screening"]
    assert len(watch_exceptions) == 1
    assert watch_exceptions[0]["transaction_id"] == "T1"


def test_watchlist_rule_does_not_fire_on_clean_transaction(rules):
    base = datetime(2026, 6, 1, 11, 0)
    rows = [_txn("T1", "ACCT-CLEAN", base, 1200, "Acme Retail Corp", "wire_transfer")]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    watch_exceptions = [e for e in exceptions if e["rule_name"] == "watchlist_keyword_screening"]
    assert len(watch_exceptions) == 0


# -----------------------------------------------------------------------------
# General engine sanity checks
# -----------------------------------------------------------------------------

def test_engine_returns_structured_exception_fields(rules):
    base = datetime(2026, 6, 1, 10, 0)
    rows = [_txn("T1", "ACCT-LARGE", base, 20000, "Acme Retail Corp", "wire_transfer")]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    assert len(exceptions) >= 1
    expected_keys = {"rule_id", "rule_name", "severity", "transaction_id", "account_id", "timestamp", "reason"}
    assert expected_keys.issubset(exceptions[0].keys())


def test_engine_handles_fully_clean_dataset(rules):
    base = datetime(2026, 6, 1, 9, 0)
    rows = [
        _txn("T1", "ACCT-CLEAN", base, 200, "Acme Retail Corp", "card_payment"),
        _txn("T2", "ACCT-CLEAN", base + timedelta(hours=4), 300, "Blue Harbor Supplies", "ach_transfer"),
    ]
    df = _to_df(rows)
    exceptions = run_rule_engine(df=df, rules=rules)
    assert len(exceptions) == 0
