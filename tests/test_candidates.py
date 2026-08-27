import pandas as pd

from fec_mt.candidates import assert_candidate_invariants, select_candidates
from fec_mt.committees import build_committee_lookup, link_candidate_committees


def test_candidate_filter_prefers_requested_cycle_without_dropping_active_candidates():
    master = pd.DataFrame([
        {"CAND_ID": "H6MT01001", "CAND_NAME": "OLD NAME", "CAND_PTY_AFFILIATION": "DEM", "CAND_ELECTION_YR": "2024", "CAND_OFFICE_ST": "MT", "CAND_OFFICE": "H", "CAND_OFFICE_DISTRICT": "01", "CAND_ICI": "C", "CAND_STATUS": "C", "CAND_PCC": "C00111111"},
        {"CAND_ID": "H6MT01001", "CAND_NAME": "CURRENT NAME", "CAND_PTY_AFFILIATION": "DEM", "CAND_ELECTION_YR": "2026", "CAND_OFFICE_ST": "MT", "CAND_OFFICE": "H", "CAND_OFFICE_DISTRICT": "01", "CAND_ICI": "C", "CAND_STATUS": "C", "CAND_PCC": "C00111111"},
        {"CAND_ID": "S8MT00002", "CAND_NAME": "ACTIVE FUTURE SENATOR", "CAND_PTY_AFFILIATION": "REP", "CAND_ELECTION_YR": "2028", "CAND_OFFICE_ST": "MT", "CAND_OFFICE": "S", "CAND_OFFICE_DISTRICT": "00", "CAND_ICI": "I", "CAND_STATUS": "C", "CAND_PCC": "C00999999"},
        {"CAND_ID": "S6MT00003", "CAND_NAME": "MISSING YEAR ACTIVE", "CAND_PTY_AFFILIATION": "IND", "CAND_ELECTION_YR": "", "CAND_OFFICE_ST": "MT", "CAND_OFFICE": "S", "CAND_OFFICE_DISTRICT": "00", "CAND_ICI": "C", "CAND_STATUS": "C", "CAND_PCC": "C00666666"},
        {"CAND_ID": "S6MT00004", "CAND_NAME": "CURRENT SENATOR", "CAND_PTY_AFFILIATION": "DEM", "CAND_ELECTION_YR": "2026", "CAND_OFFICE_ST": "MT", "CAND_OFFICE": "S", "CAND_OFFICE_DISTRICT": "00", "CAND_ICI": "C", "CAND_STATUS": "C", "CAND_PCC": "C00555555"},
        {"CAND_ID": "H6WY01003", "CAND_NAME": "WYOMING", "CAND_PTY_AFFILIATION": "REP", "CAND_ELECTION_YR": "2026", "CAND_OFFICE_ST": "WY", "CAND_OFFICE": "H", "CAND_OFFICE_DISTRICT": "01", "CAND_ICI": "C", "CAND_STATUS": "C", "CAND_PCC": "C00888888"},
        {"CAND_ID": "P60000004", "CAND_NAME": "PRESIDENT", "CAND_PTY_AFFILIATION": "IND", "CAND_ELECTION_YR": "2028", "CAND_OFFICE_ST": "MT", "CAND_OFFICE": "P", "CAND_OFFICE_DISTRICT": "00", "CAND_ICI": "O", "CAND_STATUS": "C", "CAND_PCC": "C00777777"},
    ])
    selected = select_candidates(master, state="MT", offices=("H", "S"), cycle=2026)
    assert_candidate_invariants(selected, "MT", ("H", "S"))
    assert selected["candidate_id"].tolist() == ["H6MT01001", "S6MT00003", "S6MT00004"]
    assert selected.loc[selected["candidate_id"] == "H6MT01001", "candidate_name"].item() == "CURRENT NAME"


def test_linkage_keeps_pa_and_deduplicates():
    candidates = pd.DataFrame([{
        "candidate_id": "H6MT01001", "candidate_name": "TEST", "party": "DEM",
        "election_year": "2026", "office": "H", "state": "MT", "district": "01",
        "incumbent_challenger_status": "C", "candidate_status": "C",
        "principal_committee_id": "C00111111",
    }])
    linkage = pd.DataFrame([
        {"CAND_ID": "H6MT01001", "CAND_ELECTION_YR": "2026", "FEC_ELECTION_YR": "2026", "CMTE_ID": "C00111111", "CMTE_TP": "H", "CMTE_DSGN": "P", "LINKAGE_ID": "1"},
        {"CAND_ID": "H6MT01001", "CAND_ELECTION_YR": "2026", "FEC_ELECTION_YR": "2026", "CMTE_ID": "C00111111", "CMTE_TP": "H", "CMTE_DSGN": "P", "LINKAGE_ID": "1"},
        {"CAND_ID": "H6MT01001", "CAND_ELECTION_YR": "2026", "FEC_ELECTION_YR": "2026", "CMTE_ID": "C00444444", "CMTE_TP": "H", "CMTE_DSGN": "A", "LINKAGE_ID": "2"},
        {"CAND_ID": "H6MT01001", "CAND_ELECTION_YR": "2026", "FEC_ELECTION_YR": "2026", "CMTE_ID": "C00333333", "CMTE_TP": "N", "CMTE_DSGN": "J", "LINKAGE_ID": "3"},
    ])
    cm = pd.DataFrame([
        {"CMTE_ID": cid, "CMTE_NM": cid, "CMTE_DSGN": dsgn, "CMTE_TP": "H", "CMTE_PTY_AFFILIATION": "", "ORG_TP": "", "CONNECTED_ORG_NM": "", "CAND_ID": "H6MT01001"}
        for cid, dsgn in [("C00111111", "P"), ("C00444444", "A"), ("C00333333", "J")]
    ])
    links = link_candidate_committees(candidates, linkage, build_committee_lookup(cm))
    assert links["committee_id"].tolist() == ["C00111111", "C00444444"]


def test_candidate_pcc_fallback_never_admits_leadership_pac():
    candidates = pd.DataFrame([{
        "candidate_id": "H4MT01041", "candidate_name": "TEST", "party": "REP",
        "election_year": "2026", "office": "H", "state": "MT", "district": "01",
        "incumbent_challenger_status": "I", "candidate_status": "C",
        "principal_committee_id": "C00778159",
    }])
    linkage = pd.DataFrame([{
        "CAND_ID": "H4MT01041", "CAND_ELECTION_YR": "2026", "FEC_ELECTION_YR": "2026",
        "CMTE_ID": "C00778159", "CMTE_TP": "Q", "CMTE_DSGN": "D", "LINKAGE_ID": "260463",
    }])
    committee_master = pd.DataFrame([{
        "CMTE_ID": "C00778159", "CMTE_NM": "LEADERSHIP FUND", "CMTE_DSGN": "D",
        "CMTE_TP": "Q", "CMTE_PTY_AFFILIATION": "REP", "ORG_TP": "",
        "CONNECTED_ORG_NM": "", "CAND_ID": "H4MT01041",
    }])
    links = link_candidate_committees(
        candidates, linkage, build_committee_lookup(committee_master)
    )
    assert links.empty
