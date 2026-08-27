from fec_mt.classify import classify_receipts, duplicate_transaction_id_diagnostic

from conftest import make_record


def test_processed_amended_report_fixture_contains_only_latest_disclosure(normalized_records, committee_lookup):
    """FLINT FOR MONTANA Q2 amendment (file 1995117), captured 2026-08-25.

    The processed API returned this latest A-version disclosure once; the superseded
    report row was absent and must not be recreated or added by this pipeline.
    """
    processed_api_rows = normalized_records(make_record(
        committee_id="C00941575",
        committee_name="FLINT FOR MONTANA",
        report_type="Q2",
        transaction_id="A507132CAE74C4D42973",
        sub_id="4080620261570353068",
        original_sub_id=None,
        file_number="1995117",
        amendment_indicator="A",
        line_number="12",
        filing_form="F3",
        contributor_name="GROW THE MAJORITY",
        entity_type="COM",
        contribution_receipt_amount=22802.15,
        contribution_receipt_date="2026-06-30",
    ))
    result = classify_receipts(processed_api_rows, committee_lookup)
    assert len(result) == 1
    assert result["reported_receipt_amount"].sum() == 22802.15
    assert result.loc[0, "file_number"] == "1995117"
    assert result.loc[0, "amendment_indicator"] == "A"


def test_duplicate_transaction_ids_are_diagnosed_not_blindly_deleted(normalized_records, committee_lookup):
    raw = normalized_records(
        make_record(transaction_id="DUP", sub_id="1", file_number="10", amendment_indicator="N"),
        make_record(transaction_id="DUP", sub_id="2", file_number="11", amendment_indicator="A"),
    )
    classified = classify_receipts(raw, committee_lookup)
    diagnostic = duplicate_transaction_id_diagnostic(classified)
    assert len(classified) == 2
    assert len(diagnostic) == 2
