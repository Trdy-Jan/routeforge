import asyncio
from datetime import timedelta

import httpx
from sqlmodel import Session, select

from routeforge.db.models import NodeRow, Source, utcnow
from routeforge.scheduler import refresh_loop
from routeforge.sources.fetch import fetch_subscription, format_userinfo, parse_userinfo
from routeforge.sources.refresh import due_sources, refresh_due, refresh_source
from tests.helpers import mock_client

URL = "https://airport.example/sub?token=abc"
TWO_LINKS = "trojan://pw@a.example.com:443#A\nss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B\n"
USERINFO = "upload=100; download=200; total=1000; expire=1767225600"


def add_sub(s: Session, **kw) -> Source:
    src = Source(kind="subscription", name="机场", url=URL, **kw)
    s.add(src)
    s.commit()
    s.refresh(src)
    return src


def node_names(s: Session) -> list[str]:
    return [r.name for r in s.exec(select(NodeRow).order_by(NodeRow.position)).all()]


def test_parse_and_format_userinfo():
    assert parse_userinfo(USERINFO) == {"upload": 100, "download": 200, "total": 1000, "expire": 1767225600}
    assert parse_userinfo("upload=1; download=; total=x; junk") == {"upload": 1}
    assert parse_userinfo("") is None and parse_userinfo(None) is None
    assert format_userinfo({"total": 3, "upload": 1}) == "upload=1; total=3"


def test_fetch_sends_user_agent_and_reads_userinfo():
    def route(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "clash.meta"
        return httpx.Response(200, text=TWO_LINKS, headers={"subscription-userinfo": USERINFO})

    result = fetch_subscription(mock_client({URL: route}), URL, "clash.meta")
    assert result.text == TWO_LINKS
    assert result.userinfo["total"] == 1000


def test_refresh_success_syncs_nodes_and_metadata(engine):
    client = mock_client({URL: httpx.Response(200, text=TWO_LINKS, headers={"subscription-userinfo": USERINFO})})
    with Session(engine) as s:
        src = add_sub(s, last_error="旧错误")
        outcome = refresh_source(s, src, client)
        assert outcome.ok and outcome.sync.added == 2
        assert node_names(s) == ["A", "B"]
        s.refresh(src)
        assert src.last_error is None
        assert src.userinfo == {"upload": 100, "download": 200, "total": 1000, "expire": 1767225600}
        assert src.last_fetched_at is not None


def test_refresh_failures_keep_existing_nodes(engine):
    routes = {URL: httpx.Response(200, text=TWO_LINKS)}
    client = mock_client(routes)
    with Session(engine) as s:
        src = add_sub(s)
        refresh_source(s, src, client)

        routes[URL] = httpx.Response(500)
        bad = refresh_source(s, src, client)
        assert not bad.ok and "HTTP 500" in bad.error

        routes[URL] = httpx.Response(200, text="<html>维护中</html>")
        empty = refresh_source(s, src, client)
        assert not empty.ok and "没有可用节点" in empty.error

        routes[URL] = httpx.ConnectError("boom")
        down = refresh_source(s, src, client)
        assert not down.ok and "拉取失败" in down.error

        assert node_names(s) == ["A", "B"]
        s.refresh(src)
        assert "拉取失败" in src.last_error


def test_refresh_rejects_manual_source(engine):
    with Session(engine) as s:
        src = Source(kind="manual", name="手动")
        s.add(src)
        s.commit()
        try:
            refresh_source(s, src, mock_client({}))
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


def test_due_sources(engine):
    now = utcnow()
    with Session(engine) as s:
        never = add_sub(s)
        recent = add_sub(s, last_fetched_at=now - timedelta(minutes=10))
        stale = add_sub(s, last_fetched_at=now - timedelta(minutes=361))
        s.add(Source(kind="manual", name="手动"))
        s.commit()
        assert sorted(x.id for x in due_sources(s, now)) == sorted([never.id, stale.id])
        assert recent.id not in [x.id for x in due_sources(s, now)]


def test_refresh_due_and_loop_calls_on_change(engine):
    client = mock_client({URL: httpx.Response(200, text=TWO_LINKS)})
    with Session(engine) as s:
        add_sub(s)
    assert refresh_due(engine, client) == 1
    assert refresh_due(engine, client) == 0  # 刚刷新过，未到期

    with Session(engine) as s:
        add_sub(s)
    calls: list[int] = []

    async def main() -> None:
        task = asyncio.create_task(refresh_loop(engine, client, lambda: calls.append(1), interval=0.01))
        for _ in range(200):
            if calls:
                break
            await asyncio.sleep(0.01)
        task.cancel()

    asyncio.run(main())
    assert calls
