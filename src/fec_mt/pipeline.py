from __future__ import annotations

import logging
import os
import subprocess
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from dotenv import find_dotenv, load_dotenv

from . import __version__
from .aggregate import (
    build_candidate_summary,
    build_contributions,
    build_donor_candidate_matrix,
    build_donor_summary,
    enrich_receipts,
)
from .bulk import load_bulk_data
from .candidates import assert_candidate_invariants, select_candidates
from .classify import classify_receipts, duplicate_transaction_id_diagnostic
from .committees import build_committee_lookup, link_candidate_committees
from .config import PipelineConfig
from .fec_api import FECAPIError, FECClient
from .normalize import normalize_schedule_a
from .output import write_all_outputs, write_csv, write_json, write_parquet
from .schedule_a import fetch_all_schedule_a
from .validate import (
    assert_recipient_mapping,
    build_validation_report,
    committee_resolution_rate,
    transaction_diagnostics,
)

LOGGER = logging.getLogger(__name__)


def _load_api_key() -> str | None:
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path, override=False)
    return os.environ.get("FEC_API_KEY")


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _fetch_totals(
    client: FECClient,
    committee_ids: list[str],
    cycle: int,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, str]]:
    totals: dict[str, dict[str, Any] | None] = {}
    errors: dict[str, str] = {}
    for committee_id in committee_ids:
        try:
            totals[committee_id] = client.fetch_committee_totals(committee_id, cycle)
        except FECAPIError as exc:
            LOGGER.error("Could not retrieve validation totals for %s: %s", committee_id, exc)
            errors[committee_id] = str(exc)
    return totals, errors


def run_pipeline(config: PipelineConfig, *, api_key: str | None = None) -> dict[str, Any]:
    config.create_directories()
    key = api_key or _load_api_key()
    if not key:
        raise ValueError("FEC_API_KEY is not set; add it to .env or the environment")

    candidate_master, candidate_url, candidate_path = load_bulk_data(
        "candidate_master", config.cycle, config.raw_dir, refresh=config.refresh
    )
    linkage, linkage_url, linkage_path = load_bulk_data(
        "candidate_committee_linkage", config.cycle, config.raw_dir, refresh=config.refresh
    )
    committee_master, committee_url, committee_path = load_bulk_data(
        "committee_master", config.cycle, config.raw_dir, refresh=config.refresh
    )

    candidates = select_candidates(
        candidate_master, state=config.state, offices=config.offices, cycle=config.cycle
    )
    assert_candidate_invariants(candidates, config.state, config.offices)
    committee_lookup = build_committee_lookup(committee_master)
    candidate_committees = link_candidate_committees(candidates, linkage, committee_lookup)
    if candidate_committees.empty:
        raise ValueError("candidate discovery produced no P/A committees")
    write_csv(candidates, config.intermediate_dir / "candidates.csv")
    write_csv(candidate_committees, config.intermediate_dir / "candidate_committees.csv")
    write_csv(committee_lookup, config.intermediate_dir / "committee_master.csv")
    LOGGER.info("Found %s %s federal candidates for cycle %s", len(candidates), config.state, config.cycle)
    LOGGER.info("Found %s P/A candidate committees", candidate_committees["committee_id"].nunique())
    candidates_without_committees = sorted(
        set(candidates["candidate_id"]) - set(candidate_committees["candidate_id"])
    )
    if candidates_without_committees:
        LOGGER.warning(
            "Candidates with no P/A committee in current FEC master/linkage data: %s",
            ", ".join(candidates_without_committees),
        )

    start_text = config.start_date.isoformat() if config.start_date else None
    end_text = config.end_date.isoformat() if config.end_date else None
    with FECClient(key) as client:
        records = fetch_all_schedule_a(
            client,
            candidate_committees,
            cycle=config.cycle,
            cache_dir=config.cache_dir,
            start_date=start_text,
            end_date=end_text,
            refresh=config.refresh,
        )
        raw = normalize_schedule_a(records)
        assert_recipient_mapping(raw, candidate_committees)
        # Materialize the auditable raw layer before any interpretive transform.
        write_parquet(raw, config.raw_dir / "schedule_a.parquet")
        classified = classify_receipts(raw, committee_lookup)
        receipts = enrich_receipts(classified, candidate_committees, committee_lookup)
        committee_ids = candidate_committees["committee_id"].drop_duplicates().tolist()
        totals, total_errors = _fetch_totals(client, committee_ids, config.cycle)

    contributions = build_contributions(receipts)
    donor_summary = build_donor_summary(contributions)
    candidate_summary = build_candidate_summary(receipts, candidates)
    matrix = build_donor_candidate_matrix(donor_summary)
    full_cycle = config.start_date == date(config.cycle - 1, 1, 1) and config.end_date is None
    validation = build_validation_report(
        receipts,
        totals,
        full_cycle_date_range=full_cycle,
        api_errors=total_errors,
        candidate_committees=candidate_committees,
    )
    duplicate_transactions = duplicate_transaction_id_diagnostic(raw)
    paths = write_all_outputs(
        raw_schedule_a=raw,
        receipts=receipts,
        contributions=contributions,
        donor_summary=donor_summary,
        candidate_summary=candidate_summary,
        donor_matrix=matrix,
        candidates=candidates,
        candidate_committees=candidate_committees,
        validation_report=validation,
        duplicate_transactions=duplicate_transactions,
        raw_dir=config.raw_dir,
        final_dir=config.final_dir,
    )

    unknown = receipts.loc[
        receipts["record_class"].eq("unknown")
        | (receipts["is_memo"] & receipts["memo_role"].eq("unknown"))
    ]
    diagnostics = transaction_diagnostics(raw)
    metadata = {
        "state": config.state,
        "cycle": config.cycle,
        "offices": list(config.offices),
        "start_date": start_text,
        "end_date": end_text,
        "fec_data_type": "processed",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "candidate_count": len(candidates),
        "committee_count": candidate_committees["committee_id"].nunique(),
        "schedule_a_record_count": len(raw),
        "donor_attribution_record_count": len(contributions),
        "unknown_record_count": len(unknown),
        "unknown_reported_amount": float(unknown["contribution_receipt_amount"].sum()) if not unknown.empty else 0.0,
        "duplicate_transaction_id_row_count": len(duplicate_transactions),
        "committee_contributor_resolution_rate": committee_resolution_rate(receipts),
        "transaction_diagnostics": diagnostics,
        "source_urls": {
            "candidate_master": candidate_url,
            "candidate_committee_linkage": linkage_url,
            "committee_master": committee_url,
            "schedule_a": "https://api.open.fec.gov/v1/schedules/schedule_a/",
            "committee_totals": "https://api.open.fec.gov/v1/committee/{committee_id}/totals/",
        },
        "source_files": {
            "candidate_master": candidate_path.name,
            "candidate_committee_linkage": linkage_path.name,
            "committee_master": committee_path.name,
        },
        "git_commit": _git_commit(),
        "software_version": __version__,
    }
    metadata_path = config.final_dir / "run_metadata.json"
    write_json(metadata, metadata_path)
    paths["metadata"] = metadata_path

    counts = receipts["record_class"].value_counts().to_dict()
    LOGGER.info("Retrieved %s Schedule A rows", len(raw))
    LOGGER.info("Classified records: %s", counts)
    LOGGER.warning(
        "Review required: %s unknown/uncertain memo records (signed amount %.2f), %s duplicate transaction-ID rows",
        len(unknown),
        metadata["unknown_reported_amount"],
        len(duplicate_transactions),
    )
    return {"metadata": metadata, "paths": paths, "classification_counts": counts}
