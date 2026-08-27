from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .fec_api import FECAPIError, FECClient, load_or_fetch_schedule_a

LOGGER = logging.getLogger(__name__)


class ScheduleAFetchFailure(RuntimeError):
    def __init__(self, failed_committee_ids: list[str]) -> None:
        self.failed_committee_ids = failed_committee_ids
        super().__init__("failed Schedule A committees: " + ", ".join(failed_committee_ids))


def fetch_all_schedule_a(
    client: FECClient,
    candidate_committees: pd.DataFrame,
    *,
    cycle: int,
    cache_dir: Any,
    start_date: str | None,
    end_date: str | None,
    refresh: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    committees = candidate_committees.drop_duplicates("committee_id")
    for committee in committees.itertuples(index=False):
        LOGGER.info("Fetching %s — %s", committee.committee_id, committee.committee_name or "unknown committee")
        try:
            committee_records = load_or_fetch_schedule_a(
                client,
                committee.committee_id,
                cycle,
                cache_dir,
                start_date=start_date,
                end_date=end_date,
                refresh=refresh,
            )
            for record in committee_records:
                if not record.get("committee_id"):
                    record["committee_id"] = committee.committee_id
                if not record.get("committee_name"):
                    record["committee_name"] = committee.committee_name
            records.extend(committee_records)
        except (FECAPIError, OSError, ValueError) as exc:
            LOGGER.error("Failed to retrieve %s: %s", committee.committee_id, exc)
            failures.append(committee.committee_id)
    if failures:
        raise ScheduleAFetchFailure(failures)
    return records
