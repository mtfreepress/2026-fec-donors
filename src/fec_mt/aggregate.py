from __future__ import annotations

from typing import Any

import pandas as pd

from .normalize import build_individual_donor_key, normalize_name, normalize_zip5


ENTITY_DONOR_TYPES = {
    "IND": "individual",
    "PAC": "pac_or_committee",
    "COM": "pac_or_committee",
    "CCM": "pac_or_committee",
    "PTY": "party",
    "CAN": "candidate",
    "ORG": "organization",
}

CONTRIBUTION_COLUMNS = [
    "candidate_id", "candidate_name", "candidate_party", "candidate_office",
    "candidate_district", "recipient_committee_id", "recipient_committee_name",
    "recipient_committee_designation", "donor_key", "donor_name_reported",
    "donor_name_canonical", "donor_type", "donor_fec_id", "donor_city", "donor_state",
    "donor_zip", "donor_zip5", "donor_employer", "donor_occupation", "amount", "date",
    "election_type", "fec_election_year", "record_class", "is_memo", "memo_role",
    "memo_text", "transaction_type", "line_number", "transaction_id",
    "back_reference_transaction_id", "sub_id", "original_sub_id", "file_number",
    "image_number", "donor_identity_method", "donor_connected_organization",
    "donor_committee_type", "donor_committee_designation", "donor_party",
    "committee_lookup_failed", "source",
]


def _text(value: Any) -> str:
    if value is None or value is pd.NA or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return ""
    return str(value).strip()


def enrich_receipts(
    receipts: pd.DataFrame,
    candidate_committees: pd.DataFrame,
    committee_lookup: pd.DataFrame,
) -> pd.DataFrame:
    recipient = candidate_committees.rename(columns={
        "committee_id": "recipient_committee_id",
        "committee_name": "recipient_committee_name",
        "committee_designation": "recipient_committee_designation",
    })[[
        "candidate_id", "candidate_name", "candidate_party", "candidate_office",
        "candidate_district", "recipient_committee_id", "recipient_committee_name",
        "recipient_committee_designation",
    ]]
    frame = receipts.rename(columns={"committee_id": "recipient_committee_id", "committee_name": "reported_recipient_committee_name"})
    frame = frame.merge(
        recipient,
        on="recipient_committee_id",
        how="left",
        validate="many_to_many",
        suffixes=("_fec_api", ""),
    )
    frame["recipient_committee_name"] = frame["recipient_committee_name"].fillna(frame["reported_recipient_committee_name"])

    donor_lookup = committee_lookup.rename(columns={
        "committee_id": "donor_committee_id",
        "committee_name": "donor_committee_name",
        "committee_designation": "donor_committee_designation",
        "committee_type": "donor_committee_type",
        "committee_party": "donor_party",
        "connected_organization_name": "donor_connected_organization",
        "candidate_id": "donor_committee_candidate_id",
    })
    frame = frame.merge(
        donor_lookup,
        left_on="contributor_id",
        right_on="donor_committee_id",
        how="left",
        validate="many_to_one",
        suffixes=("_fec_api", ""),
    )
    frame["donor_name_reported"] = frame["contributor_name"]
    frame["donor_name_canonical"] = frame["donor_committee_name"].fillna(frame["contributor_name"])
    frame["donor_fec_id"] = frame["contributor_id"]
    frame["committee_lookup_failed"] = (
        frame["contributor_id"].fillna("").astype(str).str.match(r"^C\d{8}$")
        & frame["donor_committee_id"].isna()
    )

    donor_types: list[str] = []
    donor_keys: list[str] = []
    identity_methods: list[str] = []
    normalized_names: list[str] = []
    zip5s: list[str] = []
    for row in frame.itertuples(index=False):
        entity = _text(row.entity_type).upper()
        donor_type = ENTITY_DONOR_TYPES.get(entity, "unknown")
        if _text(row.donor_committee_id):
            donor_type = "party" if _text(row.donor_committee_designation).upper() == "J" and entity == "PTY" else "pac_or_committee"
        if row.record_class == "direct_party_contribution":
            donor_type = "party"
        elif row.record_class == "candidate_self_contribution":
            donor_type = "candidate"
        elif row.record_class in {"partnership_or_llc_parent", "partnership_or_llc_member_attribution"}:
            donor_type = "partnership_or_llc" if row.record_class.endswith("parent") else donor_type

        normalized = normalize_name(row.donor_name_canonical)
        zip5 = normalize_zip5(row.contributor_zip)
        fec_id = _text(row.donor_fec_id)
        if fec_id.startswith("C"):
            donor_key = f"FEC:{fec_id}"
            method = "fec_committee_id"
        elif donor_type == "individual":
            donor_key, method = build_individual_donor_key(
                row.donor_name_canonical, row.contributor_zip, row.contributor_city, row.contributor_state
            )
        else:
            prefix = {
                "candidate": "CAN", "organization": "ORG", "party": "PTY",
                "pac_or_committee": "COM", "partnership_or_llc": "LLC",
            }.get(donor_type, "UNK")
            location = zip5 or f"{normalize_name(row.contributor_city)}|{normalize_name(row.contributor_state)}"
            donor_key = f"{prefix}:{normalized}|{location}"
            method = f"{donor_type}_name_location"
        donor_types.append(donor_type)
        donor_keys.append(donor_key)
        identity_methods.append(method)
        normalized_names.append(normalized)
        zip5s.append(zip5)

    frame["donor_type"] = donor_types
    frame["donor_key"] = donor_keys
    frame["donor_identity_method"] = identity_methods
    frame["donor_name_normalized"] = normalized_names
    frame["donor_zip5"] = zip5s
    return frame


