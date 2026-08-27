# Montana federal candidate contributions

This project builds a reproducible, auditable dataset of identifiable donors to Montana U.S. House and U.S. Senate candidates. Candidate discovery comes from FEC Candidate Master, P/A committee relationships from the candidate–committee linkage file, committee identities from Committee Master, and transactions from each recipient committee's processed Schedule A API disclosures.

Defaults are Montana (`MT`), the 2025–2026 cycle, and House and Senate. Presidential candidates are excluded unless `--office P` is explicitly supplied. Raw FEC identifiers and every retrieved receipt are preserved; unclear records are exported for review rather than discarded.

## Setup and API key

Python 3.11 or later is required:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Request a key from the [OpenFEC API documentation](https://api.open.fec.gov/developers/), copy the example environment file, and add your key to `.env`:

```bash
cp .env.example .env
```

```dotenv
FEC_API_KEY=your-key-here
```

The pipeline loads `.env` automatically. The file is ignored by Git and must never be committed; `.env.example` is the safe template that remains in source control. An explicitly supplied API key or an existing `FEC_API_KEY` shell variable takes precedence over the value in `.env`.

## Run

```bash
python -m fec_mt build --cycle 2026 --state MT
```

Options include:

```text
--office H                 Repeat for each desired office; defaults to H and S
--office S
--office P                 Explicitly include presidential candidates
--start-date YYYY-MM-DD    Defaults to January 1 of the pre-election year
--end-date YYYY-MM-DD      Defaults to the latest processed API data
--refresh                  Ignore locally cached bulk/API data
--output-dir data/         Choose the data root
--verbose                  Enable detailed logging
```

Any even-numbered cycle can be supplied without editing source. The command exits non-zero and lists committee IDs if any Schedule A extraction fails. Bulk files and per-committee API responses are cached under `data/raw/`; use `--refresh` for current copies.

Candidate Master includes historical and future candidates whose committees remain active. Discovery therefore prioritizes the requested election year, retains active missing-year records, and uses an office-wide active fallback only when no exact-cycle records exist. For Montana House builds, the specified universe is restricted to districts 01 and 02. A `CAND_PCC` fallback is accepted only when Committee Master independently confirms designation P or A; a candidate whose listed committee is another designation remains visible in diagnostics with no committee searched.

## Outputs

- `data/intermediate/candidates.csv`: selected candidate-master records.
- `data/intermediate/candidate_committees.csv`: deduplicated P/A committee relationships.
- `data/intermediate/committee_master.csv`: recipient and contributor committee lookup.
- `data/raw/schedule_a.parquet`: normalized, unclassified Schedule A records with original filing and transaction identifiers plus practical extra API fields.
- `data/output/receipts_classified.parquet`: all receipts with classes, inclusion flags, reported receipt amount, and donor-attributed amount; this is the audit trail.
- `data/output/contributions.csv` and `.parquet`: donor-attributable disclosures. `amount` means donor-attributed amount, not every reported receipt.
- `data/output/donor_summary.csv`: conservative donor-key totals by candidate.
- `data/output/candidate_summary.csv`: direct categories plus separate JFR gross-attribution and net-transfer measures.
- `data/output/donor_candidate_matrix.csv`: donor totals pivoted across candidates.
- `data/output/candidates_and_committees.csv`: every selected candidate and committee searched.
- `data/output/unclassified_receipts.csv`: unknown records and uncertain memo rows.
- `data/output/duplicate_transaction_ids.csv`: repeated recipient/transaction IDs for amendment investigation; rows are not deleted.
- `data/output/validation_report.csv`: calculations compared with FEC cycle totals where comparable.
- `data/output/run_metadata.json`: parameters, source URLs/files, retrieval time, counts, diagnostics, and Git commit.

Generated/downloaded data are ignored by Git.

## Classification and double-counting safeguards

For Form 3 committees, ordinary contribution-ledger rows come from Lines 11(a)(i), 11(b), 11(c), and 11(d). Signed amounts—including negative corrections—are retained. Loans, offsets, refunds/rebates, and miscellaneous receipts are not presented as ordinary donations. Memo rows are never globally dropped; financial-ledger and donor-attribution inclusion are separate flags with explicit reasons.

### Joint fundraising

A recognized JFR's Line 12 transfer is preserved as cash received but is not a donor. Original-contributor memo rows linked by back-reference IDs are donor-attributable but are not added as financial receipts. Committee Master designation `J` is primary; name text is a labeled fallback only.

Gross donor allocation and net JFR transfer are reported separately. They need not equal because transfers can be net of allocated fundraising costs. Never add the gross memo allocations and net transfers as separate donations.

### Partnerships and LLCs

The parent Line 11(a)(i) receipt remains in the ledger. Linked partner/member memo rows remain as attribution detail but are not added again to financial totals. The parent is not automatically replaced with its members.

Because donor summaries preserve attribution detail, do not sum every donor-summary row to derive campaign cash totals when parent and member attributions coexist. Use `candidate_summary.csv` or ledger flags in classified receipts for financial totals.

### Amendments

Schedule A requests use `data_type=processed`, letting the FEC determine current filing versions. The pipeline never deduplicates on donor name, date, and amount: two such transactions with different IDs may both be legitimate. It preserves `transaction_id`, `sub_id`, `original_sub_id`, `file_number`, and `amendment_indicator`, and exports repeated recipient/transaction IDs for investigation.

## Donor identity and limitations

Registered political committees use stable FEC committee IDs (`FEC:C…`) where supplied. Committee Master provides a canonical name and connected organization, while the originally reported contributor name is always retained.

Individuals usually lack stable FEC IDs. Their conservative key uses normalized name plus ZIP5, falling back to normalized name, city, and state. Normalization only uppercases, trims, collapses whitespace, standardizes simple punctuation, and extracts ZIP5. Similar-looking names are not aggressively merged, and the key is not claimed to identify a unique human.

> Individual donor totals are based on itemized donor records available from the FEC. Small-dollar contributions that are not required to be itemized cannot be associated with individual donors.

Candidate committees generally itemize an individual's contributions after the election-cycle aggregate exceeds $200. This dataset therefore describes all identifiable/itemized donors, not every person who gave any amount. Unitemized totals remain explicitly `NOT_COMPARABLE` to donor-level Schedule A rows.

Contributor data are also subject to restrictions on sale or use to solicit contributions. Review the [FEC API terms and data guidance](https://api.open.fec.gov/developers/) before use or redistribution.

## Tests

```bash
pytest
```

Tests cover discovery/linkage, conservative identity, direct individual/PAC/candidate receipts, loans, signed adjustments, committee resolution, JFR transfer/memo separation, partnership members, processed amendments, duplicate-ID diagnostics, legitimate duplicate-looking transactions, and pagination.

## Official sources

- [Candidate Master description](https://www.fec.gov/campaign-finance-data/candidate-master-file-description/)
- [Candidate–committee linkage description](https://www.fec.gov/campaign-finance-data/candidate-committee-linkage-file-description/)
- [Committee Master description](https://www.fec.gov/campaign-finance-data/committee-master-file-description/)
- [OpenFEC API](https://api.open.fec.gov/developers/)
