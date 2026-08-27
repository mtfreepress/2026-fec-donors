from __future__ import annotations

import json
import logging
import random
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.open.fec.gov/v1"
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class FECAPIError(RuntimeError):
    pass


class FECClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
        retries: int = 6,
        backoff_base: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("FEC_API_KEY is required")
        self.api_key = api_key
        self.retries = retries
        self.backoff_base = backoff_base
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={"X-Api-Key": api_key},
        )

    def __enter__(self) -> "FECClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = dict(params or {})
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.get(path.lstrip("/"), params=request_params)
                if response.status_code in TRANSIENT_STATUS:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = float(retry_after)
                    else:
                        delay = min(self.backoff_base * (2 ** attempt) + random.random(), 60)
                    if attempt == self.retries:
                        response.raise_for_status()
                    LOGGER.warning(
                        "FEC API returned %s for %s; retrying in %.1fs",
                        response.status_code,
                        path,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise FECAPIError(f"malformed JSON response from {path}") from exc
                if not isinstance(payload, dict):
                    raise FECAPIError(f"unexpected non-object response from {path}")
                return payload
            except (httpx.HTTPError, FECAPIError) as exc:
                last_error = exc
                if attempt == self.retries:
                    break
                delay = min(self.backoff_base * (2 ** attempt) + random.random(), 60)
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                error_label = f"HTTP {status}" if status else type(exc).__name__
                # Never interpolate an HTTPX exception: its URL includes the API key.
                LOGGER.warning("FEC API request failed (%s); retrying in %.1fs", error_label, delay)
                time.sleep(delay)
        status = last_error.response.status_code if isinstance(last_error, httpx.HTTPStatusError) else None
        detail = f"HTTP {status}" if status else type(last_error).__name__ if last_error else "unknown error"
        raise FECAPIError(f"FEC API request failed for {path}: {detail}")

    def fetch_schedule_a(
        self,
        committee_id: str,
        cycle: int,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {
                "committee_id": committee_id,
                "two_year_transaction_period": cycle,
                "data_type": "processed",
                "per_page": per_page,
                "page": page,
                "sort": "-contribution_receipt_date",
            }
            if start_date:
                params["min_date"] = date.fromisoformat(start_date).strftime("%m/%d/%Y")
            if end_date:
                params["max_date"] = date.fromisoformat(end_date).strftime("%m/%d/%Y")
            payload = self.get_json("schedules/schedule_a/", params)
            results = payload.get("results")
            if results is None:
                raise FECAPIError(f"Schedule A response for {committee_id} page {page} has no results key")
            if not isinstance(results, list):
                raise FECAPIError(f"Schedule A results for {committee_id} page {page} are malformed")
            LOGGER.info("  page %s: %s rows", page, len(results))
            if not results:
                break
            records.extend(record for record in results if isinstance(record, dict))

            pagination = payload.get("pagination") or {}
            pages = pagination.get("pages") or pagination.get("last_page")
            if pages is not None:
                try:
                    if page >= int(pages):
                        break
                    page += 1
                    continue
                except (TypeError, ValueError):
                    LOGGER.warning("Ignoring malformed pagination page count: %r", pages)
            if len(results) < per_page:
                break
            page += 1
            if page > 100_000:
                raise FECAPIError(f"pagination safety limit exceeded for {committee_id}")
        return records

    def fetch_committee_totals(self, committee_id: str, cycle: int) -> dict[str, Any] | None:
        payload = self.get_json(f"committee/{committee_id}/totals/", {"cycle": cycle, "per_page": 100})
        results = payload.get("results") or []
        if not isinstance(results, list):
            raise FECAPIError(f"committee totals response for {committee_id} is malformed")
        exact = [row for row in results if str(row.get("cycle", "")) == str(cycle)]
        return (exact or results or [None])[0]


def load_or_fetch_schedule_a(
    client: FECClient,
    committee_id: str,
    cycle: int,
    cache_dir: Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    cache_path = cache_dir / f"schedule_a_{committee_id}_{cycle}.json"
    if cache_path.exists() and not refresh:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("results"), list)
                and payload.get("committee_id") == committee_id
                and payload.get("cycle") == cycle
                and payload.get("start_date") == start_date
                and payload.get("end_date") == end_date
                and payload.get("data_type") == "processed"
            ):
                LOGGER.info("Using cached Schedule A records for %s", committee_id)
                return payload["results"]
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Ignoring malformed cache %s", cache_path)
    records = client.fetch_schedule_a(
        committee_id,
        cycle,
        start_date=start_date,
        end_date=end_date,
    )
    cache_path.write_text(
        json.dumps({
            "committee_id": committee_id,
            "cycle": cycle,
            "start_date": start_date,
            "end_date": end_date,
            "data_type": "processed",
            "results": records,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return records
