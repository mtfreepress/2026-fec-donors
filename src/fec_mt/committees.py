from __future__ import annotations

import pandas as pd


COMMITTEE_LOOKUP_COLUMNS = [
    "committee_id", "committee_name", "committee_designation", "committee_type",
    "committee_party", "organization_type", "connected_organization_name", "candidate_id",
]


def build_committee_lookup(committee_master: pd.DataFrame) -> pd.DataFrame:
    lookup = committee_master.rename(columns={
        "CMTE_ID": "committee_id",
        "CMTE_NM": "committee_name",
        "CMTE_DSGN": "committee_designation",
        "CMTE_TP": "committee_type",
        "CMTE_PTY_AFFILIATION": "committee_party",
        "ORG_TP": "organization_type",
        "CONNECTED_ORG_NM": "connected_organization_name",
        "CAND_ID": "candidate_id",
    })[COMMITTEE_LOOKUP_COLUMNS].copy()
    return lookup.drop_duplicates("committee_id", keep="last").reset_index(drop=True)


def link_candidate_committees(
    candidates: pd.DataFrame,
    linkage: pd.DataFrame,
    committee_lookup: pd.DataFrame,
) -> pd.DataFrame:
    links = linkage.loc[
        linkage["CAND_ID"].isin(candidates["candidate_id"])
        & linkage["CMTE_DSGN"].isin(["P", "A"])
    ].copy()
    links = links.rename(columns={
        "CAND_ID": "candidate_id",
        "FEC_ELECTION_YR": "fec_election_year",
        "CMTE_ID": "committee_id",
        "CMTE_TP": "committee_type",
        "CMTE_DSGN": "committee_designation",
        "LINKAGE_ID": "linkage_id",
    })
    candidate_fields = candidates.rename(columns={
        "candidate_name": "candidate_name",
        "party": "candidate_party",
        "office": "candidate_office",
        "district": "candidate_district",
    })[["candidate_id", "candidate_name", "candidate_party", "candidate_office", "candidate_district"]]
    links = links.merge(candidate_fields, on="candidate_id", how="left", validate="many_to_one")

    # CAND_PCC is a documented principal committee and is retained if a linkage row is
    # unexpectedly absent, while linkage remains the source for all other committees.
    linked_pairs = set(zip(links["candidate_id"], links["committee_id"], strict=False))
    lookup_by_id = committee_lookup.set_index("committee_id").to_dict("index")
    fallback_rows = []
    for row in candidates.itertuples(index=False):
        master = lookup_by_id.get(row.principal_committee_id, {})
        master_designation = master.get("committee_designation")
        if (
            row.principal_committee_id
            and master_designation in {"P", "A"}
            and (row.candidate_id, row.principal_committee_id) not in linked_pairs
        ):
            fallback_rows.append({
                "candidate_id": row.candidate_id,
                "fec_election_year": row.election_year,
                "committee_id": row.principal_committee_id,
                "committee_type": master.get("committee_type", ""),
                "committee_designation": master_designation,
                "linkage_id": "CAND_PCC_FALLBACK",
                "candidate_name": row.candidate_name,
                "candidate_party": row.party,
                "candidate_office": row.office,
                "candidate_district": row.district,
            })
    if fallback_rows:
        links = pd.concat([links, pd.DataFrame(fallback_rows)], ignore_index=True)

    enrich = committee_lookup[["committee_id", "committee_name", "committee_designation", "committee_type"]]
    links = links.merge(enrich, on="committee_id", how="left", suffixes=("", "_master"), validate="many_to_one")
    links["committee_designation"] = links["committee_designation"].replace("", pd.NA).fillna(links["committee_designation_master"])
    links["committee_type"] = links["committee_type"].replace("", pd.NA).fillna(links["committee_type_master"])
    links = links.drop(columns=["committee_designation_master", "committee_type_master"])
    columns = [
        "candidate_id", "candidate_name", "candidate_party", "candidate_office",
        "candidate_district", "committee_id", "committee_name", "committee_designation",
        "committee_type", "fec_election_year", "linkage_id",
    ]
    return links[columns].drop_duplicates(["candidate_id", "committee_id"]).reset_index(drop=True)