def build_contributions(receipts: pd.DataFrame) -> pd.DataFrame:
    selected = receipts.loc[receipts["include_in_donor_attribution"]].copy()
    selected = selected.rename(columns={
        "contributor_city": "donor_city",
        "contributor_state": "donor_state",
        "contributor_zip": "donor_zip",
        "contributor_employer": "donor_employer",
        "contributor_occupation": "donor_occupation",
        "donor_attributed_amount": "amount",
        "contribution_receipt_date": "date",
    })
    selected["source"] = "FEC Schedule A"
    for column in CONTRIBUTION_COLUMNS:
        if column not in selected:
            selected[column] = pd.NA
    return selected[CONTRIBUTION_COLUMNS].reset_index(drop=True)


def build_donor_summary(contributions: pd.DataFrame) -> pd.DataFrame:
    output_columns = [
        "candidate_id", "candidate_name", "candidate_party", "candidate_office",
        "candidate_district", "donor_key", "donor_name", "donor_type", "donor_fec_id",
        "donor_city", "donor_state", "donor_zip5", "donor_employer", "donor_occupation",
        "total_amount", "transaction_count", "first_contribution_date", "latest_contribution_date",
        "donor_connected_organization", "donor_committee_type", "donor_party",
    ]
    if contributions.empty:
        return pd.DataFrame(columns=output_columns)
    grouped = contributions.groupby(["candidate_id", "donor_key"], dropna=False, sort=True)
    summary = grouped.agg(
        candidate_name=("candidate_name", "first"),
        candidate_party=("candidate_party", "first"),
        candidate_office=("candidate_office", "first"),
        candidate_district=("candidate_district", "first"),
        donor_name=("donor_name_canonical", "first"),
        donor_type=("donor_type", "first"),
        donor_fec_id=("donor_fec_id", "first"),
        donor_city=("donor_city", "first"),
        donor_state=("donor_state", "first"),
        donor_zip5=("donor_zip5", "first"),
        donor_employer=("donor_employer", "first"),
        donor_occupation=("donor_occupation", "first"),
        total_amount=("amount", "sum"),
        transaction_count=("amount", "size"),
        first_contribution_date=("date", "min"),
        latest_contribution_date=("date", "max"),
        donor_connected_organization=("donor_connected_organization", "first"),
        donor_committee_type=("donor_committee_type", "first"),
        donor_party=("donor_party", "first"),
    ).reset_index()
    return summary[output_columns]


