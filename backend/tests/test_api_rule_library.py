import httpx
import pytest

from routeforge.rule_library import list_url
from tests.test_rule_library import make_routes


@pytest.fixture
def library_routes(routes):
    routes.update(make_routes())
    routes[list_url("geosite", "category-ai-!cn")] = httpx.Response(200, text="openai.com\nclaude.ai\n")
    return routes


def test_requires_login(client):
    assert client.get("/api/rule-library").status_code == 401
    assert client.post("/api/rule-library/refresh", json={}).status_code == 401
    assert client.get("/api/rule-library/geosite/openai/content").status_code == 401


def test_list_and_refresh(admin, library_routes):
    data = admin.get("/api/rule-library").json()
    assert data["error"] is None and data["updated_at"]
    assert {"category": "geoip", "name": "telegram", "behavior": "ipcidr",
            "url": "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geoip/telegram.mrs"} in data["items"]
    assert len(data["items"]) == 4
    refreshed = admin.post("/api/rule-library/refresh", json={})
    assert refreshed.status_code == 200 and len(refreshed.json()["items"]) == 4


def test_index_unavailable_returns_502(admin):
    resp = admin.get("/api/rule-library")
    assert resp.status_code == 502 and "GitHub" in resp.json()["detail"]


def test_content_ok(admin, library_routes):
    resp = admin.get("/api/rule-library/geosite/openai/content")
    assert resp.status_code == 200
    assert resp.json() == {"total": 2, "matched": 2, "offset": 0, "lines": ["openai.com", "+.chatgpt.com"]}


def test_content_search_and_paging(admin, library_routes):
    resp = admin.get("/api/rule-library/geosite/openai/content", params={"q": "CHAT", "offset": 0, "limit": 1})
    assert resp.json() == {"total": 2, "matched": 1, "offset": 0, "lines": ["+.chatgpt.com"]}
    second = admin.get("/api/rule-library/geosite/openai/content", params={"offset": 1, "limit": 1})
    assert second.json()["lines"] == ["+.chatgpt.com"]


def test_content_rejects_bad_paging(admin, library_routes):
    url = "/api/rule-library/geosite/openai/content"
    assert admin.get(url, params={"limit": 0}).status_code == 422
    assert admin.get(url, params={"limit": 5000}).status_code == 422
    assert admin.get(url, params={"offset": -1}).status_code == 422
    assert admin.get(url, params={"q": "x" * 300}).status_code == 422


def test_content_name_with_bang(admin, library_routes):
    resp = admin.get("/api/rule-library/geosite/category-ai-!cn/content")
    assert resp.status_code == 200 and resp.json()["lines"] == ["openai.com", "claude.ai"]


def test_content_unknown_404(admin, library_routes):
    assert admin.get("/api/rule-library/geosite/nope/content").status_code == 404
    assert admin.get("/api/rule-library/bad/openai/content").status_code == 404


def test_content_upstream_missing_returns_502(admin, library_routes):
    resp = admin.get("/api/rule-library/geoip/telegram/content")
    assert resp.status_code == 502 and resp.json()["detail"]
