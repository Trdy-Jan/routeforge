# RouteForge P2 服务端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 P1 核心库之上构建 RouteForge 服务端：SQLite 持久化、节点库管理、机场订阅拉取与定时刷新、管理员鉴权、管理 API、公开订阅接口。

**Architecture:** FastAPI 应用由 `create_app(settings)` 工厂创建；数据层用 SQLModel（SQLite），节点与方案以 IR 的 JSON 形式存储；业务逻辑在 `services/`、`sources/` 中，路由只做 HTTP ↔ 服务调用；订阅刷新由 lifespan 中的 asyncio 循环驱动；订阅接口带内存缓存与「上次成功结果」回退。

**Tech Stack:** FastAPI、SQLModel、httpx、argon2-cffi、itsdangerous（Starlette SessionMiddleware）、uvicorn、pytest

**Spec:** `docs/superpowers/specs/2026-10-26-routeforge-design.md`

**前置：** P1（`docs/superpowers/plans/2026-10-27-routeforge-p1-core.md`）已完成。

## Global Constraints

- 所有命令在 `backend/` 下执行；测试 `uv run pytest`
- 环境变量：`ROUTEFORGE_ADMIN_PASSWORD`（首次启动必填）、`ROUTEFORGE_DATA_DIR`（默认 `./data`，Docker 中为 `/data`）、`ROUTEFORGE_COOKIE_SECURE`（默认 true）、`ROUTEFORGE_STATIC_DIR`（P3 使用）、`ROUTEFORGE_HOST`/`ROUTEFORGE_PORT`（默认 `0.0.0.0`/`8000`）、`ROUTEFORGE_FORWARDED_ALLOW_IPS`（默认 `127.0.0.1`）
- 订阅源默认刷新间隔 360 分钟、默认 User-Agent `clash.meta`、拉取超时 30 秒
- 订阅 token：`secrets.token_urlsafe(32)`；无效 token 一律 404
- 会话 cookie：`routeforge_session`，HttpOnly、SameSite=Lax、有效期 14 天，`https_only` 由 `ROUTEFORGE_COOKIE_SECURE` 控制
- 登录限速：同一 IP 5 分钟内失败 5 次 → 锁定 5 分钟（429）
- `/api/` 下的 POST/PUT/PATCH 请求必须是 `Content-Type: application/json`，否则 415（配合 SameSite 防 CSRF；无请求体的动作接口也发送 `{}`）
- 所有面向用户的错误信息为中文；时间统一存为 naive UTC（`utcnow()`）
- 订阅响应头：`Content-Disposition: attachment; filename*=UTF-8''<方案名>.<ext>`、`profile-update-interval: 24`；方案节点只来自一个订阅源时附 `subscription-userinfo`
- 与 spec 的偏差（实现细节，不改变行为）：`profile.last_good_render` 改为 JSON 列 `last_good`（按 target 存储，为后续多格式准备）；定时刷新用 lifespan 中的 asyncio 循环代替 APScheduler（每 60 秒检查一次到期订阅源，少一个依赖）；应用入口为 `routeforge/app.py` + `routeforge/__main__.py`

## Review Focus

1. **机场返回 HTTP 200 但内容是错误页 / 空节点** → 视为失败，保留旧节点并记录错误，而不是清空节点库（Task 3 测试）
2. **机场节点改名 / 重名 / 顺序变化** → 同名节点保留 id 与启用状态，重名按出现顺序一一匹配（Task 2 测试）
3. **方案被改坏后客户端刷新订阅** → 返回上次成功的配置，而不是 500 让客户端断网（Task 7 测试）
4. **方案名含中文** → `Content-Disposition` 使用 RFC 5987 编码，不触发 latin-1 编码异常（Task 7 测试）
5. **节点库 / 方案 / 订阅刷新后订阅缓存** → 任何写操作和定时刷新后缓存失效，客户端拿到最新配置（Task 3、Task 7 测试）

## File Structure

```
backend/routeforge/
  config.py            Settings.from_env()
  db/
    __init__.py
    models.py          Source、NodeRow、ProfileRow、Setting、utcnow()、new_token()
    session.py         make_engine()、init_db()
  services/
    __init__.py
    library.py         load_library、import_links、sync_nodes、delete_source
    render.py          render_profile → RenderOutcome
  sources/
    __init__.py
    fetch.py           fetch_subscription、parse_userinfo、format_userinfo
    refresh.py         refresh_source、due_sources、refresh_due
  scheduler.py         refresh_loop（asyncio）
  auth.py              bootstrap_secrets、verify_password、LoginLimiter、ConfigError
  cache.py             RenderCache
  api/
    __init__.py
    deps.py            SessionDep、CacheDep、HttpDep、require_admin
    auth.py sources.py nodes.py profiles.py templates.py subscribe.py
  app.py               create_app()
  __main__.py          main()：uvicorn 启动
backend/tests/
  __init__.py  conftest.py  helpers.py（mock_client、ADMIN_PASSWORD）
  test_db.py test_library.py test_refresh.py test_api_auth.py test_api_sources_nodes.py
  test_api_profiles.py test_api_subscribe.py test_main.py
```

---

### Task 1: 依赖、配置与数据库模型

**Files:**
- Modify: `backend/pyproject.toml`（依赖由 `uv add` 写入）
- Create: `backend/routeforge/config.py`
- Create: `backend/routeforge/db/__init__.py`（空）
- Create: `backend/routeforge/db/models.py`
- Create: `backend/routeforge/db/session.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Consumes: P1 `NodeAdapter`、`Node`、`Profile`
- Produces:
  - `Settings(data_dir: Path, database_url: str, admin_password: str | None, cookie_secure: bool = True, static_dir: Path | None = None)`、`Settings.from_env(env: Mapping[str, str] = os.environ)`
  - `utcnow() -> datetime`（naive UTC）、`new_token() -> str`
  - `Source`（id、kind `"manual" | "subscription"`、name、url、refresh_interval、user_agent、last_fetched_at、last_error、userinfo: dict | None）
  - `NodeRow`（表名 `node`：id、source_id、name、data、enabled、position；`from_node(source_id, node, position)`、`to_node()`、`set_node(node)`）
  - `ProfileRow`（表名 `profile`：id、name、token、data、last_good: dict | None、last_good_at；`new(name)`、`to_profile()`、`set_profile(profile)`）
  - `Setting`（key、value）
  - `make_engine(url: str) -> Engine`（`"sqlite://"` 为共享连接的内存库）、`init_db(engine) -> None`
  - 测试 fixture：`engine`（已建表的内存库）

- [ ] **Step 1: 安装依赖**

Run: `uv add fastapi "uvicorn[standard]" sqlmodel httpx argon2-cffi itsdangerous`
Expected: `pyproject.toml` 的 dependencies 增加这 6 项，`uv.lock` 更新

- [ ] **Step 2: 写失败测试**

`backend/tests/conftest.py`：

```python
import pytest

from routeforge.db.session import init_db, make_engine


@pytest.fixture
def engine():
    e = make_engine("sqlite://")
    init_db(e)
    return e
```

`backend/tests/test_db.py`：

```python
from sqlmodel import Session, select

from routeforge.config import Settings
from routeforge.db.models import NodeRow, ProfileRow, Source
from routeforge.ir.node import Reality, TLSOptions, VlessNode
from routeforge.ir.profile import Profile


def test_node_row_stores_ir_as_json(engine):
    node = VlessNode(name="落地", server="ex.com", port=443, uuid="u",
                     tls=TLSOptions(reality=Reality(public_key="PK")))
    with Session(engine) as s:
        src = Source(kind="manual", name="手动")
        s.add(src)
        s.commit()
        s.refresh(src)
        s.add(NodeRow.from_node(src.id, node, position=0))
        s.commit()
    with Session(engine) as s:
        row = s.exec(select(NodeRow)).one()
        assert row.name == "落地"
        assert row.enabled is True
        assert row.to_node() == node
        row.set_node(node.model_copy(update={"name": "改名"}))
        assert row.name == "改名" and row.data["name"] == "改名"


def test_profile_row_new_has_token_and_empty_profile(engine):
    with Session(engine) as s:
        row = ProfileRow.new("我的方案")
        s.add(row)
        s.commit()
        s.refresh(row)
        assert len(row.token) >= 40
        assert row.to_profile() == Profile(name="我的方案")
        assert row.last_good is None
        row.set_profile(Profile(name="新名字"))
        assert row.name == "新名字"
        assert ProfileRow.new("x").token != row.token


def test_settings_from_env(tmp_path):
    s = Settings.from_env({"ROUTEFORGE_DATA_DIR": str(tmp_path), "ROUTEFORGE_COOKIE_SECURE": "false"})
    assert s.data_dir == tmp_path
    assert s.database_url == f"sqlite:///{(tmp_path / 'routeforge.db').as_posix()}"
    assert s.cookie_secure is False
    assert s.admin_password is None and s.static_dir is None

    d = Settings.from_env({"ROUTEFORGE_ADMIN_PASSWORD": "pw", "ROUTEFORGE_STATIC_DIR": "/srv/web"})
    assert d.cookie_secure is True and d.admin_password == "pw" and d.static_dir.as_posix() == "/srv/web"
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.db'`）

- [ ] **Step 4: 实现 `backend/routeforge/config.py`**

