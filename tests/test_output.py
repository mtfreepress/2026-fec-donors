import pandas as pd

from conftest import make_record
from fec_mt.aggregate import (
    build_candidate_summary,
    build_contributions,
    build_donor_candidate_matrix,
    build_donor_summary,
    enrich_receipts,
)
from fec_mt.classify import classify_receipts, duplicate_transaction_id_diagnostic
from fec_mt.output import write_all_outputs
from fec_mt.validate import build_validation_report


def test_auditable_outputs_serialize_and_keep_candidate_without_committee(
    tmp_path, normalized_records, committee_lookup
):
    candidates = pd.DataFrame([
        {"candidate_id": "H6MT01001", "candidate_name": "TEST", "party": "DEM", "office": "H", "district": "01"},
        {"candidate_id": "S6MT00002", "candidate_name": "NO COMMITTEE", "party": "IND", "office": "S", "district": "00"},
    ])
    links = pd.DataFrame([{
        "candidate_id": "H6MT01001", "candidate_name": "TEST", "candidate_party": "DEM",
        "candidate_office": "H", "candidate_district": "01", "committee_id": "C00111111",
        "committee_name": "MONTANA TEST CAMPAIGN", "committee_designation": "P",
        "committee_type": "H", "fec_election_year": "2026", "linkage_id": "1",
    }])
    raw = normalized_records(make_record())
    receipts = enrich_receipts(classify_receipts(raw, committee_lookup), links, committee_lookup)
    contributions = build_contributions(receipts)
    donor_summary = build_donor_summary(contributions)
    candidate_summary = build_candidate_summary(receipts, candidates)
    validation = build_validation_report(
        receipts,
        {"C00111111": None},
        full_cycle_date_range=True,
        candidate_committees=links,
    )
    paths = write_all_outputs(
        raw_schedule_a=raw,
        receipts=receipts,
        contributions=contributions,
        donor_summary=donor_summary,
        candidate_summary=candidate_summary,
        donor_matrix=build_donor_candidate_matrix(donor_summary),
        candidates=candidates,
        candidate_committees=links,
        validation_report=validation,
        duplicate_transactions=duplicate_transaction_id_diagnostic(raw),
        raw_dir=tmp_path / "raw",
        final_dir=tmp_path / "output",
    )
    assert len(pd.read_parquet(paths["raw_schedule_a"])) == 1
    assert len(pd.read_parquet(paths["receipts_classified"])) == 1
    assert len(pd.read_csv(paths["contributions_csv"])) == 1
    assert len(pd.read_csv(paths["candidates_committees"])) == 2
    assert len(candidate_summary) == 2
    empty_candidate = candidate_summary.loc[candidate_summary["candidate_id"] == "S6MT00002"].iloc[0]
    assert empty_candidate["itemized_donor_amount"] == 0
