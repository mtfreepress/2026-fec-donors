from __future__ import annotations

from typing import Any

import pandas as pd


SUMMARY_METRICS = {
    "individual_itemized_contributions": "individual_itemized_contributions",
    "individual_unitemized_contributions": "individual_unitemized_contributions",
    "political_party_committee_contributions": "political_party_committee_contributions",
    "other_political_committee_contributions": "other_political_committee_contributions",
    "candidate_contribution": "candidate_contribution",
}


def assert_recipient_mapping(receipts: pd.DataFrame, candidate_committees: pd.DataFrame) -> None:
    known = set(candidate_committees["committee_id"].dropna())
    observed = set(receipts["committee_id"].dropna())
    missing = sorted(observed - known)
    if missing:
        raise ValueError("Schedule A recipients do not map to selected candidates: " + ", ".join(missing))


def transaction_diagnostics(receipts: pd.DataFrame) -> dict[str, int]:
    sub_ids = receipts["sub_id"].dropna()
    return {
        "record_count": len(receipts),
        "duplicate_sub_id_rows": int(sub_ids.duplicated(keep=False).sum()),
        "unparsed_date_rows": int(receipts["contribution_receipt_date"].isna().sum()),
        "non_numeric_amount_rows": int(receipts["contribution_receipt_amount"].isna().sum()),
    }


def committee_resolution_rate(receipts: pd.DataFrame) -> float | None:
    committee_ids = receipts["contributor_id"].fillna("").astype(str).str.match(r"^C\d{8}$")
    if not committee_ids.any():
        return None
    return float((~receipts.loc[committee_ids, "committee_lookup_failed"]).mean())


def _calculated_totals(group: pd.DataFrame) -> dict[str, float | None]:
    ledger = group.loc[group["include_in_contribution_ledger"]]
    return {
        "individual_itemized_contributions": ledger.loc[
            ledger["record_class"].isin(["direct_individual_contribution", "partnership_or_llc_parent"]),
            "reported_receipt_amount",
        ].sum(min_count=1),
        "individual_unitemized_contributions": None,
        "political_party_committee_contributions": ledger.loc[
            ledger["record_class"] == "direct_party_contribution", "reported_receipt_amount"
        ].sum(min_count=1),
        "other_political_committee_contributions": ledger.loc[
            ledger["record_class"] == "direct_committee_contribution", "reported_receipt_amount"
        ].sum(min_count=1),
        "candidate_contribution": ledger.loc[
            ledger["record_class"] == "candidate_self_contribution", "reported_receipt_amount"
        ].sum(min_count=1),
    }


def _status(reported: float | None, calculated: float | None, comparable: bool) -> tuple[Any, Any, str]:
    if not comparable or reported is None or calculated is None or pd.isna(reported) or pd.isna(calculated):
        return None, None, "NOT_COMPARABLE"
    difference = float(calculated) - float(reported)
    percent = None if float(reported) == 0 else difference / abs(float(reported)) * 100
    absolute = abs(difference)
    if absolute <= 1:
        status = "PASS"
    elif absolute <= max(100, abs(float(reported)) * 0.01):
        status = "WARNING"
    else:
        status = "FAIL"
    return difference, percent, status


def build_validation_report(
    receipts: pd.DataFrame,
    committee_totals: dict[str, dict[str, Any] | None],
    *,
    full_cycle_date_range: bool,
    api_errors: dict[str, str] | None = None,
    candidate_committees: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    api_errors = api_errors or {}
    if candidate_committees is not None:
        identity = candidate_committees[["committee_id", "candidate_id"]].drop_duplicates().rename(
            columns={"committee_id": "recipient_committee_id"}
        )
    else:
        identity = receipts.groupby("recipient_committee_id", dropna=False).agg(
            candidate_id=("candidate_id", "first")
        ).reset_index()
    for mapping in identity.itertuples(index=False):
        committee_id = mapping.recipient_committee_id
        group = receipts.loc[receipts["recipient_committee_id"] == committee_id]
        calculated = _calculated_totals(group)
        totals = committee_totals.get(committee_id)
        if committee_id in api_errors:
            rows.append({
                "candidate_id": mapping.candidate_id,
                "committee_id": committee_id,
                "metric": "FEC_API_ERROR",
                "fec_reported_total": None,
                "calculated_total": None,
                "difference": None,
                "percent_difference": None,
                "status": "FAIL",
                "note": api_errors[committee_id],
            })
            continue
        for metric, api_field in SUMMARY_METRICS.items():
            reported = None if not totals else totals.get(api_field)
            value = calculated[metric]
            comparable = full_cycle_date_range and metric != "individual_unitemized_contributions"
            difference, percent, status = _status(reported, value, comparable)
            rows.append({
                "candidate_id": mapping.candidate_id,
                "committee_id": committee_id,
                "metric": metric,
                "fec_reported_total": reported,
                "calculated_total": value,
                "difference": difference,
                "percent_difference": percent,
                "status": status,
                "note": (
                    "unitemized contributions have no donor-level Schedule A rows"
                    if metric == "individual_unitemized_contributions"
                    else "custom date range is not comparable to cycle summary totals"
                    if not full_cycle_date_range
                    else ""
                ),
            })
    return pd.DataFrame(rows)
