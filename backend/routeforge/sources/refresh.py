"""刷新订阅源：拉取 → 解析 → 同步节点；失败时保留旧节点。"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import Engine
from sqlmodel import Session, select

from routeforge.db.models import Source, utcnow
from routeforge.parsers.subscription import parse_subscription
from routeforge.parsers.uri import LineError
from routeforge.services.library import SyncResult, sync_nodes
from routeforge.sources.fetch import fetch_subscription

logger = logging.getLogger(__name__)


@dataclass
class RefreshOutcome:
    ok: bool
    error: str | None = None
    sync: SyncResult | None = None
    parse_errors: list[LineError] = field(default_factory=list)


def refresh_source(session: Session, source: Source, client: httpx.Client) -> RefreshOutcome:
    if source.kind != "subscription" or not source.url:
        raise ValueError("只有订阅源可以刷新")
    source.last_fetched_at = utcnow()
    try:
        fetched = fetch_subscription(client, source.url, source.user_agent)
    except httpx.HTTPError as e:
        return _fail(session, source, f"拉取失败：{_describe(e)}")

    outcome = parse_subscription(fetched.text)
    if not outcome.nodes:
        detail = f"（{outcome.errors[0].message}）" if outcome.errors else ""
        return _fail(session, source, f"订阅中没有可用节点{detail}", outcome.errors)

    sync = sync_nodes(session, source.id, outcome.nodes)
    source.last_error = None
    source.userinfo = fetched.userinfo
    session.add(source)
    session.commit()
    return RefreshOutcome(ok=True, sync=sync, parse_errors=outcome.errors)


def _fail(session: Session, source: Source, message: str, parse_errors=()) -> RefreshOutcome:
    source.last_error = message
    session.add(source)
    session.commit()
    return RefreshOutcome(ok=False, error=message, parse_errors=list(parse_errors))


def _describe(e: httpx.HTTPError) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


def due_sources(session: Session, now: datetime) -> list[Source]:
    subs = session.exec(select(Source).where(Source.kind == "subscription")).all()
    return [
        s for s in subs
        if s.last_fetched_at is None or s.last_fetched_at + timedelta(minutes=s.refresh_interval) <= now
    ]


def refresh_due(engine: Engine, client: httpx.Client, now: datetime | None = None) -> int:
    with Session(engine) as session:
        due = due_sources(session, now or utcnow())
        for source in due:
            try:
                refresh_source(session, source, client)
            except Exception:
                logger.exception("刷新订阅源 #%s 出错", source.id)
                session.rollback()
        return len(due)