```python
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_FALSY = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    admin_password: str | None
    cookie_secure: bool = True
    static_dir: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        data_dir = Path(env.get("ROUTEFORGE_DATA_DIR", "./data"))
        static = env.get("ROUTEFORGE_STATIC_DIR")
        return cls(
            data_dir=data_dir,
            database_url=f"sqlite:///{(data_dir / 'routeforge.db').as_posix()}",
            admin_password=env.get("ROUTEFORGE_ADMIN_PASSWORD") or None,
            cookie_secure=env.get("ROUTEFORGE_COOKIE_SECURE", "true").strip().lower() not in _FALSY,
            static_dir=Path(static) if static else None,
        )
```

- [ ] **Step 5: 实现 `backend/routeforge/db/models.py`**

```python
import secrets
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from routeforge.ir.node import Node, NodeAdapter
from routeforge.ir.profile import Profile


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_token() -> str:
    return secrets.token_urlsafe(32)


class Source(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str  # "manual" | "subscription"
    name: str
    url: str | None = None
    refresh_interval: int = 360  # 分钟
    user_agent: str = "clash.meta"
    last_fetched_at: datetime | None = None  # 最近一次拉取尝试
    last_error: str | None = None
    userinfo: dict | None = Field(default=None, sa_column=Column(JSON))


class NodeRow(SQLModel, table=True):
    __tablename__ = "node"

    id: int | None = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="source.id", index=True)
    name: str  # 与 data["name"] 同步，用于刷新时按名称匹配
    data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    enabled: bool = True
    position: int = 0

    @classmethod
    def from_node(cls, source_id: int, node: Node, position: int) -> "NodeRow":
        return cls(source_id=source_id, name=node.name, data=NodeAdapter.dump_python(node, mode="json"),
                   position=position)

    def to_node(self) -> Node:
        return NodeAdapter.validate_python(self.data)

    def set_node(self, node: Node) -> None:
        self.name = node.name
        self.data = NodeAdapter.dump_python(node, mode="json")


class ProfileRow(SQLModel, table=True):
    __tablename__ = "profile"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    token: str = Field(index=True, unique=True)
    data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # {target: {"content": str, "content_type": str, "file_ext": str}}
    last_good: dict | None = Field(default=None, sa_column=Column(JSON))
    last_good_at: datetime | None = None

    @classmethod
    def new(cls, name: str) -> "ProfileRow":
        return cls(name=name, token=new_token(), data=Profile(name=name).model_dump(mode="json"))

    def to_profile(self) -> Profile:
        return Profile.model_validate({**self.data, "name": self.name})

    def set_profile(self, profile: Profile) -> None:
        self.name = profile.name
        self.data = profile.model_dump(mode="json")


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
```

- [ ] **Step 6: 实现 `backend/routeforge/db/session.py`**

```python
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine


def make_engine(url: str) -> Engine:
    if url == "sqlite://":  # 测试用内存库：所有线程共享同一连接
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, connect_args={"check_same_thread": False})


def init_db(engine: Engine) -> None:
    import routeforge.db.models  # noqa: F401  注册表结构

    SQLModel.metadata.create_all(engine)
```

- [ ] **Step 7: 运行确认通过**

Run: `uv run pytest tests/test_db.py -v`
Expected: 3 passed

- [ ] **Step 8: 提交**

```bash
git add backend/pyproject.toml backend/uv.lock backend/routeforge/config.py backend/routeforge/db backend/tests/conftest.py backend/tests/test_db.py
git commit -m "feat(server): add settings and sqlite models"
```

---

### Task 2: 节点库服务（导入、同步、加载）

**Files:**
- Create: `backend/routeforge/services/__init__.py`（空）
- Create: `backend/routeforge/services/library.py`
- Test: `backend/tests/test_library.py`

**Interfaces:**
- Consumes: Task 1 模型；P1 `parse_many`、`LineError`、`LibraryNode`、`Node`
- Produces:
  - `ImportResult(added: int, errors: list[LineError])`、`SyncResult(added: int, updated: int, removed: int)`
  - `load_library(session) -> list[LibraryNode]`（按 source_id、position、id 排序）
  - `import_links(session, source_id: int, text: str) -> ImportResult`（追加到该源末尾）
  - `sync_nodes(session, source_id: int, nodes: list[Node]) -> SyncResult`（按名称匹配，重名按顺序一一匹配；保留 id 与 enabled；position 改为新顺序；多余的删除）
  - `delete_source(session, source: Source) -> None`（连同节点）
  - 以上函数都会 commit

- [ ] **Step 1: 写失败测试 `backend/tests/test_library.py`**

```python
from sqlmodel import Session, select

from routeforge.db.models import NodeRow, Source
from routeforge.ir.node import SSNode
from routeforge.services.library import delete_source, import_links, load_library, sync_nodes

LINK_A = "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#A"
LINK_B = "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8389#B"


def ss(name: str, port: int = 1) -> SSNode:
    return SSNode(name=name, server="1.1.1.1", port=port, cipher="aes-128-gcm", password="p")


def make_source(s: Session, kind: str = "manual") -> Source:
    src = Source(kind=kind, name=kind, url="https://x" if kind == "subscription" else None)
    s.add(src)
    s.commit()
    s.refresh(src)
    return src


def test_import_links_appends_and_reports_bad_lines(engine):
    with Session(engine) as s:
        src = make_source(s)
        first = import_links(s, src.id, f"{LINK_A}\nnot-a-link\n")
        assert first.added == 1
        assert [e.line for e in first.errors] == ["not-a-link"]
        import_links(s, src.id, LINK_B)
        rows = s.exec(select(NodeRow).order_by(NodeRow.position)).all()
        assert [(r.name, r.position) for r in rows] == [("A", 0), ("B", 1)]


def test_sync_preserves_identity_and_enabled_and_handles_duplicates(engine):
    with Session(engine) as s:
        src = make_source(s, "subscription")
        sync_nodes(s, src.id, [ss("HK"), ss("HK"), ss("JP"), ss("US")])
        rows = {(r.name, r.position): r for r in s.exec(select(NodeRow)).all()}
        hk2_id = rows[("HK", 1)].id
        jp = rows[("JP", 2)]
        jp.enabled = False
        s.add(jp)
        s.commit()
        jp_id = jp.id

        result = sync_nodes(s, src.id, [ss("JP", port=2), ss("HK"), ss("HK"), ss("SG")])
        assert (result.added, result.updated, result.removed) == (1, 3, 1)

        after = s.exec(select(NodeRow).order_by(NodeRow.position)).all()
        assert [r.name for r in after] == ["JP", "HK", "HK", "SG"]
        assert after[0].id == jp_id and after[0].enabled is False and after[0].to_node().port == 2
        assert after[2].id == hk2_id
        assert "US" not in [r.name for r in after]


def test_sync_only_touches_its_own_source(engine):
    with Session(engine) as s:
        a, b = make_source(s, "subscription"), make_source(s, "subscription")
        sync_nodes(s, a.id, [ss("X")])
        sync_nodes(s, b.id, [ss("Y")])
        sync_nodes(s, a.id, [])
        assert [r.name for r in s.exec(select(NodeRow)).all()] == ["Y"]


def test_load_library_order_and_fields(engine):
    with Session(engine) as s:
        a, b = make_source(s), make_source(s)
        import_links(s, b.id, LINK_B)
        import_links(s, a.id, LINK_A)
        library = load_library(s)
        assert [(ln.source_id, ln.node.name) for ln in library] == [(a.id, "A"), (b.id, "B")]
        assert all(ln.enabled for ln in library)


def test_delete_source_removes_its_nodes(engine):
    with Session(engine) as s:
        src = make_source(s)
        src_id = src.id
        import_links(s, src_id, LINK_A)
        delete_source(s, src)
        assert s.exec(select(NodeRow)).all() == []
        assert s.get(Source, src_id) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_library.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.services'`）

- [ ] **Step 3: 实现 `backend/routeforge/services/library.py`**

```python
"""节点库读写：手动导入、订阅同步、加载为 resolver 输入。"""

from dataclasses import dataclass

from sqlmodel import Session, func, select

from routeforge.db.models import NodeRow, Source
from routeforge.ir.node import Node
from routeforge.parsers.uri import LineError, parse_many
from routeforge.resolver import LibraryNode


@dataclass
class ImportResult:
    added: int
    errors: list[LineError]


@dataclass
class SyncResult:
    added: int
    updated: int
    removed: int


def load_library(session: Session) -> list[LibraryNode]:
    rows = session.exec(select(NodeRow).order_by(NodeRow.source_id, NodeRow.position, NodeRow.id)).all()
    return [LibraryNode(id=r.id, source_id=r.source_id, enabled=r.enabled, node=r.to_node()) for r in rows]


def import_links(session: Session, source_id: int, text: str) -> ImportResult:
    outcome = parse_many(text)
    current = session.exec(select(func.max(NodeRow.position)).where(NodeRow.source_id == source_id)).one()
    start = 0 if current is None else current + 1
    for i, node in enumerate(outcome.nodes):
        session.add(NodeRow.from_node(source_id, node, start + i))
    session.commit()
    return ImportResult(added=len(outcome.nodes), errors=outcome.errors)


def sync_nodes(session: Session, source_id: int, nodes: list[Node]) -> SyncResult:
    rows = session.exec(
        select(NodeRow).where(NodeRow.source_id == source_id).order_by(NodeRow.position, NodeRow.id)
    ).all()
    by_name: dict[str, list[NodeRow]] = {}
    for row in rows:
        by_name.setdefault(row.name, []).append(row)

    added = updated = 0
    for position, node in enumerate(nodes):
        bucket = by_name.get(node.name)
        if bucket:
            row = bucket.pop(0)
            row.set_node(node)
            row.position = position
            session.add(row)
            updated += 1
        else:
            session.add(NodeRow.from_node(source_id, node, position))
            added += 1

    leftovers = [row for bucket in by_name.values() for row in bucket]
    for row in leftovers:
        session.delete(row)
    session.commit()
    return SyncResult(added=added, updated=updated, removed=len(leftovers))


def delete_source(session: Session, source: Source) -> None:
    for row in session.exec(select(NodeRow).where(NodeRow.source_id == source.id)).all():
        session.delete(row)
    session.delete(source)
    session.commit()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_library.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add backend/routeforge/services backend/tests/test_library.py
git commit -m "feat(server): add node library import, sync and loading"
```

