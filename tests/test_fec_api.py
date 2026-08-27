import json

import httpx

from fec_mt.fec_api import FECClient


def test_api_key_is_sent_in_header_and_not_logged_in_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == "test-secret"
        assert "test-secret" not in str(request.url)
        assert "api_key" not in request.url.params
        return httpx.Response(200, json={"results": []})

    with FECClient("test-secret", transport=httpx.MockTransport(handler)) as client:
        client.get_json("test/")


def test_schedule_a_full_pagination_stops_on_api_last_page():
    pages_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages_seen.append(page)
        return httpx.Response(200, json={
            "results": [{"sub_id": f"row-{page}"}],
            "pagination": {"page": page, "pages": 3, "count": 3},
        })

    with FECClient("test", transport=httpx.MockTransport(handler)) as client:
        records = client.fetch_schedule_a("C00111111", 2026, per_page=1)
    assert pages_seen == [1, 2, 3]
    assert [row["sub_id"] for row in records] == ["row-1", "row-2", "row-3"]


def test_schedule_a_does_not_trust_count_when_results_continue():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        results = [{"sub_id": str(page)}] if page <= 2 else []
        return httpx.Response(200, json={"results": results, "pagination": {"count": 1}})

    with FECClient("test", transport=httpx.MockTransport(handler)) as client:
        records = client.fetch_schedule_a("C00111111", 2026, per_page=1)
    assert len(records) == 2


def test_schedule_a_obeys_explicit_pages_even_if_page_is_not_full():
    pages_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages_seen.append(page)
        assert request.url.params["min_date"] == "01/01/2025"
        return httpx.Response(200, json={
            "results": [{"sub_id": str(page)}],
            "pagination": {"page": page, "pages": 2},
        })

    with FECClient("test", transport=httpx.MockTransport(handler)) as client:
        records = client.fetch_schedule_a(
            "C00111111", 2026, start_date="2025-01-01", per_page=100
        )
    assert pages_seen == [1, 2]
    assert len(records) == 2
