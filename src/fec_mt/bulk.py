from __future__ import annotations

import logging
import time
import zipfile
from io import BytesIO
from pathlib import Path

import httpx
import pandas as pd

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://www.fec.gov/files/bulk-downloads/{cycle}/{stem}{suffix}.zip"

CANDIDATE_COLUMNS = [
    "CAND_ID", "CAND_NAME", "CAND_PTY_AFFILIATION", "CAND_ELECTION_YR",
    "CAND_OFFICE_ST", "CAND_OFFICE", "CAND_OFFICE_DISTRICT", "CAND_ICI",
    "CAND_STATUS", "CAND_PCC", "CAND_ST1", "CAND_ST2", "CAND_CITY",
    "CAND_ST", "CAND_ZIP",
]
LINKAGE_COLUMNS = [
    "CAND_ID", "CAND_ELECTION_YR", "FEC_ELECTION_YR", "CMTE_ID",
    "CMTE_TP", "CMTE_DSGN", "LINKAGE_ID",
]
COMMITTEE_COLUMNS = [
    "CMTE_ID", "CMTE_NM", "TRES_NM", "CMTE_ST1", "CMTE_ST2", "CMTE_CITY",
    "CMTE_ST", "CMTE_ZIP", "CMTE_DSGN", "CMTE_TP", "CMTE_PTY_AFFILIATION",
    "CMTE_FILING_FREQ", "ORG_TP", "CONNECTED_ORG_NM", "CAND_ID",
]

BULK_FILES = {
    "candidate_master": ("cn", CANDIDATE_COLUMNS),
    "candidate_committee_linkage": ("ccl", LINKAGE_COLUMNS),
    "committee_master": ("cm", COMMITTEE_COLUMNS),
}


class BulkDownloadError(RuntimeError):
    pass


def bulk_url(kind: str, cycle: int) -> str:
    stem, _ = BULK_FILES[kind]
    return BASE_URL.format(cycle=cycle, stem=stem, suffix=str(cycle)[-2:])


def _download(url: str, timeout: float = 60.0, retries: int = 5) -> bytes:
    last_error: Exception | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(retries + 1):
            try:
                response = client.get(url)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError(
                        f"transient HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                if not response.content:
                    raise BulkDownloadError(f"empty response from {url}")
                return response.content
            except (httpx.HTTPError, BulkDownloadError) as exc:
                last_error = exc
                if attempt == retries:
                    break
                delay = min(2 ** attempt, 30)
                LOGGER.warning("Bulk download failed (%s); retrying in %ss", exc, delay)
                time.sleep(delay)
    raise BulkDownloadError(f"failed to download {url}: {last_error}")


def download_bulk_file(
    kind: str,
    cycle: int,
    raw_dir: Path,
    *,
    refresh: bool = False,
) -> tuple[Path, str]:
    stem, _ = BULK_FILES[kind]
    suffix = str(cycle)[-2:]
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = raw_dir / f"{stem}{suffix}.txt"
    url = bulk_url(kind, cycle)
    if output_path.exists() and not refresh:
        LOGGER.info("Using cached %s", output_path)
        return output_path, url

    LOGGER.info("Downloading %s", url)
    content = _download(url)
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            if not members:
                raise BulkDownloadError(f"archive from {url} contains no files")
            preferred = next((name for name in members if name.lower().endswith(".txt")), members[0])
            output_path.write_bytes(archive.read(preferred))
    except zipfile.BadZipFile as exc:
        raise BulkDownloadError(f"invalid ZIP archive from {url}") from exc
    return output_path, url


def read_bulk_file(path: Path, columns: list[str]) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            path,
            sep="|",
            names=columns,
            header=None,
            dtype="string",
            encoding="latin-1",
            keep_default_na=False,
            na_values=[],
        )
    except (OSError, pd.errors.ParserError) as exc:
        raise BulkDownloadError(f"could not parse {path}: {exc}") from exc
    if frame.shape[1] != len(columns):
        raise BulkDownloadError(f"unexpected column count in {path}")
    return frame


def load_bulk_data(kind: str, cycle: int, raw_dir: Path, *, refresh: bool = False) -> tuple[pd.DataFrame, str, Path]:
    path, url = download_bulk_file(kind, cycle, raw_dir, refresh=refresh)
    return read_bulk_file(path, BULK_FILES[kind][1]), url, path