### Task 3: 订阅拉取、刷新与定时循环

**Files:**
- Create: `backend/routeforge/sources/__init__.py`（空）
- Create: `backend/routeforge/sources/fetch.py`
- Create: `backend/routeforge/sources/refresh.py`
- Create: `backend/routeforge/scheduler.py`
- Create: `backend/tests/__init__.py`（空）、`backend/tests/helpers.py`
- Modify: `backend/pyproject.toml`（pytest `pythonpath`）
- Test: `backend/tests/test_refresh.py`

**Interfaces:**
- Consumes: Task 1 模型与 `utcnow`；Task 2 `sync_nodes`、`SyncResult`；P1 `parse_subscription`、`LineError`
- Produces:
  - `sources.fetch`: `FetchResult(text: str, userinfo: dict[str, int] | None)`、`fetch_subscription(client: httpx.Client, url: str, user_agent: str) -> FetchResult`（非 2xx 抛 `httpx.HTTPStatusError`）、`parse_userinfo(header: str | None) -> dict[str, int] | None`、`format_userinfo(info: dict) -> str`
  - `sources.refresh`: `RefreshOutcome(ok: bool, error: str | None, sync: SyncResult | None, parse_errors: list[LineError])`、`refresh_source(session, source: Source, client) -> RefreshOutcome`（非订阅源抛 `ValueError`）、`due_sources(session, now: datetime) -> list[Source]`、`refresh_due(engine, client, now: datetime | None = None) -> int`（返回尝试刷新的源数量）
  - `scheduler.refresh_loop(engine, client, on_change: Callable[[], None], interval: float = 60) -> None`（协程；有源被刷新时调用 `on_change`）
  - `tests.helpers`：`mock_client(routes: dict[str, httpx.Response | Exception | Callable[[httpx.Request], httpx.Response]]) -> httpx.Client`

失败判定：网络错误、非 2xx、解析出 0 个节点 → 不动节点，写 `last_error`；成功 → 同步节点、清空 `last_error`、更新 `userinfo`。无论成败都更新 `last_fetched_at`（避免失败源每分钟重试）。

- [ ] **Step 1: 创建测试辅助模块**

`backend/tests/helpers.py`：

```python
import httpx


def mock_client(routes: dict) -> httpx.Client:
    """routes: url -> httpx.Response | Exception | (request -> httpx.Response)"""

    def handler(request: httpx.Request) -> httpx.Response:
        route = routes.get(str(request.url))
        if route is None:
            return httpx.Response(404)
        if isinstance(route, Exception):
            raise route
        if callable(route):
            return route(request)
        return route

    return httpx.Client(transport=httpx.MockTransport(handler))
```

创建空文件 `backend/tests/__init__.py`，并在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 中加入 `pythonpath = ["."]`，使测试可以 `from tests.helpers import mock_client`。

- [ ] **Step 2: 写失败测试 `backend/tests/test_refresh.py`**

```python
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
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_refresh.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.scheduler'`）

- [ ] **Step 4: 实现 `backend/routeforge/sources/fetch.py`**

```python
"""拉取机场订阅。"""

from dataclasses import dataclass

import httpx

_USERINFO_KEYS = ("upload", "download", "total", "expire")


@dataclass
class FetchResult:
    text: str
    userinfo: dict[str, int] | None


def fetch_subscription(client: httpx.Client, url: str, user_agent: str) -> FetchResult:
    resp = client.get(url, headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return FetchResult(text=resp.text, userinfo=parse_userinfo(resp.headers.get("subscription-userinfo")))


def parse_userinfo(header: str | None) -> dict[str, int] | None:
    if not header:
        return None
    info: dict[str, int] = {}
    for part in header.split(";"):
        key, sep, value = part.strip().partition("=")
        value = value.strip()
        if sep and key in _USERINFO_KEYS and value.isdigit():
            info[key] = int(value)
    return info or None


def format_userinfo(info: dict) -> str:
    return "; ".join(f"{k}={info[k]}" for k in _USERINFO_KEYS if k in info)
```

- [ ] **Step 5: 实现 `backend/routeforge/sources/refresh.py`**

```python
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
```

- [ ] **Step 6: 实现 `backend/routeforge/scheduler.py`**

```python
"""定时刷新订阅：每 interval 秒检查一次到期的订阅源。"""

import asyncio
import logging
from collections.abc import Callable

import httpx
from sqlalchemy import Engine

from routeforge.sources.refresh import refresh_due

logger = logging.getLogger(__name__)


async def refresh_loop(engine: Engine, client: httpx.Client, on_change: Callable[[], None],
                       interval: float = 60) -> None:
    while True:
        try:
            if await asyncio.to_thread(refresh_due, engine, client):
                on_change()
        except Exception:
            logger.exception("定时刷新订阅出错")
        await asyncio.sleep(interval)
```

- [ ] **Step 7: 运行确认通过**

Run: `uv run pytest tests/test_refresh.py -v`
Expected: 全部 passed

- [ ] **Step 8: 提交**

```bash
git add backend/pyproject.toml backend/routeforge/sources backend/routeforge/scheduler.py backend/tests/__init__.py backend/tests/helpers.py backend/tests/test_refresh.py
git commit -m "feat(server): fetch and refresh airport subscriptions on a schedule"
```

### Task 4: 鉴权、渲染缓存与应用工厂

**Files:**
- Create: `backend/routeforge/auth.py`
- Create: `backend/routeforge/cache.py`
- Create: `backend/routeforge/api/__init__.py`（空）
- Create: `backend/routeforge/api/deps.py`
- Create: `backend/routeforge/api/auth.py`
- Create: `backend/routeforge/app.py`
- Modify: `backend/tests/conftest.py`（追加应用相关 fixture）、`backend/tests/helpers.py`（`ADMIN_PASSWORD`）
- Test: `backend/tests/test_api_auth.py`

**Interfaces:**
- Consumes: Task 1 `Settings`、`Setting`、`make_engine`、`init_db`；Task 3 `refresh_loop`；`tests.helpers.mock_client`
- Produces:
  - `auth`: `ConfigError(RuntimeError)`、`bootstrap_secrets(session, admin_password: str | None) -> str`（返回会话密钥；库中无管理员密码且未提供时抛 `ConfigError`）、`verify_password(session, password: str) -> bool`、`LoginLimiter(max_failures=5, window=300, lockout=300, clock=time.monotonic)`（`is_locked(key)`、`record_failure(key)`、`reset(key)`）
  - `cache.RenderCache`：`get(key)`、`put(key, value)`、`invalidate()`（线程安全）
  - `api.deps`: `get_session`、`SessionDep`、`CacheDep`、`HttpDep`、`require_admin`（未登录 401）
  - `app.create_app(settings: Settings, *, http_client: httpx.Client | None = None, start_scheduler: bool = True) -> FastAPI`；`app.state` 上有 `settings`、`engine`、`cache`、`http`、`limiter`
  - 接口：`POST /api/auth/login {password}`、`POST /api/auth/logout {}`、`GET /api/auth/me`
  - conftest fixture：`routes`（dict，测试可往里放 mock 响应）、`settings`、`app`、`client`、`admin`（已登录的 client）、`db`（绑定 app 引擎的 Session）；`tests.helpers.ADMIN_PASSWORD = "secret-pw"`

- [ ] **Step 1: 在 `backend/tests/conftest.py` 追加 fixture**

文件顶部 import 区追加：

```python
from fastapi.testclient import TestClient
from sqlmodel import Session

from routeforge.app import create_app
from routeforge.config import Settings
from tests.helpers import ADMIN_PASSWORD, mock_client
```

在 `backend/tests/helpers.py` 顶部（import 之后）加入常量：

```python
ADMIN_PASSWORD = "secret-pw"
```

文件末尾追加：

```python
@pytest.fixture
def routes() -> dict:
    return {}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, database_url="sqlite://", admin_password=ADMIN_PASSWORD, cookie_secure=False)


@pytest.fixture
def app(settings, routes):
    return create_app(settings, http_client=mock_client(routes), start_scheduler=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    resp = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    return client


@pytest.fixture
def db(app):
    with Session(app.state.engine) as s:
        yield s
```

- [ ] **Step 2: 写失败测试 `backend/tests/test_api_auth.py`**

