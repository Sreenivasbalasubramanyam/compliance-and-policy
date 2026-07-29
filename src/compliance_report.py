"""
compliance_report.py

Aggregates rule_engine.py output into a summary compliance report:
  - outputs/compliance_exceptions.csv  (full, structured exception detail)
  - outputs/summary.txt                (human-readable counts by rule/severity)

IMPORTANT: This is a portfolio demonstration of a rule-engine reporting
workflow, not a production compliance report. See disclaimers in
config/policy_rules.yaml and data/generate_transactions.py.
"""

import os
import sys
from datetime import datetime

import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from rule_engine import load_rules, load_transactions, run_rule_engine  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
EXCEPTIONS_CSV_PATH = os.path.join(OUTPUT_DIR, "compliance_exceptions.csv")
SUMMARY_TXT_PATH = os.path.join(OUTPUT_DIR, "summary.txt")


def build_report(data_path=None, config_path=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = load_transactions(data_path) if data_path else load_transactions()
    rules = load_rules(config_path) if config_path else load_rules()

    exceptions = run_rule_engine(df=df, rules=rules)
    exceptions_df = pd.DataFrame(exceptions)

    if exceptions_df.empty:
        exceptions_df = pd.DataFrame(
            columns=["rule_id", "rule_name", "severity", "transaction_id", "account_id", "timestamp", "reason"]
        )

    exceptions_df.to_csv(EXCEPTIONS_CSV_PATH, index=False)

    total_transactions = len(df)
    total_exceptions = len(exceptions_df)
    unique_accounts_flagged = exceptions_df["account_id"].nunique() if not exceptions_df.empty else 0

    by_rule = exceptions_df["rule_name"].value_counts() if not exceptions_df.empty else pd.Series(dtype=int)
    by_severity = exceptions_df["severity"].value_counts() if not exceptions_df.empty else pd.Series(dtype=int)

    lines = []
    lines.append("=" * 70)
    lines.append("TRANSACTION COMPLIANCE MONITORING - SUMMARY REPORT")
    lines.append("(SYNTHETIC DATA - portfolio demonstration only, not a real compliance report)")
    lines.append("=" * 70)
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Total transactions screened: {total_transactions}")
    lines.append(f"Total exceptions flagged:    {total_exceptions}")
    lines.append(f"Unique accounts flagged:     {unique_accounts_flagged}")
    lines.append("")
    lines.append("Exceptions by rule:")
    for rule_name, count in by_rule.items():
        lines.append(f"  - {rule_name}: {count}")
    lines.append("")
    lines.append("Exceptions by severity:")
    for severity, count in by_severity.items():
        lines.append(f"  - {severity}: {count}")
    lines.append("")
    lines.append(f"Full exception detail written to: {os.path.relpath(EXCEPTIONS_CSV_PATH, BASE_DIR)}")
    lines.append("=" * 70)

    summary_text = "\n".join(lines)
    with open(SUMMARY_TXT_PATH, "w") as f:
        f.write(summary_text + "\n")

    print(summary_text)

    return {
        "total_transactions": total_transactions,
        "total_exceptions": total_exceptions,
        "unique_accounts_flagged": unique_accounts_flagged,
        "by_rule": by_rule.to_dict(),
        "by_severity": by_severity.to_dict(),
    }


if __name__ == "__main__":
    build_report()