def build_candidate_summary(receipts: pd.DataFrame, candidates: pd.DataFrame | None = None) -> pd.DataFrame:
    output_columns = [
        "candidate_id", "candidate_name", "party", "office", "district",
        "itemized_donor_amount", "individual_amount", "committee_pac_amount", "party_amount",
        "candidate_self_amount", "unique_donor_keys", "individual_donor_keys",
        "committee_donor_keys", "earliest_transaction", "latest_transaction",
        "joint_fundraising_gross_attributed", "joint_fundraising_net_transfers",
    ]
    rows: list[dict[str, Any]] = []
    for candidate_id, group in receipts.groupby("candidate_id", dropna=False):
        ledger = group.loc[group["include_in_contribution_ledger"]]
        donor = group.loc[group["include_in_donor_attribution"]]
        direct_for_totals = ledger.loc[ledger["record_class"] != "partnership_or_llc_member_attribution"]
        rows.append({
            "candidate_id": candidate_id,
            "candidate_name": group["candidate_name"].iloc[0],
            "party": group["candidate_party"].iloc[0],
            "office": group["candidate_office"].iloc[0],
            "district": group["candidate_district"].iloc[0],
            "itemized_donor_amount": direct_for_totals["reported_receipt_amount"].sum(min_count=1),
            "individual_amount": ledger.loc[ledger["record_class"].isin(["direct_individual_contribution", "partnership_or_llc_parent"]), "reported_receipt_amount"].sum(min_count=1),
            "committee_pac_amount": ledger.loc[ledger["record_class"] == "direct_committee_contribution", "reported_receipt_amount"].sum(min_count=1),
            "party_amount": ledger.loc[ledger["record_class"] == "direct_party_contribution", "reported_receipt_amount"].sum(min_count=1),
            "candidate_self_amount": ledger.loc[ledger["record_class"] == "candidate_self_contribution", "reported_receipt_amount"].sum(min_count=1),
            "unique_donor_keys": donor["donor_key"].nunique(),
            "individual_donor_keys": donor.loc[donor["donor_type"] == "individual", "donor_key"].nunique(),
            "committee_donor_keys": donor.loc[donor["donor_type"].isin(["pac_or_committee", "party"]), "donor_key"].nunique(),
            "earliest_transaction": group["contribution_receipt_date"].min(),
            "latest_transaction": group["contribution_receipt_date"].max(),
            "joint_fundraising_gross_attributed": group.loc[group["record_class"] == "joint_fundraising_original_donor", "donor_attributed_amount"].sum(min_count=1),
            "joint_fundraising_net_transfers": group.loc[group["record_class"] == "joint_fundraising_transfer", "reported_receipt_amount"].sum(min_count=1),
        })
    summary = pd.DataFrame(rows, columns=output_columns)
    if candidates is None:
        return summary
    universe = candidates.rename(columns={
        "party": "party", "office": "office", "district": "district"
    })[["candidate_id", "candidate_name", "party", "office", "district"]]
    metrics = [column for column in output_columns if column not in universe.columns]
    if summary.empty:
        summary = universe.copy()
        for column in metrics:
            summary[column] = pd.NA
    else:
        summary = universe.merge(
            summary.drop(columns=["candidate_name", "party", "office", "district"]),
            on="candidate_id",
            how="left",
            validate="one_to_one",
        )
    zero_columns = [
        "itemized_donor_amount", "individual_amount", "committee_pac_amount", "party_amount",
        "candidate_self_amount", "unique_donor_keys", "individual_donor_keys",
        "committee_donor_keys", "joint_fundraising_gross_attributed", "joint_fundraising_net_transfers",
    ]
    summary[zero_columns] = summary[zero_columns].fillna(0)
    return summary[output_columns]


def build_donor_candidate_matrix(donor_summary: pd.DataFrame) -> pd.DataFrame:
    if donor_summary.empty:
        return pd.DataFrame(columns=["donor_key", "donor_name"])
    pivot = donor_summary.pivot_table(
        index=["donor_key", "donor_name"],
        columns="candidate_name",
        values="total_amount",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    pivot.columns.name = None
    return pivot