```python
import pytest
from fastapi.testclient import TestClient

from routeforge.app import create_app
from routeforge.auth import ConfigError, LoginLimiter
from routeforge.config import Settings
from tests.helpers import ADMIN_PASSWORD


def test_login_me_logout(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": ADMIN_PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").json() == {"admin": True}
    assert client.post("/api/auth/logout", json={}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_session_cookie_flags(client):
    resp = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    cookie = resp.headers["set-cookie"].lower()
    assert "routeforge_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_lockout_after_five_failures(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": ADMIN_PASSWORD}).status_code == 429


def test_limiter_unlocks_after_lockout_window():
    now = [0.0]
    limiter = LoginLimiter(max_failures=2, window=60, lockout=100, clock=lambda: now[0])
    limiter.record_failure("ip")
    now[0] = 61  # 第一次失败已滑出窗口
    limiter.record_failure("ip")
    assert not limiter.is_locked("ip")
    limiter.record_failure("ip")
    assert limiter.is_locked("ip")
    now[0] = 162
    assert not limiter.is_locked("ip")


def test_non_json_post_rejected(client):
    resp = client.post("/api/auth/login", data={"password": ADMIN_PASSWORD})
    assert resp.status_code == 415


def test_first_start_requires_admin_password(tmp_path):
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{(tmp_path / 'r.db').as_posix()}",
                        admin_password=None, cookie_secure=False)
    with pytest.raises(ConfigError):
        create_app(settings, start_scheduler=False)


def test_password_only_needed_on_first_start(tmp_path):
    url = f"sqlite:///{(tmp_path / 'r.db').as_posix()}"
    create_app(Settings(data_dir=tmp_path, database_url=url, admin_password="first", cookie_secure=False),
               start_scheduler=False)
    app = create_app(Settings(data_dir=tmp_path, database_url=url, admin_password=None, cookie_secure=False),
                     start_scheduler=False)
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"password": "first"}).status_code == 200
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_api_auth.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.app'`）

- [ ] **Step 4: 实现 `backend/routeforge/auth.py`**

```python
"""管理员密码、会话密钥与登录限速。"""

import secrets
import time
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlmodel import Session

from routeforge.db.models import Setting

ADMIN_HASH_KEY = "admin_password_hash"
SESSION_SECRET_KEY = "session_secret"
_hasher = PasswordHasher()


class ConfigError(RuntimeError):
    pass


def bootstrap_secrets(session: Session, admin_password: str | None) -> str:
    if session.get(Setting, ADMIN_HASH_KEY) is None:
        if not admin_password:
            raise ConfigError("首次启动必须设置环境变量 ROUTEFORGE_ADMIN_PASSWORD")
        session.add(Setting(key=ADMIN_HASH_KEY, value=_hasher.hash(admin_password)))
    secret = session.get(Setting, SESSION_SECRET_KEY)
    if secret is None:
        secret = Setting(key=SESSION_SECRET_KEY, value=secrets.token_urlsafe(32))
        session.add(secret)
    session.commit()
    return secret.value


def verify_password(session: Session, password: str) -> bool:
    row = session.get(Setting, ADMIN_HASH_KEY)
    if row is None:
        return False
    try:
        return _hasher.verify(row.value, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


class LoginLimiter:
    """滑动窗口内失败 max_failures 次后锁定 lockout 秒。仅内存，单进程有效。"""

    def __init__(self, max_failures: int = 5, window: float = 300, lockout: float = 300,
                 clock: Callable[[], float] = time.monotonic):
        self.max_failures = max_failures
        self.window = window
        self.lockout = lockout
        self.clock = clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def is_locked(self, key: str) -> bool:
        return self._locked_until.get(key, 0) > self.clock()

    def record_failure(self, key: str) -> None:
        now = self.clock()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        recent.append(now)
        if len(recent) >= self.max_failures:
            self._locked_until[key] = now + self.lockout
            recent = []
        self._failures[key] = recent

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)
```

- [ ] **Step 5: 实现 `backend/routeforge/cache.py`**

```python
import threading
from typing import Any


class RenderCache:
    """订阅渲染结果缓存；任何数据写入后整体失效。"""

    def __init__(self) -> None:
        self._data: dict[Any, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def invalidate(self) -> None:
        with self._lock:
            self._data.clear()
```

- [ ] **Step 6: 实现 `backend/routeforge/api/deps.py`**

```python
from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from routeforge.cache import RenderCache


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_cache(request: Request) -> RenderCache:
    return request.app.state.cache


def get_http(request: Request) -> httpx.Client:
    return request.app.state.http


def require_admin(request: Request) -> None:
    if not request.session.get("admin"):
        raise HTTPException(status_code=401, detail="未登录")


SessionDep = Annotated[Session, Depends(get_session)]
CacheDep = Annotated[RenderCache, Depends(get_cache)]
HttpDep = Annotated[httpx.Client, Depends(get_http)]
```

- [ ] **Step 7: 实现 `backend/routeforge/api/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from routeforge.api.deps import SessionDep, require_admin
from routeforge.auth import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, session: SessionDep) -> dict:
    limiter = request.app.state.limiter
    key = request.client.host if request.client else "unknown"
    if limiter.is_locked(key):
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 5 分钟后再试")
    if not verify_password(session, body.password):
        limiter.record_failure(key)
        raise HTTPException(status_code=401, detail="密码错误")
    limiter.reset(key)
    request.session["admin"] = True
    return {"ok": True}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_admin)])
def me() -> dict:
    return {"admin": True}
```

- [ ] **Step 8: 实现 `backend/routeforge/app.py`**

```python
"""FastAPI 应用工厂。"""

import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from routeforge.api import auth as auth_api
from routeforge.auth import LoginLimiter, bootstrap_secrets
from routeforge.cache import RenderCache
from routeforge.config import Settings
from routeforge.db.session import init_db, make_engine
from routeforge.scheduler import refresh_loop

_UNSAFE_METHODS = {"POST", "PUT", "PATCH"}


def create_app(settings: Settings, *, http_client: httpx.Client | None = None,
               start_scheduler: bool = True) -> FastAPI:
    if settings.database_url.startswith("sqlite:///"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    init_db(engine)
    with Session(engine) as session:
        session_secret = bootstrap_secrets(session, settings.admin_password)

    client = http_client or httpx.Client(timeout=30, follow_redirects=True)
    cache = RenderCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(refresh_loop(engine, client, cache.invalidate)) if start_scheduler else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if http_client is None:
                client.close()

    app = FastAPI(title="RouteForge", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.cache = cache
    app.state.http = client
    app.state.limiter = LoginLimiter()

    @app.middleware("http")
    async def json_only(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in _UNSAFE_METHODS:
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "请求必须是 JSON"}, status_code=415)
        return await call_next(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie="routeforge_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    app.include_router(auth_api.router)
    return app
```

- [ ] **Step 9: 运行确认通过（含之前全部测试）**

Run: `uv run pytest -v`
Expected: 全部 passed

- [ ] **Step 10: 提交**

```bash
git add backend/routeforge/auth.py backend/routeforge/cache.py backend/routeforge/api backend/routeforge/app.py backend/tests/conftest.py backend/tests/helpers.py backend/tests/test_api_auth.py
git commit -m "feat(server): add admin auth, render cache and app factory"
```

### Task 5: 节点源与节点管理 API

**Files:**
- Create: `backend/routeforge/api/sources.py`
- Create: `backend/routeforge/api/nodes.py`
- Modify: `backend/routeforge/app.py`（注册路由）
- Test: `backend/tests/test_api_sources_nodes.py`

**Interfaces:**
- Consumes: Task 2 `import_links`、`delete_source`、`load_library`；Task 3 `refresh_source`；Task 4 `SessionDep`、`CacheDep`、`HttpDep`、`require_admin`；P1 `Filter`、`match_filter`、`LineError`
- Produces（全部需登录；所有写操作后 `cache.invalidate()`）：
  - `GET /api/sources` → `list[SourceOut]`；`SourceOut = {id, kind, name, url, refresh_interval, user_agent, last_fetched_at, last_error, userinfo, node_count}`
  - `POST /api/sources {kind, name, url?, refresh_interval?, user_agent?}` → 201 `SourceOut`（订阅源创建后立即拉取一次）
  - `PATCH /api/sources/{id} {name?, url?, refresh_interval?, user_agent?}` → `SourceOut`
  - `DELETE /api/sources/{id}` → 204（连同节点）
  - `POST /api/sources/{id}/refresh {}` → `RefreshOut = {ok, error, added, updated, removed, parse_errors: [{line, message}]}`（仅订阅源）
  - `POST /api/sources/{id}/nodes/import {text}` → `ImportOut = {added, errors: [{line, message}]}`（仅手动源）
  - `GET /api/nodes?source_id=&q=` → `list[NodeOut]`；`NodeOut = {id, source_id, name, type, server, port, enabled, position, data}`
  - `PATCH /api/nodes/{id} {name?, enabled?}` → `NodeOut`（订阅节点不能改名）
  - `DELETE /api/nodes/{id}` → 204（仅手动节点）
  - `POST /api/nodes/bulk {ids, enabled}` → `{updated}`
  - `POST /api/nodes/match {source_id?, name_regex, exclude_regex?}` → `list[NodeOut]`（正则无效 400）

- [ ] **Step 1: 写失败测试 `backend/tests/test_api_sources_nodes.py`**

