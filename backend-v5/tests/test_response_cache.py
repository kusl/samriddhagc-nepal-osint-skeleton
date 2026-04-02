from starlette.requests import Request

from app.core.response_cache import _is_shared_auth_cacheable, _match_route, _should_bypass_cache


def _build_request(
    path: str,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
        "query_string": b"",
    }
    return Request(scope)


def test_match_route_covers_dashboard_public_endpoints():
    assert _match_route("/api/v1/debt-clock/nepal") == 30
    assert _match_route("/api/v1/govt-decisions/latest") == 120
    assert _match_route("/api/v1/cabinet-actions/summary") == 120
    assert _match_route("/api/v1/cabinet-actions/items") == 120
    assert _match_route("/api/v1/cabinet-actions/items/123") == 120
    assert _match_route("/api/v1/cabinet-actions/manifesto/AC1") == 120
    assert _match_route("/api/v1/economy/nrb-snapshot") == 600
    assert _match_route("/api/v1/analytics/consolidated-stories") == 30
    assert _match_route(
        "/api/v1/election-results/house-representatives/341708/parliamentary-summary"
    ) == 60


def test_should_bypass_cache_for_authenticated_or_cookie_requests():
    auth_request = _build_request(
        "/api/v1/watchlists",
        headers=[(b"authorization", b"Bearer test-token")],
    )
    cookie_request = _build_request(
        "/api/v1/activity/feed",
        headers=[(b"cookie", b"session=abc123")],
    )
    public_request = _build_request("/api/v1/govt-decisions/latest")

    assert _should_bypass_cache(auth_request) is True
    assert _should_bypass_cache(cookie_request) is True
    assert _should_bypass_cache(public_request) is False


def test_shared_dashboard_reads_do_not_bypass_cache_when_auth_header_present():
    shared_auth_request = _build_request(
        "/api/v1/analytics/consolidated-stories",
        headers=[(b"authorization", b"Bearer guest-token")],
    )

    assert _is_shared_auth_cacheable("/api/v1/analytics/consolidated-stories") is True
    assert _should_bypass_cache(shared_auth_request) is False
