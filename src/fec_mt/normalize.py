from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import pandas as pd


STABLE_SCHEDULE_A_COLUMNS = [
    "committee_id", "committee_name",
    "contributor_id", "contributor_name", "contributor_first_name",
    "contributor_middle_name", "contributor_last_name", "contributor_prefix",
    "contributor_suffix", "contributor_city", "contributor_state", "contributor_zip",
    "contributor_employer", "contributor_occupation", "entity_type", "entity_type_desc",
    "contribution_receipt_date", "contribution_receipt_amount", "contribution_aggregate",
    "election_type", "fec_election_year", "line_number", "line_number_original", "transaction_type",
    "transaction_type_desc", "memo_code", "memo_text", "transaction_id",
    "back_reference_transaction_id", "back_reference_schedule_name", "file_number",
    "image_number", "sub_id", "original_sub_id", "amendment_indicator", "report_type",
    "filing_form",
]

ALIASES = {
    "committee_name": ("committee_name", "committee.name"),
    "entity_type_desc": ("entity_type_desc", "entity_type_description"),
    "line_number": ("line_number",),
    "filing_form": ("filing_form", "form_type"),
}
ID_COLUMNS = [
    "committee_id", "contributor_id", "transaction_id", "back_reference_transaction_id",
    "file_number", "image_number", "sub_id", "original_sub_id",
]


def _nested_value(record: dict[str, Any], dotted: str) -> Any:
    current: Any = record
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _first_value(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = _nested_value(record, name)
        if value is not None:
            return value
    return None


def _safe_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value


def _id_string(value: Any) -> str | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _memo_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return str(value).strip().upper() not in {"", "0", "N", "NO", "FALSE"}


def canonical_line_number(line_number: Any, filing_form: Any) -> str:
    if line_number is None or pd.isna(line_number):
        return ""
    line = re.sub(r"[\s()]", "", str(line_number).upper())
    if line.startswith("F"):
        return line
    form = "" if filing_form is None or pd.isna(filing_form) else str(filing_form).upper().strip()
    if form.startswith("F3"):
        return f"F3-{line}"
    return line


def normalize_schedule_a(records: list[dict[str, Any]]) -> pd.DataFrame:
    normalized: list[dict[str, Any]] = []
    for source in records:
        row = {key: _safe_cell(value) for key, value in source.items()}
        for column in STABLE_SCHEDULE_A_COLUMNS:
            aliases = ALIASES.get(column, (column,))
            row[column] = _safe_cell(_first_value(source, aliases))
        normalized.append(row)
    frame = pd.DataFrame(normalized)
    for column in STABLE_SCHEDULE_A_COLUMNS:
        if column not in frame:
            frame[column] = pd.NA
    for column in ID_COLUMNS:
        frame[column] = frame[column].map(_id_string).astype("string")
    frame["line_number_original"] = frame["line_number"]
    frame["line_number"] = [
        canonical_line_number(line, form)
        for line, form in zip(frame["line_number_original"], frame["filing_form"], strict=False)
    ]
    frame["contribution_receipt_amount"] = pd.to_numeric(frame["contribution_receipt_amount"], errors="coerce")
    frame["contribution_aggregate"] = pd.to_numeric(frame["contribution_aggregate"], errors="coerce")
    frame["contribution_receipt_date"] = pd.to_datetime(
        frame["contribution_receipt_date"], errors="coerce", utc=True
    )
    frame["is_memo"] = frame["memo_code"].map(_memo_flag)
    return frame[[*STABLE_SCHEDULE_A_COLUMNS, "is_memo", *[c for c in frame.columns if c not in STABLE_SCHEDULE_A_COLUMNS and c != "is_memo"]]]


def normalize_name(value: Any) -> str:
    if value is None or value is pd.NA or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).upper().strip()
    text = re.sub(r"[.,;:]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_zip5(value: Any) -> str:
    if value is None or value is pd.NA or (not isinstance(value, (dict, list)) and pd.isna(value)):
        return ""
    match = re.search(r"\d{5}", str(value))
    return match.group(0) if match else ""


def build_individual_donor_key(name: Any, zipcode: Any, city: Any, state: Any) -> tuple[str, str]:
    normalized = normalize_name(name)
    zip5 = normalize_zip5(zipcode)
    if zip5:
        return f"IND:{normalized}|{zip5}", "name_zip"
    return f"IND:{normalized}|{normalize_name(city)}|{normalize_name(state)}", "name_city_state"