```python
import httpx

SUB_URL = "https://airport.example/sub"
LINKS = (
    "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#A\n"
    "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8389#B\n"
    "broken\n"
)


def create_manual(admin) -> int:
    resp = admin.post("/api/sources", json={"kind": "manual", "name": "手动"})
    assert resp.status_code == 201
    return resp.json()["id"]


def create_subscription(admin, routes) -> dict:
    routes[SUB_URL] = httpx.Response(200, text=LINKS, headers={"subscription-userinfo": "upload=1; download=2; total=3"})
    resp = admin.post("/api/sources", json={"kind": "subscription", "name": "机场", "url": SUB_URL})
    assert resp.status_code == 201
    return resp.json()


def test_requires_login(client):
    assert client.get("/api/sources").status_code == 401
    assert client.get("/api/nodes").status_code == 401


def test_manual_source_import_list_and_edit(admin):
    sid = create_manual(admin)
    result = admin.post(f"/api/sources/{sid}/nodes/import", json={"text": LINKS}).json()
    assert result["added"] == 2
    assert result["errors"] == [{"line": "broken", "message": "不是分享链接"}]

    nodes = admin.get("/api/nodes", params={"source_id": sid}).json()
    assert [n["name"] for n in nodes] == ["A", "B"]
    assert (nodes[0]["type"], nodes[0]["server"], nodes[0]["port"]) == ("ss", "1.2.3.4", 8388)

    a_id = nodes[0]["id"]
    renamed = admin.patch(f"/api/nodes/{a_id}", json={"name": "香港 A"}).json()
    assert renamed["name"] == "香港 A" and renamed["data"]["name"] == "香港 A"
    assert [n["id"] for n in admin.get("/api/nodes", params={"q": "香港"}).json()] == [a_id]

    bulk = admin.post("/api/nodes/bulk", json={"ids": [n["id"] for n in nodes], "enabled": False})
    assert bulk.json() == {"updated": 2}
    assert all(not n["enabled"] for n in admin.get("/api/nodes").json())
    assert admin.get("/api/sources").json()[0]["node_count"] == 2

    assert admin.delete(f"/api/nodes/{a_id}").status_code == 204
    assert len(admin.get("/api/nodes").json()) == 1


def test_subscription_source_fetches_on_create_and_keeps_nodes_on_failure(admin, routes):
    src = create_subscription(admin, routes)
    assert src["node_count"] == 2 and src["last_error"] is None
    assert src["userinfo"] == {"upload": 1, "download": 2, "total": 3}

    routes[SUB_URL] = httpx.Response(503)
    result = admin.post(f"/api/sources/{src['id']}/refresh", json={}).json()
    assert result["ok"] is False and "503" in result["error"]

    after = admin.get("/api/sources").json()[0]
    assert after["node_count"] == 2 and "503" in after["last_error"]


def test_subscription_nodes_cannot_be_renamed_deleted_or_imported(admin, routes):
    src = create_subscription(admin, routes)
    nid = admin.get("/api/nodes").json()[0]["id"]
    assert admin.patch(f"/api/nodes/{nid}", json={"name": "x"}).status_code == 400
    assert admin.patch(f"/api/nodes/{nid}", json={"enabled": False}).json()["enabled"] is False
    assert admin.delete(f"/api/nodes/{nid}").status_code == 400
    assert admin.post(f"/api/sources/{src['id']}/nodes/import", json={"text": LINKS}).status_code == 400


def test_source_validation_and_kind_rules(admin):
    assert admin.post("/api/sources", json={"kind": "subscription", "name": "x"}).status_code == 422
    assert admin.post("/api/sources", json={"kind": "subscription", "name": "x", "url": "ftp://a"}).status_code == 422
    assert admin.post("/api/sources", json={"kind": "manual", "name": ""}).status_code == 422
    sid = create_manual(admin)
    assert admin.post(f"/api/sources/{sid}/refresh", json={}).status_code == 400
    assert admin.patch(f"/api/sources/{sid}", json={"url": "https://a"}).status_code == 400
    assert admin.patch(f"/api/sources/{sid}", json={"name": "改名"}).json()["name"] == "改名"
    assert admin.patch("/api/sources/999", json={"name": "x"}).status_code == 404


def test_delete_source_removes_nodes(admin):
    sid = create_manual(admin)
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": LINKS})
    assert admin.delete(f"/api/sources/{sid}").status_code == 204
    assert admin.get("/api/sources").json() == []
    assert admin.get("/api/nodes").json() == []


def test_match_filter(admin):
    sid = create_manual(admin)
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": LINKS})
    matched = admin.post("/api/nodes/match", json={"source_id": sid, "name_regex": "^A$"}).json()
    assert [n["name"] for n in matched] == ["A"]
    assert admin.post("/api/nodes/match", json={"name_regex": "("}).status_code == 400
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_api_sources_nodes.py -v`
Expected: FAIL（各接口 404）

- [ ] **Step 3: 实现 `backend/routeforge/api/sources.py`**

```python
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, func, select

from routeforge.api.deps import CacheDep, HttpDep, SessionDep, require_admin
from routeforge.db.models import NodeRow, Source
from routeforge.parsers.uri import LineError
from routeforge.services.library import delete_source, import_links
from routeforge.sources.refresh import refresh_source

router = APIRouter(prefix="/api/sources", tags=["sources"], dependencies=[Depends(require_admin)])


def _valid_url(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


class SourceIn(BaseModel):
    kind: Literal["manual", "subscription"]
    name: str = Field(min_length=1, max_length=100)
    url: str | None = None
    refresh_interval: int = Field(default=360, ge=10, le=10080)
    user_agent: str = Field(default="clash.meta", min_length=1)

    @model_validator(mode="after")
    def _check_url(self) -> "SourceIn":
        if self.kind == "subscription" and not _valid_url(self.url):
            raise ValueError("订阅源需要 http(s) 链接")
        if self.kind == "manual":
            self.url = None
        return self


class SourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = None
    refresh_interval: int | None = Field(default=None, ge=10, le=10080)
    user_agent: str | None = Field(default=None, min_length=1)


class SourceOut(BaseModel):
    id: int
    kind: str
    name: str
    url: str | None
    refresh_interval: int
    user_agent: str
    last_fetched_at: datetime | None
    last_error: str | None
    userinfo: dict | None
    node_count: int


class ImportIn(BaseModel):
    text: str = Field(min_length=1)


class ImportOut(BaseModel):
    added: int
    errors: list[LineError]


class RefreshOut(BaseModel):
    ok: bool
    error: str | None = None
    added: int = 0
    updated: int = 0
    removed: int = 0
    parse_errors: list[LineError] = []


def _get(session: Session, source_id: int) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="节点源不存在")
    return source


def _out(session: Session, source: Source) -> SourceOut:
    count = session.exec(select(func.count()).select_from(NodeRow).where(NodeRow.source_id == source.id)).one()
    return SourceOut(**source.model_dump(), node_count=count)


@router.get("")
def list_sources(session: SessionDep) -> list[SourceOut]:
    return [_out(session, s) for s in session.exec(select(Source).order_by(Source.id)).all()]


@router.post("", status_code=201)
def create_source(body: SourceIn, session: SessionDep, http: HttpDep, cache: CacheDep) -> SourceOut:
    source = Source(**body.model_dump())
    session.add(source)
    session.commit()
    session.refresh(source)
    if source.kind == "subscription":
        refresh_source(session, source, http)
    cache.invalidate()
    return _out(session, source)


@router.patch("/{source_id}")
def update_source(source_id: int, body: SourcePatch, session: SessionDep, cache: CacheDep) -> SourceOut:
    source = _get(session, source_id)
    changes = body.model_dump(exclude_none=True)
    if "url" in changes:
        if source.kind != "subscription":
            raise HTTPException(status_code=400, detail="手动节点源没有订阅链接")
        if not _valid_url(changes["url"]):
            raise HTTPException(status_code=400, detail="订阅源需要 http(s) 链接")
    for key, value in changes.items():
        setattr(source, key, value)
    session.add(source)
    session.commit()
    session.refresh(source)
    cache.invalidate()
    return _out(session, source)


@router.delete("/{source_id}", status_code=204)
def remove_source(source_id: int, session: SessionDep, cache: CacheDep) -> Response:
    delete_source(session, _get(session, source_id))
    cache.invalidate()
    return Response(status_code=204)


@router.post("/{source_id}/refresh")
def refresh(source_id: int, session: SessionDep, http: HttpDep, cache: CacheDep) -> RefreshOut:
    source = _get(session, source_id)
    if source.kind != "subscription":
        raise HTTPException(status_code=400, detail="手动节点源无需刷新")
    outcome = refresh_source(session, source, http)
    cache.invalidate()
    sync = outcome.sync
    return RefreshOut(
        ok=outcome.ok,
        error=outcome.error,
        added=sync.added if sync else 0,
        updated=sync.updated if sync else 0,
        removed=sync.removed if sync else 0,
        parse_errors=outcome.parse_errors,
    )


@router.post("/{source_id}/nodes/import")
def import_nodes(source_id: int, body: ImportIn, session: SessionDep, cache: CacheDep) -> ImportOut:
    source = _get(session, source_id)
    if source.kind != "manual":
        raise HTTPException(status_code=400, detail="订阅源的节点由订阅内容决定，不能手动导入")
    result = import_links(session, source.id, body.text)
    cache.invalidate()
    return ImportOut(added=result.added, errors=result.errors)
```

