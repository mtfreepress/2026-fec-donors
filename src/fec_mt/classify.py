from __future__ import annotations

import re
from typing import Any

import pandas as pd


DIRECT_LINES = {
    "F3-11AI": "direct_individual_contribution",
    "F3-11B": "direct_party_contribution",
    "F3-11C": "direct_committee_contribution",
    "F3-11D": "candidate_self_contribution",
}
PARTNERSHIP_PATTERN = re.compile(r"\b(LLC|L\.L\.C|LLP|L\.L\.P|LP|PARTNERSHIP|PARTNERS)\b", re.I)
JFR_PATTERN = re.compile(r"\b(JOINT FUNDRAIS|JFC\b|JFR\b)", re.I)


def _text(value: Any) -> str:
    if value is None or value is pd.NA or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return ""
    return str(value).strip()


def _line(value: Any) -> str:
    return _text(value).upper().replace(" ", "")


def _is_partnership_parent(entity_type: Any, name: Any) -> bool:
    entity = _text(entity_type).upper()
    return entity in {"ORG", "OTH"} and bool(PARTNERSHIP_PATTERN.search(_text(name)))


def _memo_role(memo_text: Any) -> str:
    text = _text(memo_text).upper()
    if "REATTRIBUT" in text:
        return "reattribution"
    if "REDESIGNAT" in text:
        return "redesignation"
    if any(token in text for token in ("PARTNER", "MEMBER", "ATTRIBUTION")):
        return "partnership_member"
    if any(token in text for token in ("INFORMATION", "MEMO ONLY", "NOT INCLUDED")):
        return "informational"
    return "unknown"


def classify_receipts(raw: pd.DataFrame, committee_lookup: pd.DataFrame) -> pd.DataFrame:
    """Classify without deleting rows or deduplicating FEC-reported transactions."""
    frame = raw.copy()
    if frame.empty:
        for column, dtype in {
            "record_class": "string", "include_in_contribution_ledger": "bool",
            "include_in_donor_attribution": "bool", "classification_reason": "string",
            "memo_role": "string", "reported_receipt_amount": "float64",
            "donor_attributed_amount": "float64", "member_attributed_amount": "float64",
        }.items():
            frame[column] = pd.Series(dtype=dtype)
        return frame

    committee_designations = committee_lookup.set_index("committee_id")["committee_designation"].to_dict()
    committee_names = committee_lookup.set_index("committee_id")["committee_name"].to_dict()

    parent_kind: dict[tuple[str, str], str] = {}
    for row in frame.itertuples(index=False):
        if bool(row.is_memo) or not _text(row.transaction_id):
            continue
        key = (_text(row.committee_id), _text(row.transaction_id))
        contributor_id = _text(row.contributor_id)
        designation = _text(committee_designations.get(contributor_id)).upper()
        contributor_name = _text(committee_names.get(contributor_id)) or _text(row.contributor_name)
        if _line(row.line_number) == "F3-12" and (
            designation == "J" or JFR_PATTERN.search(contributor_name)
        ):
            parent_kind[key] = "jfr"
        elif _line(row.line_number) == "F3-11AI" and _is_partnership_parent(row.entity_type, row.contributor_name):
            parent_kind[key] = "partnership"

    classes: list[str] = []
    ledger_flags: list[bool] = []
    donor_flags: list[bool] = []
    reasons: list[str] = []
    memo_roles: list[str] = []
    reported_amounts: list[float | None] = []
    attributed_amounts: list[float | None] = []
    member_amounts: list[float | None] = []

    for row in frame.itertuples(index=False):
        line = _line(row.line_number)
        memo = bool(row.is_memo)
        amount = row.contribution_receipt_amount
        amount_value = None if pd.isna(amount) else float(amount)
        contributor_id = _text(row.contributor_id)
        contributor_name = _text(committee_names.get(contributor_id)) or _text(row.contributor_name)
        designation = _text(committee_designations.get(contributor_id)).upper()
        parent = parent_kind.get((_text(row.committee_id), _text(row.back_reference_transaction_id)))

        record_class = "unknown"
        in_ledger = False
        in_donor = False
        reason = "unrecognized_line_and_structure"
        memo_role = "unknown" if memo else ""
        reported = None if memo else amount_value
        attributed = None
        member_amount = None

        if memo and parent == "jfr":
            record_class = "joint_fundraising_original_donor"
            in_donor = True
            reason = "memo_back_reference_to_recognized_jfr_transfer"
            memo_role = "joint_fundraising_original_donor"
            attributed = amount_value
        elif memo and parent == "partnership":
            record_class = "partnership_or_llc_member_attribution"
            in_donor = True
            reason = "memo_back_reference_to_partnership_or_llc_parent"
            memo_role = "partnership_member"
            attributed = amount_value
            member_amount = amount_value
        elif line == "F3-12" and not memo:
            if designation == "J":
                record_class = "joint_fundraising_transfer"
                reason = "line_12_contributor_committee_designation_j"
            elif JFR_PATTERN.search(contributor_name):
                record_class = "joint_fundraising_transfer"
                reason = "line_12_jfr_text_fallback"
            else:
                record_class = "authorized_committee_transfer"
                reason = "line_12_non_jfr_transfer"
        elif memo:
            inferred_role = _memo_role(row.memo_text)
            memo_role = inferred_role
            if inferred_role == "partnership_member" and line == "F3-11AI":
                record_class = "partnership_or_llc_member_attribution"
                in_donor = True
                reason = "line_11ai_partnership_member_text_heuristic"
                attributed = amount_value
                member_amount = amount_value
            else:
                record_class = "other_memo_attribution"
                reason = f"memo_role_{inferred_role}"
        elif line in DIRECT_LINES:
            record_class = DIRECT_LINES[line]
            if line == "F3-11AI" and _is_partnership_parent(row.entity_type, row.contributor_name):
                record_class = "partnership_or_llc_parent"
                reason = "line_11ai_organization_name_indicates_partnership_or_llc"
            else:
                reason = f"line_{line.lower().replace('-', '_')}"
            in_ledger = True
            in_donor = True
            attributed = amount_value
        elif line.startswith("F3-"):
            record_class = "non_contribution_receipt"
            reason = f"form_3_non_contribution_line_{line.lower().replace('-', '_')}"

        classes.append(record_class)
        ledger_flags.append(in_ledger)
        donor_flags.append(in_donor)
        reasons.append(reason)
        memo_roles.append(memo_role)
        reported_amounts.append(reported)
        attributed_amounts.append(attributed)
        member_amounts.append(member_amount)

    frame["record_class"] = classes
    frame["include_in_contribution_ledger"] = ledger_flags
    frame["include_in_donor_attribution"] = donor_flags
    frame["classification_reason"] = reasons
    frame["memo_role"] = memo_roles
    frame["reported_receipt_amount"] = reported_amounts
    frame["donor_attributed_amount"] = attributed_amounts
    frame["member_attributed_amount"] = member_amounts
    return frame


def duplicate_transaction_id_diagnostic(receipts: pd.DataFrame) -> pd.DataFrame:
    populated = receipts.loc[receipts["transaction_id"].fillna("").ne("")].copy()
    duplicate_mask = populated.duplicated(["committee_id", "transaction_id"], keep=False)
    columns = [
        "committee_id", "transaction_id", "sub_id", "original_sub_id", "file_number",
        "amendment_indicator", "contributor_name", "contribution_receipt_date",
        "contribution_receipt_amount",
    ]
    return populated.loc[duplicate_mask, columns].sort_values(["committee_id", "transaction_id"])
