from fec_mt.classify import classify_receipts

from conftest import make_record


def test_jfr_transfer_and_original_donor_are_separate_measures(normalized_records, committee_lookup):
    raw = normalized_records(
        make_record(
            transaction_id="JFR-TRANSFER", sub_id="1", line_number="F3-12",
            contributor_id="C00333333", contributor_name="VARIANT REPORTED NAME",
            entity_type="COM", contribution_receipt_amount=900,
        ),
        make_record(
            transaction_id="JFR-DONOR", sub_id="2", line_number="F3-12",
            contributor_name="DOE, JOHN", contribution_receipt_amount=1000,
            memo_code="X", memo_text="Original contributor share",
            back_reference_transaction_id="JFR-TRANSFER",
        ),
    )
    result = classify_receipts(raw, committee_lookup).set_index("transaction_id")
    transfer = result.loc["JFR-TRANSFER"]
    donor = result.loc["JFR-DONOR"]
    assert transfer["record_class"] == "joint_fundraising_transfer"
    assert not bool(transfer["include_in_contribution_ledger"])
    assert not bool(transfer["include_in_donor_attribution"])
    assert transfer["reported_receipt_amount"] == 900
    assert donor["record_class"] == "joint_fundraising_original_donor"
    assert not bool(donor["include_in_contribution_ledger"])
    assert bool(donor["include_in_donor_attribution"])
    assert donor["donor_attributed_amount"] == 1000
    assert donor["reported_receipt_amount"] != donor["reported_receipt_amount"]  # NaN


def test_partnership_parent_and_member_are_preserved_without_ledger_double_count(normalized_records, committee_lookup):
    raw = normalized_records(
        make_record(transaction_id="LLC-PARENT", sub_id="1", contributor_name="BIG SKY VENTURES LLC", entity_type="ORG", contribution_receipt_amount=1000),
        make_record(transaction_id="LLC-MEMBER", sub_id="2", contributor_name="MEMBER, MARIA", memo_code="X", memo_text="Attribution to member", back_reference_transaction_id="LLC-PARENT", contribution_receipt_amount=1000),
    )
    result = classify_receipts(raw, committee_lookup).set_index("transaction_id")
    assert result.loc["LLC-PARENT", "record_class"] == "partnership_or_llc_parent"
    assert bool(result.loc["LLC-PARENT", "include_in_contribution_ledger"])
    assert result.loc["LLC-MEMBER", "record_class"] == "partnership_or_llc_member_attribution"
    assert not bool(result.loc["LLC-MEMBER", "include_in_contribution_ledger"])
    assert result["reported_receipt_amount"].sum() == 1000