- [ ] **Step 4: 实现 `backend/routeforge/api/nodes.py`**

```python
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from routeforge.api.deps import CacheDep, SessionDep, require_admin
from routeforge.db.models import NodeRow, Source
from routeforge.ir.profile import Filter
from routeforge.resolver import match_filter
from routeforge.services.library import load_library

router = APIRouter(prefix="/api/nodes", tags=["nodes"], dependencies=[Depends(require_admin)])


class NodeOut(BaseModel):
    id: int
    source_id: int
    name: str
    type: str
    server: str
    port: int
    enabled: bool
    position: int
    data: dict


class NodePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None


class BulkIn(BaseModel):
    ids: list[int]
    enabled: bool


class BulkOut(BaseModel):
    updated: int


def _out(row: NodeRow) -> NodeOut:
    return NodeOut(id=row.id, source_id=row.source_id, name=row.name, type=row.data["type"],
                   server=row.data["server"], port=row.data["port"], enabled=row.enabled,
                   position=row.position, data=row.data)


def _get(session: Session, node_id: int) -> NodeRow:
    row = session.get(NodeRow, node_id)
    if row is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return row


def _require_manual(session: Session, row: NodeRow, action: str) -> None:
    source = session.get(Source, row.source_id)
    if source is None or source.kind != "manual":
        raise HTTPException(status_code=400, detail=f"订阅节点会在刷新时被覆盖，不能{action}")


@router.get("")
def list_nodes(session: SessionDep, source_id: int | None = None, q: str | None = None) -> list[NodeOut]:
    stmt = select(NodeRow).order_by(NodeRow.source_id, NodeRow.position, NodeRow.id)
    if source_id is not None:
        stmt = stmt.where(NodeRow.source_id == source_id)
    rows = session.exec(stmt).all()
    if q:
        rows = [r for r in rows if q.lower() in r.name.lower()]
    return [_out(r) for r in rows]


@router.patch("/{node_id}")
def update_node(node_id: int, body: NodePatch, session: SessionDep, cache: CacheDep) -> NodeOut:
    row = _get(session, node_id)
    if body.name is not None and body.name != row.name:
        _require_manual(session, row, "改名")
        row.set_node(row.to_node().model_copy(update={"name": body.name}))
    if body.enabled is not None:
        row.enabled = body.enabled
    session.add(row)
    session.commit()
    session.refresh(row)
    cache.invalidate()
    return _out(row)


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: int, session: SessionDep, cache: CacheDep) -> Response:
    row = _get(session, node_id)
    _require_manual(session, row, "删除（可以改为禁用）")
    session.delete(row)
    session.commit()
    cache.invalidate()
    return Response(status_code=204)


@router.post("/bulk")
def bulk_update(body: BulkIn, session: SessionDep, cache: CacheDep) -> BulkOut:
    rows = session.exec(select(NodeRow).where(col(NodeRow.id).in_(body.ids))).all()
    for row in rows:
        row.enabled = body.enabled
        session.add(row)
    session.commit()
    cache.invalidate()
    return BulkOut(updated=len(rows))


@router.post("/match")
def match_nodes(body: Filter, session: SessionDep) -> list[NodeOut]:
    try:
        matched = match_filter(load_library(session), body)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"正则无效：{e}") from e
    ids = [ln.id for ln in matched]
    rows = {r.id: r for r in session.exec(select(NodeRow).where(col(NodeRow.id).in_(ids))).all()}
    return [_out(rows[i]) for i in ids]
```

- [ ] **Step 5: 在 `app.py` 注册路由**

导入改为：

```python
from routeforge.api import auth as auth_api
from routeforge.api import nodes as nodes_api
from routeforge.api import sources as sources_api
```

`app.include_router(auth_api.router)` 之后追加：

```python
    app.include_router(sources_api.router)
    app.include_router(nodes_api.router)
```

- [ ] **Step 6: 运行确认通过**

Run: `uv run pytest tests/test_api_sources_nodes.py -v`
Expected: 全部 passed

- [ ] **Step 7: 提交**

```bash
git add backend/routeforge/api/sources.py backend/routeforge/api/nodes.py backend/routeforge/app.py backend/tests/test_api_sources_nodes.py
git commit -m "feat(api): add source and node management endpoints"
```

### Task 6: 方案、模板与预览 API

**Files:**
- Create: `backend/routeforge/services/render.py`
- Create: `backend/routeforge/api/profiles.py`
- Create: `backend/routeforge/api/templates.py`
- Modify: `backend/routeforge/app.py`（注册路由）
- Test: `backend/tests/test_api_profiles.py`

**Interfaces:**
- Consumes: Task 1 `ProfileRow`、`new_token`；Task 2 `load_library`；Task 4 依赖项；P1 `Profile`、`resolve`、`RENDERERS`、`get_renderer`、`RenderResult`、`load_templates`、`apply_template`
- Produces:
  - `services.render`: `RenderOutcome(result: RenderResult | None, errors: list[str], warnings: list[str], source_ids: list[int])`（`.ok` 属性）、`render_profile(session, profile: Profile, target: str) -> RenderOutcome`（target 必须已在 `RENDERERS` 中）
  - 接口（全部需登录；写操作后 `cache.invalidate()`）：
    - `GET /api/profiles` → `[{id, name, token}]`
    - `POST /api/profiles {name}` → 201 `ProfileOut = {id, token, last_good_at, profile: Profile}`
    - `GET /api/profiles/{id}` → `ProfileOut`
    - `PUT /api/profiles/{id}`（body 为完整 `Profile`）→ `ProfileOut`；结构不合法 422；允许保存语义有误的方案（预览中显示错误）
    - `DELETE /api/profiles/{id}` → 204
    - `POST /api/profiles/{id}/apply-template {template_id}` → `{profile: ProfileOut, notes: [str]}`；未知模板 404
    - `POST /api/profiles/{id}/rotate-token {}` → `ProfileOut`
    - `GET /api/profiles/{id}/preview?target=mihomo` → `{ok, content, errors, warnings}`；未知 target 400
    - `GET /api/templates` → `[{id, name, description}]`

- [ ] **Step 1: 写失败测试 `backend/tests/test_api_profiles.py`**

```python
SS_HK = "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#%E9%A6%99%E6%B8%AF%2001"
GOOD = {
    "name": "方案A",
    "groups": [{"name": "Proxy", "members": [{"kind": "filter", "name_regex": "香港"}]}],
    "rules": [{"type": "MATCH", "target": "Proxy"}],
}


def create_profile(admin, name="我的方案") -> dict:
    resp = admin.post("/api/profiles", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def import_hk(admin) -> None:
    sid = admin.post("/api/sources", json={"kind": "manual", "name": "手动"}).json()["id"]
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": SS_HK})


def test_requires_login(client):
    assert client.get("/api/profiles").status_code == 401
    assert client.get("/api/templates").status_code == 401


def test_create_get_update_delete(admin):
    p = create_profile(admin)
    assert p["profile"] == {"name": "我的方案", "groups": [], "rules": [], "rule_providers": [], "chains": []}
    assert len(p["token"]) >= 40 and p["last_good_at"] is None

    updated = admin.put(f"/api/profiles/{p['id']}", json=GOOD).json()
    assert updated["profile"]["name"] == "方案A"
    assert updated["profile"]["groups"][0]["type"] == "select"
    assert admin.get(f"/api/profiles/{p['id']}").json() == updated
    assert admin.get("/api/profiles").json() == [{"id": p["id"], "name": "方案A", "token": p["token"]}]

    bad = {"name": "x", "groups": [{"name": "G", "type": "bogus"}]}
    assert admin.put(f"/api/profiles/{p['id']}", json=bad).status_code == 422

    assert admin.delete(f"/api/profiles/{p['id']}").status_code == 204
    assert admin.get(f"/api/profiles/{p['id']}").status_code == 404


def test_templates_list_and_apply(admin):
    templates = admin.get("/api/templates").json()
    assert len(templates) == 6
    assert {"id": "ads", "name": "广告拦截"}.items() <= templates[0].items()

    p = create_profile(admin)
    applied = admin.post(f"/api/profiles/{p['id']}/apply-template", json={"template_id": "ai"}).json()
    assert [g["name"] for g in applied["profile"]["profile"]["groups"]] == ["节点选择", "AI 服务"]
    assert any("节点选择" in n for n in applied["notes"])
    assert admin.get(f"/api/profiles/{p['id']}").json()["profile"] == applied["profile"]["profile"]
    assert admin.post(f"/api/profiles/{p['id']}/apply-template", json={"template_id": "nope"}).status_code == 404


def test_preview_renders_or_reports_errors(admin):
    import_hk(admin)
    p = create_profile(admin)
    admin.put(f"/api/profiles/{p['id']}", json=GOOD)
    preview = admin.get(f"/api/profiles/{p['id']}/preview").json()
    assert preview["ok"] is True and preview["errors"] == []
    assert "香港 01" in preview["content"]

    admin.put(f"/api/profiles/{p['id']}", json={**GOOD, "rules": []})
    broken = admin.get(f"/api/profiles/{p['id']}/preview").json()
    assert broken["ok"] is False and broken["content"] is None
    assert any("MATCH" in e for e in broken["errors"])

    assert admin.get(f"/api/profiles/{p['id']}/preview", params={"target": "surge"}).status_code == 400


def test_rotate_token(admin):
    p = create_profile(admin)
    rotated = admin.post(f"/api/profiles/{p['id']}/rotate-token", json={}).json()
    assert rotated["token"] != p["token"] and len(rotated["token"]) >= 40
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_api_profiles.py -v`
Expected: FAIL（接口 404）

