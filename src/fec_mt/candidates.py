from __future__ import annotations

import pandas as pd


CANDIDATE_OUTPUT_COLUMNS = [
    "candidate_id", "candidate_name", "party", "election_year", "office",
    "state", "district", "incumbent_challenger_status", "candidate_status",
    "principal_committee_id",
]


def select_candidates(
    candidate_master: pd.DataFrame,
    *,
    state: str,
    offices: tuple[str, ...],
    cycle: int,
) -> pd.DataFrame:
    """Select the requested-cycle universe without admitting stale prior campaigns.

    Candidate Master contains historical/future candidates with active committees. Exact
    election-year matches are therefore primary. Active rows with a missing election year
    are retained, and an office-wide active fallback is used only if the file has no exact
    cycle records for that requested office.
    """
    selected = candidate_master.loc[
        candidate_master["CAND_OFFICE_ST"].str.upper().eq(state.upper())
        & candidate_master["CAND_OFFICE"].str.upper().isin(offices)
    ].copy()
    election_year = selected["CAND_ELECTION_YR"].fillna("").str.strip()
    active = selected["CAND_STATUS"].isin(["C", "F"])
    keep = pd.Series(False, index=selected.index)
    for office in offices:
        office_rows = selected["CAND_OFFICE"].eq(office)
        exact = office_rows & election_year.eq(str(cycle))
        if exact.any():
            keep |= exact | (office_rows & election_year.eq("") & active)
        else:
            keep |= office_rows & active
    selected = selected.loc[keep].copy()
    if state.upper() == "MT" and "H" in offices:
        selected = selected.loc[
            selected["CAND_OFFICE"].ne("H")
            | selected["CAND_OFFICE_DISTRICT"].isin(["01", "02"])
        ].copy()
    selected["_cycle_match"] = selected["CAND_ELECTION_YR"].eq(str(cycle))
    selected["_active_rank"] = selected["CAND_STATUS"].map({"C": 3, "F": 2, "N": 1, "P": 0}).fillna(-1)
    selected = selected.sort_values(
        ["CAND_ID", "_cycle_match", "_active_rank"], ascending=[True, False, False]
    ).drop_duplicates("CAND_ID", keep="first")
    selected = selected.rename(columns={
        "CAND_ID": "candidate_id",
        "CAND_NAME": "candidate_name",
        "CAND_PTY_AFFILIATION": "party",
        "CAND_ELECTION_YR": "election_year",
        "CAND_OFFICE": "office",
        "CAND_OFFICE_ST": "state",
        "CAND_OFFICE_DISTRICT": "district",
        "CAND_ICI": "incumbent_challenger_status",
        "CAND_STATUS": "candidate_status",
        "CAND_PCC": "principal_committee_id",
    })
    return selected[CANDIDATE_OUTPUT_COLUMNS].reset_index(drop=True)


def assert_candidate_invariants(candidates: pd.DataFrame, state: str, offices: tuple[str, ...]) -> None:
    if not candidates["state"].eq(state).all():
        raise ValueError(f"candidate discovery returned a candidate outside {state}")
    if not candidates["office"].isin(offices).all():
        raise ValueError("candidate discovery returned an unrequested office")
    if candidates["candidate_id"].duplicated().any():
        raise ValueError("candidate master output contains duplicate candidate IDs")
