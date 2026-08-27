from fec_mt.aggregate import build_contributions, enrich_receipts
from fec_mt.classify import classify_receipts

from conftest import make_record


def test_direct_individual_pac_candidate_and_loan(normalized_records, committee_lookup):
    raw = normalized_records(
        make_record(transaction_id="IND", sub_id="1"),
        make_record(transaction_id="PAC", sub_id="2", line_number="F3-11C", contributor_id="C00222222", contributor_name="REPORTED PAC NAME", entity_type="PAC"),
        make_record(transaction_id="CAN", sub_id="3", line_number="F3-11D", contributor_name="CANDIDATE, TEST", entity_type="CAN", contribution_receipt_amount=-100),
        make_record(transaction_id="LOAN", sub_id="4", line_number="F3-13A", transaction_type="13", contribution_receipt_amount=5000),
    )
    classified = classify_receipts(raw, committee_lookup)
    by_id = classified.set_index("transaction_id")
    assert by_id.loc["IND", "record_class"] == "direct_individual_contribution"
    assert bool(by_id.loc["IND", "include_in_contribution_ledger"])
    assert bool(by_id.loc["IND", "include_in_donor_attribution"])
    assert by_id.loc["CAN", "record_class"] == "candidate_self_contribution"
    assert by_id.loc["CAN", "donor_attributed_amount"] == -100
    assert by_id.loc["LOAN", "record_class"] == "non_contribution_receipt"
    assert not bool(by_id.loc["LOAN", "include_in_donor_attribution"])

    candidate_committees = __import__("pandas").DataFrame([{
        "candidate_id": "H6MT01001", "candidate_name": "TEST", "candidate_party": "DEM",
        "candidate_office": "H", "candidate_district": "01", "committee_id": "C00111111",
        "committee_name": "MONTANA TEST CAMPAIGN", "committee_designation": "P",
    }])
    enriched = enrich_receipts(classified, candidate_committees, committee_lookup)
    pac = enriched.loc[enriched["transaction_id"] == "PAC"].iloc[0]
    candidate = enriched.loc[enriched["transaction_id"] == "CAN"].iloc[0]
    assert pac["donor_name_reported"] == "REPORTED PAC NAME"
    assert pac["donor_name_canonical"] == "EXAMPLE PAC"
    assert pac["donor_key"] == "FEC:C00222222"
    assert pac["donor_connected_organization"] == "EXAMPLE COMPANY"
    assert candidate["donor_type"] == "candidate"
    assert candidate["donor_key"].startswith("CAN:")
    assert len(build_contributions(enriched)) == 3


def test_identical_date_name_and_amount_are_not_deduplicated(normalized_records, committee_lookup):
    raw = normalized_records(
        make_record(transaction_id="A", sub_id="1"),
        make_record(transaction_id="B", sub_id="2"),
    )
    result = classify_receipts(raw, committee_lookup)
    assert len(result) == 2
    assert set(result["transaction_id"]) == {"A", "B"}


def test_live_api_fields_do_not_collide_with_enriched_columns(
    normalized_records, committee_lookup
):
    raw = normalized_records(make_record(
        contributor_id="C00222222",
        candidate_id="RAW-CANDIDATE-ID",
        candidate_name="RAW CANDIDATE NAME",
        candidate_office="RAW OFFICE",
        donor_committee_name="RAW DONOR COMMITTEE NAME",
        recipient_committee_designation="RAW DESIGNATION",
    ))
    candidate_committees = __import__("pandas").DataFrame([{
        "candidate_id": "H6MT01001", "candidate_name": "TEST", "candidate_party": "DEM",
        "candidate_office": "H", "candidate_district": "01", "committee_id": "C00111111",
        "committee_name": "MONTANA TEST CAMPAIGN", "committee_designation": "P",
    }])

    enriched = enrich_receipts(
        classify_receipts(raw, committee_lookup), candidate_committees, committee_lookup
    )
    row = enriched.iloc[0]

    assert row["candidate_id"] == "H6MT01001"
    assert row["candidate_name"] == "TEST"
    assert row["candidate_office"] == "H"
    assert row["recipient_committee_designation"] == "P"
    assert row["donor_committee_name"] == "EXAMPLE PAC"
    assert row["candidate_id_fec_api"] == "RAW-CANDIDATE-ID"
    assert row["donor_committee_name_fec_api"] == "RAW DONOR COMMITTEE NAME"