- [ ] **Step 3: 实现 `backend/routeforge/services/render.py`**

```python
"""方案 → 目标格式：加载节点库、resolve、渲染。"""

from dataclasses import dataclass, field

from sqlmodel import Session

from routeforge.ir.profile import Profile
from routeforge.renderers import RenderResult, get_renderer
from routeforge.resolver import resolve
from routeforge.services.library import load_library


@dataclass
class RenderOutcome:
    result: RenderResult | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_ids: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.result is not None


def render_profile(session: Session, profile: Profile, target: str) -> RenderOutcome:
    renderer = get_renderer(target)
    resolved = resolve(profile, load_library(session))
    if not resolved.ok:
        return RenderOutcome(result=None, errors=resolved.errors, warnings=resolved.warnings)
    result = renderer.render(resolved.profile)
    return RenderOutcome(
        result=result,
        warnings=resolved.warnings + result.warnings,
        source_ids=resolved.profile.source_ids,
    )
```

- [ ] **Step 4: 实现 `backend/routeforge/api/profiles.py`**

```python
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from routeforge.api.deps import CacheDep, SessionDep, require_admin
from routeforge.cache import RenderCache
from routeforge.db.models import ProfileRow, new_token
from routeforge.ir.profile import Profile
from routeforge.renderers import RENDERERS
from routeforge.services.render import render_profile
from routeforge.templates import apply_template, load_templates

router = APIRouter(prefix="/api/profiles", tags=["profiles"], dependencies=[Depends(require_admin)])


class ProfileSummary(BaseModel):
    id: int
    name: str
    token: str


class ProfileOut(BaseModel):
    id: int
    token: str
    last_good_at: datetime | None
    profile: Profile


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApplyTemplateIn(BaseModel):
    template_id: str


class ApplyTemplateOut(BaseModel):
    profile: ProfileOut
    notes: list[str]


class PreviewOut(BaseModel):
    ok: bool
    content: str | None
    errors: list[str]
    warnings: list[str]


def _get(session: Session, profile_id: int) -> ProfileRow:
    row = session.get(ProfileRow, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    return row


def _out(row: ProfileRow) -> ProfileOut:
    return ProfileOut(id=row.id, token=row.token, last_good_at=row.last_good_at, profile=row.to_profile())


def _save(session: Session, row: ProfileRow, cache: RenderCache) -> ProfileRow:
    session.add(row)
    session.commit()
    session.refresh(row)
    cache.invalidate()
    return row


@router.get("")
def list_profiles(session: SessionDep) -> list[ProfileSummary]:
    rows = session.exec(select(ProfileRow).order_by(ProfileRow.id)).all()
    return [ProfileSummary(id=r.id, name=r.name, token=r.token) for r in rows]


@router.post("", status_code=201)
def create_profile(body: ProfileCreate, session: SessionDep, cache: CacheDep) -> ProfileOut:
    return _out(_save(session, ProfileRow.new(body.name), cache))


@router.get("/{profile_id}")
def get_profile(profile_id: int, session: SessionDep) -> ProfileOut:
    return _out(_get(session, profile_id))


@router.put("/{profile_id}")
def update_profile(profile_id: int, body: Profile, session: SessionDep, cache: CacheDep) -> ProfileOut:
    row = _get(session, profile_id)
    row.set_profile(body)
    return _out(_save(session, row, cache))


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, session: SessionDep, cache: CacheDep) -> Response:
    session.delete(_get(session, profile_id))
    session.commit()
    cache.invalidate()
    return Response(status_code=204)


@router.post("/{profile_id}/apply-template")
def apply(profile_id: int, body: ApplyTemplateIn, session: SessionDep, cache: CacheDep) -> ApplyTemplateOut:
    row = _get(session, profile_id)
    template = load_templates().get(body.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    profile, notes = apply_template(row.to_profile(), template)
    row.set_profile(profile)
    return ApplyTemplateOut(profile=_out(_save(session, row, cache)), notes=notes)


@router.post("/{profile_id}/rotate-token")
def rotate_token(profile_id: int, session: SessionDep, cache: CacheDep) -> ProfileOut:
    row = _get(session, profile_id)
    row.token = new_token()
    return _out(_save(session, row, cache))


@router.get("/{profile_id}/preview")
def preview(profile_id: int, session: SessionDep, target: str = "mihomo") -> PreviewOut:
    row = _get(session, profile_id)
    if target not in RENDERERS:
        raise HTTPException(status_code=400, detail=f"不支持的目标格式：{target}")
    outcome = render_profile(session, row.to_profile(), target)
    return PreviewOut(
        ok=outcome.ok,
        content=outcome.result.content if outcome.result else None,
        errors=outcome.errors,
        warnings=outcome.warnings,
    )
```

- [ ] **Step 5: 实现 `backend/routeforge/api/templates.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from routeforge.api.deps import require_admin
from routeforge.templates import load_templates

router = APIRouter(prefix="/api/templates", tags=["templates"], dependencies=[Depends(require_admin)])


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str


@router.get("")
def list_templates() -> list[TemplateOut]:
    return [TemplateOut(id=t.id, name=t.name, description=t.description) for t in load_templates().values()]
```

- [ ] **Step 6: 在 `app.py` 注册路由**

导入追加：

```python
from routeforge.api import profiles as profiles_api
from routeforge.api import templates as templates_api
```

`include_router` 区追加：

```python
    app.include_router(profiles_api.router)
    app.include_router(templates_api.router)
```

- [ ] **Step 7: 运行确认通过**

Run: `uv run pytest tests/test_api_profiles.py -v`
Expected: 全部 passed

- [ ] **Step 8: 提交**

```bash
git add backend/routeforge/services/render.py backend/routeforge/api/profiles.py backend/routeforge/api/templates.py backend/routeforge/app.py backend/tests/test_api_profiles.py
git commit -m "feat(api): add profile, template and preview endpoints"
```

### Task 7: 公开订阅接口 `/sub/{token}`

**Files:**
- Create: `backend/routeforge/api/subscribe.py`
- Modify: `backend/routeforge/app.py`（注册路由）
- Test: `backend/tests/test_api_subscribe.py`

**Interfaces:**
- Consumes: Task 6 `render_profile`；Task 3 `format_userinfo`；Task 4 `SessionDep`、`CacheDep`；Task 1 `ProfileRow`、`Source`、`utcnow`；P1 `RENDERERS`
- Produces: `GET /sub/{token}?target=mihomo`（无需登录）
  - token 不存在 → 404；target 不支持 → 400
  - 缓存命中 → 直接返回；未命中 → 渲染：成功则写入 `ProfileRow.last_good[target]`、`last_good_at` 并缓存；失败则返回 `last_good[target]`（不缓存，不带 userinfo），没有历史版本 → 500
  - 响应头见 Global Constraints
  - `CachedSub(content, content_type, file_ext, userinfo: str | None)` 为缓存值，key 为 `(profile_id, target)`

- [ ] **Step 1: 写失败测试 `backend/tests/test_api_subscribe.py`**

```python
from urllib.parse import quote

import httpx
import yaml

SUB_URL = "https://airport.example/sub"
SS_HK = "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#%E9%A6%99%E6%B8%AF%2001"
GOOD = {
    "name": "我的方案",
    "groups": [{"name": "Proxy", "members": [{"kind": "filter", "name_regex": "."}]}],
    "rules": [{"type": "MATCH", "target": "Proxy"}],
}


def make_profile(admin, body=GOOD) -> dict:
    p = admin.post("/api/profiles", json={"name": body["name"]}).json()
    assert admin.put(f"/api/profiles/{p['id']}", json=body).status_code == 200
    return {"id": p["id"], "token": p["token"]}


def manual_with(admin, links: str) -> int:
    sid = admin.post("/api/sources", json={"kind": "manual", "name": "手动"}).json()["id"]
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": links})
    return sid


def proxy_names(resp) -> list[str]:
    return [p["name"] for p in yaml.safe_load(resp.text)["proxies"]]


def test_unknown_token_is_404(client):
    assert client.get("/sub/does-not-exist").status_code == 404


def test_returns_yaml_and_headers_without_login(admin):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    admin.post("/api/auth/logout", json={})

    resp = admin.get(f"/sub/{p['token']}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/yaml")
    assert resp.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote('我的方案')}.yaml"
    assert resp.headers["profile-update-interval"] == "24"
    assert "subscription-userinfo" not in resp.headers
    assert proxy_names(resp) == ["香港 01"]


def test_userinfo_only_when_all_nodes_from_one_subscription(admin, routes):
    routes[SUB_URL] = httpx.Response(200, text=SS_HK,
                                     headers={"subscription-userinfo": "upload=1; download=2; total=3; expire=4"})
    admin.post("/api/sources", json={"kind": "subscription", "name": "机场", "url": SUB_URL})
    p = make_profile(admin)
    first = admin.get(f"/sub/{p['token']}")
    assert first.headers["subscription-userinfo"] == "upload=1; download=2; total=3; expire=4"

    manual_with(admin, "trojan://pw@a.example.com:443#B")  # 导入会让缓存失效
    second = admin.get(f"/sub/{p['token']}")
    assert "subscription-userinfo" not in second.headers
    assert proxy_names(second) == ["香港 01", "B"]


def test_broken_profile_falls_back_to_last_good(admin):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    good = admin.get(f"/sub/{p['token']}")
    assert good.status_code == 200

    admin.put(f"/api/profiles/{p['id']}", json={**GOOD, "rules": []})
    fallback = admin.get(f"/sub/{p['token']}")
    assert fallback.status_code == 200
    assert fallback.text == good.text
    assert admin.get(f"/api/profiles/{p['id']}").json()["last_good_at"] is not None


def test_broken_profile_without_history_is_500(admin):
    p = make_profile(admin, {**GOOD, "rules": []})
    resp = admin.get(f"/sub/{p['token']}")
    assert resp.status_code == 500
    assert "管理界面" in resp.text


def test_rotated_token_invalidates_old_link(admin):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    new_token = admin.post(f"/api/profiles/{p['id']}/rotate-token", json={}).json()["token"]
    assert admin.get(f"/sub/{p['token']}").status_code == 404
    assert admin.get(f"/sub/{new_token}").status_code == 200


def test_unknown_target_is_400(admin):
    p = make_profile(admin)
    assert admin.get(f"/sub/{p['token']}", params={"target": "surge"}).status_code == 400


def test_cache_is_used_and_invalidated_by_writes(admin, app):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    admin.get(f"/sub/{p['token']}")
    assert app.state.cache.get((p["id"], "mihomo")) is not None

    node_ids = [n["id"] for n in admin.get("/api/nodes").json()]
    admin.post("/api/nodes/bulk", json={"ids": node_ids, "enabled": False})
    assert app.state.cache.get((p["id"], "mihomo")) is None
    assert proxy_names(admin.get(f"/sub/{p['token']}")) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_api_subscribe.py -v`
