from fec_mt.normalize import build_individual_donor_key, normalize_name, normalize_schedule_a, normalize_zip5
from fec_mt.classify import classify_receipts
import pandas as pd


def test_conservative_identity_normalization():
    assert normalize_name("  Smith,   John A. ") == "SMITH JOHN A"
    assert normalize_zip5("59601-1234") == "59601"
    assert build_individual_donor_key("Smith, John", "59601-1234", "", "") == (
        "IND:SMITH JOHN|59601", "name_zip"
    )
    assert build_individual_donor_key("Smith, John", "", "Helena", "mt") == (
        "IND:SMITH JOHN|HELENA|MT", "name_city_state"
    )


def test_ids_remain_strings_and_signed_amount_is_preserved():
    frame = normalize_schedule_a([{
        "committee_id": "C00000001", "sub_id": 401, "file_number": 12.0,
        "contribution_receipt_amount": -25, "contribution_receipt_date": "2026-01-01",
    }])
    assert frame.loc[0, "sub_id"] == "401"
    assert frame.loc[0, "file_number"] == "12"
    assert frame.loc[0, "contribution_receipt_amount"] == -25


def test_false_boolean_memo_code_is_not_a_memo():
    frame = normalize_schedule_a([{"committee_id": "C00000001", "memo_code": False}])
    assert not bool(frame.loc[0, "is_memo"])


def test_live_api_style_raw_form3_line_is_canonicalized_and_original_retained():
    frame = normalize_schedule_a([{
        "committee_id": "C00000001", "filing_form": "F3", "line_number": "11A(I)",
        "contributor_name": "DOE, JANE", "entity_type": "IND",
        "contribution_receipt_amount": 250, "transaction_id": "A",
    }])
    assert frame.loc[0, "line_number_original"] == "11A(I)"
    assert frame.loc[0, "line_number"] == "F3-11AI"
    empty_lookup = pd.DataFrame(columns=[
        "committee_id", "committee_name", "committee_designation", "committee_type",
        "committee_party", "organization_type", "connected_organization_name", "candidate_id",
    ])
    assert classify_receipts(frame, empty_lookup).loc[0, "record_class"] == "direct_individual_contribution"
