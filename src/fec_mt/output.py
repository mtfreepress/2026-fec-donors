from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, engine="pyarrow")


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_all_outputs(
    *,
    raw_schedule_a: pd.DataFrame,
    receipts: pd.DataFrame,
    contributions: pd.DataFrame,
    donor_summary: pd.DataFrame,
    candidate_summary: pd.DataFrame,
    donor_matrix: pd.DataFrame,
    candidates: pd.DataFrame,
    candidate_committees: pd.DataFrame,
    validation_report: pd.DataFrame,
    duplicate_transactions: pd.DataFrame,
    raw_dir: Path,
    final_dir: Path,
) -> dict[str, Path]:
    paths = {
        "raw_schedule_a": raw_dir / "schedule_a.parquet",
        "contributions_csv": final_dir / "contributions.csv",
        "contributions_parquet": final_dir / "contributions.parquet",
        "receipts_classified": final_dir / "receipts_classified.parquet",
        "donor_summary": final_dir / "donor_summary.csv",
        "candidate_summary": final_dir / "candidate_summary.csv",
        "donor_matrix": final_dir / "donor_candidate_matrix.csv",
        "candidates_committees": final_dir / "candidates_and_committees.csv",
        "unclassified": final_dir / "unclassified_receipts.csv",
        "validation": final_dir / "validation_report.csv",
        "duplicate_transactions": final_dir / "duplicate_transaction_ids.csv",
    }
    write_parquet(raw_schedule_a, paths["raw_schedule_a"])
    write_csv(contributions, paths["contributions_csv"])
    write_parquet(contributions, paths["contributions_parquet"])
    write_parquet(receipts, paths["receipts_classified"])
    write_csv(donor_summary, paths["donor_summary"])
    write_csv(candidate_summary, paths["candidate_summary"])
    write_csv(donor_matrix, paths["donor_matrix"])
    candidate_base = candidates[["candidate_id", "candidate_name", "party", "office", "district"]]
    committee_fields = candidate_committees[[
        "candidate_id", "committee_name", "committee_id", "committee_designation", "committee_type"
    ]]
    diagnostics = candidate_base.merge(committee_fields, on="candidate_id", how="left", validate="one_to_many")[[
        "candidate_name", "candidate_id", "party", "office", "district",
        "committee_name", "committee_id", "committee_designation", "committee_type",
    ]]
    write_csv(diagnostics, paths["candidates_committees"])
    unknown = receipts.loc[
        receipts["record_class"].eq("unknown")
        | (receipts["is_memo"] & receipts["memo_role"].eq("unknown"))
    ]
    write_csv(unknown, paths["unclassified"])
    write_csv(validation_report, paths["validation"])
    write_csv(duplicate_transactions, paths["duplicate_transactions"])
    return paths
