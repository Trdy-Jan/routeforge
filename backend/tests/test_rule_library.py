import httpx
import pytest

from routeforge import rule_library
from routeforge.rule_library import LibraryUnavailable, RuleLibrary, item_url, list_url
from routeforge.templates import load_templates
from tests.helpers import mock_client

TREE = "https://api.github.com/repos/MetaCubeX/meta-rules-dat/git/trees/meta:{}"


def tree(*paths: str) -> httpx.Response:
    return httpx.Response(200, json={"tree": [
        {"path": p, "type": "tree" if p == "classical" else "blob"} for p in paths]})


def make_routes() -> dict:
    return {
        TREE.format("geo/geosite"): tree("openai.mrs", "openai.list", "openai.yaml", "category-ai-!cn.mrs",
                                         "category-ai-!cn.list", "classical"),
        TREE.format("geo/geoip"): tree("telegram.mrs", "telegram.list", "classical"),
        TREE.format("geo-lite/geosite"): tree("apple.mrs", "apple.yaml"),
        list_url("geosite", "openai"): httpx.Response(200, text="# comment\n\nopenai.com\n  +.chatgpt.com  \n"),
    }


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def counting(routes: dict) -> tuple[httpx.Client, list[str]]:
    calls: list[str] = []
    inner = mock_client(routes)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return inner.send(request)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_index_parses_three_categories():
    idx = RuleLibrary(mock_client(make_routes())).index()
    assert {(i.category, i.name, i.behavior) for i in idx.items} == {
        ("geosite", "openai", "domain"), ("geosite", "category-ai-!cn", "domain"),
        ("geoip", "telegram", "ipcidr"), ("geo-lite", "apple", "domain")}
    assert idx.error is None and idx.updated_at is not None


def test_item_url_matches_template():
    assert item_url("geosite", "category-ai-!cn") == load_templates()["ai"].rule_providers[0].url
    assert item_url("geo-lite", "apple") == \
        "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo-lite/geosite/apple.mrs"
    assert list_url("geoip", "telegram") == \
        "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geoip/telegram.list"


def test_index_cached_until_ttl():
    client, calls = counting(make_routes())
    clock = Clock()
    lib = RuleLibrary(client, clock=clock)
    lib.index()
    assert len(calls) == 3
    lib.index()
    assert len(calls) == 3
    clock.now += 86401
    lib.index()
    assert len(calls) == 6
    lib.index(force=True)
    assert len(calls) == 9


def test_refresh_failure_keeps_stale_items():
    routes = make_routes()
    lib = RuleLibrary(mock_client(routes))
    first = lib.index()
    routes[TREE.format("geo/geoip")] = httpx.ConnectError("boom")
    again = lib.index(force=True)
    assert again.items == first.items
    assert again.error and again.updated_at == first.updated_at
    routes[TREE.format("geo/geoip")] = tree("cn.mrs")
    healed = lib.index(force=True)
    assert healed.error is None and ("geoip", "cn") in {(i.category, i.name) for i in healed.items}


def test_no_data_raises_unavailable():
    routes = make_routes()
    routes[TREE.format("geo/geosite")] = httpx.Response(403, json={"message": "rate limited"})
    with pytest.raises(LibraryUnavailable, match="GitHub"):
        RuleLibrary(mock_client(routes)).index()


def test_content_strips_comments_and_blank_lines():
    content = RuleLibrary(mock_client(make_routes())).content("geosite", "openai")
    assert content.total == 2 and content.matched == 2 and content.offset == 0
    assert content.lines == ["openai.com", "+.chatgpt.com"]


def big_routes(n: int) -> dict:
    routes = make_routes()
    routes[list_url("geosite", "openai")] = httpx.Response(200, text="\n".join(f"d{i}.Example.com" for i in range(n)))
    return routes


def test_content_pages_with_offset_and_limit():
    lib = RuleLibrary(mock_client(big_routes(10)))
    page = lib.content("geosite", "openai", offset=3, limit=4)
    assert page.total == 10 and page.matched == 10 and page.offset == 3
    assert page.lines == ["d3.Example.com", "d4.Example.com", "d5.Example.com", "d6.Example.com"]
    tail = lib.content("geosite", "openai", offset=8, limit=4)
    assert tail.lines == ["d8.Example.com", "d9.Example.com"]
    assert lib.content("geosite", "openai", offset=20, limit=4).lines == []


def test_content_search_is_case_insensitive_substring():
    lib = RuleLibrary(mock_client(big_routes(25)))
    page = lib.content("geosite", "openai", q="  D1  ", limit=3)
    # d1, d10..d19 共 11 条匹配，按原顺序分页
    assert page.total == 25 and page.matched == 11
    assert page.lines == ["d1.Example.com", "d10.Example.com", "d11.Example.com"]
    nxt = lib.content("geosite", "openai", q="d1", offset=9, limit=3)
    assert nxt.lines == ["d18.Example.com", "d19.Example.com"]
    assert lib.content("geosite", "openai", q="example.COM").matched == 25
    assert lib.content("geosite", "openai", q="nothing").matched == 0


def test_content_caps_huge_lists(monkeypatch):
    monkeypatch.setattr(rule_library, "MAX_LINES", 5)
    page = RuleLibrary(mock_client(big_routes(8))).content("geosite", "openai")
    assert page.total == 5 and len(page.lines) == 5


def test_content_unknown_raises_keyerror():
    lib = RuleLibrary(mock_client(make_routes()))
    with pytest.raises(KeyError):
        lib.content("geosite", "nope")
    with pytest.raises(KeyError):
        lib.content("bad", "openai")


def test_content_upstream_error_raises_unavailable():
    lib = RuleLibrary(mock_client(make_routes()))
    with pytest.raises(LibraryUnavailable):
        lib.content("geoip", "telegram")  # 索引里有，但 .list 路由缺失 → 404


def test_content_lru_cache():
    client, calls = counting(make_routes())
    lib = RuleLibrary(client)
    lib.content("geosite", "openai")
    n = len(calls)
    lib.content("geosite", "openai", q="chat", offset=0, limit=1)
    assert len(calls) == n