Expected: FAIL（`/sub/...` 404 断言以外的用例失败）

- [ ] **Step 3: 实现 `backend/routeforge/api/subscribe.py`**

```python
"""公开订阅接口：客户端用 token 拉取渲染后的配置。"""

from dataclasses import dataclass
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session, select

from routeforge.api.deps import CacheDep, SessionDep
from routeforge.cache import RenderCache
from routeforge.db.models import ProfileRow, Source, utcnow
from routeforge.renderers import RENDERERS
from routeforge.services.render import render_profile
from routeforge.sources.fetch import format_userinfo

router = APIRouter(tags=["subscribe"])


@dataclass(frozen=True)
class CachedSub:
    content: str
    content_type: str
    file_ext: str
    userinfo: str | None


@router.get("/sub/{token}")
def subscribe(token: str, session: SessionDep, cache: CacheDep, target: str = "mihomo") -> Response:
    row = session.exec(select(ProfileRow).where(ProfileRow.token == token)).first()
    if row is None:
        raise HTTPException(status_code=404)
    if target not in RENDERERS:
        raise HTTPException(status_code=400, detail=f"不支持的目标格式：{target}")

    key = (row.id, target)
    sub = cache.get(key) or _render_or_fallback(session, row, target, cache, key)
    if sub is None:
        return PlainTextResponse("方案配置有误且没有可用的历史版本，请在管理界面检查方案", status_code=500)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.name, safe='')}.{sub.file_ext}",
        "profile-update-interval": "24",
    }
    if sub.userinfo:
        headers["subscription-userinfo"] = sub.userinfo
    return Response(content=sub.content, media_type=sub.content_type, headers=headers)


def _render_or_fallback(session: Session, row: ProfileRow, target: str, cache: RenderCache, key) -> CachedSub | None:
    outcome = render_profile(session, row.to_profile(), target)
    if outcome.result is not None:
        r = outcome.result
        row.last_good = {**(row.last_good or {}),
                         target: {"content": r.content, "content_type": r.content_type, "file_ext": r.file_ext}}
        row.last_good_at = utcnow()
        session.add(row)
        session.commit()
        sub = CachedSub(r.content, r.content_type, r.file_ext, _userinfo_header(session, outcome.source_ids))
        cache.put(key, sub)
        return sub
    saved = (row.last_good or {}).get(target)
    if saved is None:
        return None
    return CachedSub(saved["content"], saved["content_type"], saved["file_ext"], None)


def _userinfo_header(session: Session, source_ids: list[int]) -> str | None:
    if len(source_ids) != 1:
        return None
    source = session.get(Source, source_ids[0])
    if source is None or not source.userinfo:
        return None
    return format_userinfo(source.userinfo)
```

- [ ] **Step 4: 在 `app.py` 注册路由**

导入追加 `from routeforge.api import subscribe as subscribe_api`，`include_router` 区追加：

```python
    app.include_router(subscribe_api.router)
```

- [ ] **Step 5: 运行确认通过**

Run: `uv run pytest -v`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add backend/routeforge/api/subscribe.py backend/routeforge/app.py backend/tests/test_api_subscribe.py
git commit -m "feat(api): serve rendered subscriptions with cache and last-good fallback"
```

### Task 8: 启动入口与端到端冒烟测试

**Files:**
- Create: `backend/routeforge/__main__.py`
- Modify: `backend/pyproject.toml`（`[project.scripts]`）
- Test: `backend/tests/test_main.py`

**Interfaces:**
- Consumes: Task 4 `create_app`、`ConfigError`；Task 1 `Settings.from_env`
- Produces: `routeforge.__main__.main() -> None`；命令 `uv run routeforge` / `python -m routeforge`

- [ ] **Step 1: 写失败测试 `backend/tests/test_main.py`**

```python
import pytest

from routeforge import __main__ as entry


def test_exits_with_message_when_admin_password_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROUTEFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ROUTEFORGE_ADMIN_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 1
    assert "ROUTEFORGE_ADMIN_PASSWORD" in capsys.readouterr().err


def test_runs_uvicorn_with_proxy_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTEFORGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ROUTEFORGE_ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("ROUTEFORGE_PORT", "9000")
    calls: dict = {}
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: calls.update(kw, app=app))
    entry.main()
    assert calls["port"] == 9000 and calls["host"] == "0.0.0.0"
    assert calls["proxy_headers"] is True and calls["forwarded_allow_ips"] == "127.0.0.1"
    assert (tmp_path / "routeforge.db").exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL（`ImportError: cannot import name '__main__'` 或 `AttributeError: main`）

- [ ] **Step 3: 实现 `backend/routeforge/__main__.py`**

```python
"""启动入口：python -m routeforge"""

import logging
import os
import sys

import uvicorn

from routeforge.app import create_app
from routeforge.auth import ConfigError
from routeforge.config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        app = create_app(Settings.from_env())
    except ConfigError as e:
        print(f"启动失败：{e}", file=sys.stderr)
        raise SystemExit(1) from e
    uvicorn.run(
        app,
        host=os.environ.get("ROUTEFORGE_HOST", "0.0.0.0"),
        port=int(os.environ.get("ROUTEFORGE_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("ROUTEFORGE_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
```

在 `backend/pyproject.toml` 的 `[project]` 之后加入：

```toml
[project.scripts]
routeforge = "routeforge.__main__:main"
```

Run: `uv sync`

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest -v`
Expected: 全部 passed

- [ ] **Step 5: 端到端冒烟测试（手动，bash）**

在 `backend/` 下启动服务（后台运行）：

```bash
ROUTEFORGE_ADMIN_PASSWORD=pw ROUTEFORGE_DATA_DIR=./data ROUTEFORGE_COOKIE_SECURE=false uv run routeforge
```

另一个终端：

```bash
J='Content-Type: application/json'
curl -s -c jar -H "$J" -d '{"password":"pw"}' localhost:8000/api/auth/login
SID=$(curl -s -b jar -H "$J" -d '{"kind":"manual","name":"手动"}' localhost:8000/api/sources | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -b jar -H "$J" -d '{"text":"ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#HK"}' localhost:8000/api/sources/$SID/nodes/import
PID=$(curl -s -b jar -H "$J" -d '{"name":"测试"}' localhost:8000/api/profiles | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
for t in ads ai cn-direct final; do curl -s -b jar -H "$J" -d "{\"template_id\":\"$t\"}" localhost:8000/api/profiles/$PID/apply-template > /dev/null; done
curl -s -b jar localhost:8000/api/profiles/$PID/preview | python -c "import sys,json;d=json.load(sys.stdin);print(d['ok'],d['errors'],d['warnings'])"
TOKEN=$(curl -s -b jar localhost:8000/api/profiles/$PID | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -D - localhost:8000/sub/$TOKEN | head -20
```

Expected：预览 `ok=True`、`errors=[]`，警告中有「节点选择」为空已补 DIRECT；订阅响应 200，响应头含 `content-disposition` 与 `profile-update-interval: 24`，正文为 Mihomo YAML。完成后停止服务并删除 `backend/data/` 与 `backend/jar`。

- [ ] **Step 6: 提交**

```bash
git add backend/routeforge/__main__.py backend/pyproject.toml backend/uv.lock backend/tests/test_main.py
git commit -m "feat(server): add command-line entry point"
```

---

## P2 完成标准

- `cd backend && uv run pytest` 全部通过
- 冒烟测试中 `/sub/{token}` 返回可被 Mihomo 加载的 YAML（若有条件，可用 Clash Verge Rev 导入该链接验证）
