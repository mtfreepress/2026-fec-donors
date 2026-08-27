from __future__ import annotations

import pandas as pd
import pytest

from fec_mt.normalize import normalize_schedule_a


@pytest.fixture
def committee_lookup() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "committee_id": "C00111111",
            "committee_name": "MONTANA TEST CAMPAIGN",
            "committee_designation": "P",
            "committee_type": "H",
            "committee_party": "DEM",
            "organization_type": "",
            "connected_organization_name": "",
            "candidate_id": "H6MT01001",
        },
        {
            "committee_id": "C00222222",
            "committee_name": "EXAMPLE PAC",
            "committee_designation": "U",
            "committee_type": "Q",
            "committee_party": "",
            "organization_type": "C",
            "connected_organization_name": "EXAMPLE COMPANY",
            "candidate_id": "",
        },
        {
            "committee_id": "C00333333",
            "committee_name": "MONTANA VICTORY JOINT FUNDRAISING COMMITTEE",
            "committee_designation": "J",
            "committee_type": "N",
            "committee_party": "",
            "organization_type": "",
            "connected_organization_name": "",
            "candidate_id": "",
        },
    ])


def make_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "committee_id": "C00111111",
        "committee_name": "MONTANA TEST CAMPAIGN",
        "contributor_id": None,
        "contributor_name": "DOE, JANE",
        "contributor_city": "HELENA",
        "contributor_state": "MT",
        "contributor_zip": "59601-1234",
        "contributor_employer": "SELF",
        "contributor_occupation": "WRITER",
        "entity_type": "IND",
        "contribution_receipt_date": "2026-02-03T12:00:00",
        "contribution_receipt_amount": 250.0,
        "election_type": "P2026",
        "fec_election_year": 2026,
        "line_number": "F3-11AI",
        "transaction_type": "15",
        "memo_code": None,
        "memo_text": None,
        "transaction_id": "A-1",
        "back_reference_transaction_id": None,
        "sub_id": "401012026000000001",
        "original_sub_id": "401012026000000001",
        "file_number": "1900001",
        "image_number": "202601019999999999",
        "amendment_indicator": "N",
        "filing_form": "F3",
    }
    record.update(overrides)
    return record


@pytest.fixture
def normalized_records():
    def factory(*records: dict[str, object]) -> pd.DataFrame:
        return normalize_schedule_a(list(records))
    return factory

