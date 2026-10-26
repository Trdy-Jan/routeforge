# RouteForge P1 核心库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 RouteForge 的纯 Python 核心库：节点中间模型（IR）、分享链接与订阅解析、方案解析（resolver）、Mihomo 渲染器、内置分流模板。

**Architecture:** 所有输入解析为 Pydantic IR（`routeforge.ir`）；`resolver.resolve()` 把方案 + 节点库展开、校验为 `ResolvedProfile`；渲染器只依赖 `ResolvedProfile` 输出目标格式文本。本计划不含数据库、HTTP、前端（见 P2、P3）。

**Tech Stack:** Python 3.12、uv、Pydantic v2、PyYAML、pytest

**Spec:** `docs/superpowers/specs/2026-10-26-routeforge-design.md`

**系列计划：** P1 核心库（本文）→ P2 服务端（`2026-10-27-routeforge-p2-server.md`）→ P3 前端与 Docker（`2026-10-27-routeforge-p3-frontend-docker.md`）

## Global Constraints

- Python `>=3.12`；依赖管理用 uv，项目根为 `backend/`，所有命令在 `backend/` 目录下执行（`uv run pytest ...`）
- 支持协议：ss、vmess、vless（含 Reality）、trojan、hysteria2、tuic
- 第一期唯一渲染目标：`mihomo`
- 面向用户的错误 / 警告信息使用中文（前端直接展示）
- 渲染输出必须确定（同输入 → 逐字节相同输出），YAML 用 `allow_unicode=True, sort_keys=False`
- 解析失败一律抛 `routeforge.parsers.errors.ParseError`（`ValueError` 子类），不得让 `KeyError` / `json.JSONDecodeError` / pydantic `ValidationError` 漏出解析器公开函数
- 内置模板规则集统一使用 MetaCubeX meta-rules-dat：`https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/{geosite|geoip}/<name>.mrs`
- 传输层：IR 中 `transport=None` 表示 tcp（不存在 `Transport(type="tcp")`）
- 与 spec 的偏差：Mihomo 渲染测试用「解析后的结构等值断言」代替 golden 文件（同样确定、且计划中可直接审阅）

## Review Focus

1. **节点名含中文 / emoji / 空格且经 URL 编码** → 解码为原文，再编码后往返一致（Task 2、Task 3 测试）
2. **机场 Base64 订阅无填充、urlsafe 字符、CRLF 换行** → 正常解析出全部节点（Task 6 测试）
3. **IPv6 服务器地址 `[2001:db8::1]:443`** → IR 中不带方括号，生成链接时补回方括号（Task 2、Task 3 测试）
4. **过滤器正则写错（如 `(`）** → resolver 返回中文错误而非抛异常（Task 7 测试）
5. **节点名与分组名或其他节点重名** → 自动追加 ` 2` 后缀，分组成员与 `dialer-proxy` 引用同步更新（Task 7 测试）

## File Structure

```
backend/
  pyproject.toml
  routeforge/
    __init__.py
    ir/
      __init__.py
      node.py          Node 判别联合 + TLSOptions/Reality/Transport
      profile.py       Profile、ProxyGroup、成员类型、Rule、RuleProvider、Chain
      resolved.py      ResolvedGroup、ResolvedProfile（渲染器输入）
    parsers/
      __init__.py
      errors.py        ParseError、UnsupportedNode
      uri/
        __init__.py    parse_uri / to_uri / parse_many 分发
        _common.py     base64、host:port、query、TLS/传输层 query 互转
        ss.py trojan.py vless.py vmess.py hysteria2.py tuic.py
      clash_proxy.py   Clash/Mihomo proxy dict <-> Node
      subscription.py  订阅内容格式识别与解析
    resolver.py        LibraryNode、ResolveResult、resolve()
    renderers/
      __init__.py      get_renderer()
      base.py          Renderer 协议、RenderResult
      mihomo.py
    templates/
      __init__.py      Template、load_templates()、apply_template()
      ads.yaml ai.yaml streaming.yaml telegram.yaml cn-direct.yaml final.yaml
  tests/
    test_ir_node.py test_uri_ss.py test_uri_trojan_vless.py test_uri_vmess_hy2_tuic.py
    test_clash_proxy.py test_subscription.py test_resolver.py test_mihomo.py test_templates.py
```

---

### Task 1: 项目骨架 + 节点 IR

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/routeforge/__init__.py`（空）
- Create: `backend/routeforge/ir/__init__.py`（空）
- Create: `backend/routeforge/ir/node.py`
- Test: `backend/tests/test_ir_node.py`

**Interfaces:**
- Produces: `routeforge.ir.node` 中的 `Reality`、`TLSOptions`、`Transport`、`SSNode`、`VmessNode`、`VlessNode`、`TrojanNode`、`Hysteria2Node`、`TuicNode`、`Node`（判别联合类型别名）、`NodeAdapter: TypeAdapter[Node]`

- [ ] **Step 1: 创建 `backend/pyproject.toml`**

```toml
[project]
name = "routeforge"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.9",
    "pyyaml>=6.0",
]

[dependency-groups]
dev = ["pytest>=8.3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["routeforge"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

创建空文件 `backend/routeforge/__init__.py`、`backend/routeforge/ir/__init__.py`，然后：

Run: `cd backend && uv sync`
Expected: 创建 `.venv` 并安装 pydantic、pyyaml、pytest

- [ ] **Step 2: 写失败测试 `backend/tests/test_ir_node.py`**

```python
import pytest
from pydantic import ValidationError

from routeforge.ir.node import NodeAdapter, Reality, SSNode, TLSOptions, Transport, VlessNode


def test_discriminated_union_picks_class_by_type():
    node = NodeAdapter.validate_python(
        {"type": "ss", "name": "a", "server": "1.1.1.1", "port": 8388, "cipher": "aes-128-gcm", "password": "p"}
    )
    assert isinstance(node, SSNode)
    assert node.udp is True
    assert node.tls is None and node.transport is None and node.via is None


def test_vless_reality_json_roundtrip():
    node = VlessNode(
        name="R",
        server="ex.com",
        port=443,
        uuid="u",
        flow="xtls-rprx-vision",
        tls=TLSOptions(sni="www.apple.com", fingerprint="chrome", reality=Reality(public_key="pk", short_id="ab")),
        transport=Transport(type="grpc", service_name="gun"),
    )
    assert NodeAdapter.validate_json(NodeAdapter.dump_json(node)) == node


def test_port_out_of_range_rejected():
    with pytest.raises(ValidationError):
        SSNode(name="a", server="h", port=70000, cipher="c", password="p")


def test_tcp_is_not_a_transport_type():
    with pytest.raises(ValidationError):
        Transport(type="tcp")
```

- [ ] **Step 3: 运行确认失败**

Run: `uv run pytest tests/test_ir_node.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.ir.node'`）

- [ ] **Step 4: 实现 `backend/routeforge/ir/node.py`**

```python
"""节点中间模型（IR）。所有输入格式解析到这里，所有渲染器从这里输出。"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter


class Reality(BaseModel):
    public_key: str
    short_id: str = ""


class TLSOptions(BaseModel):
    sni: str | None = None
    alpn: list[str] = []
    insecure: bool = False
    fingerprint: str | None = None
    reality: Reality | None = None


class Transport(BaseModel):
    """非 tcp 传输层；tcp 用 Node.transport = None 表示。"""

    type: Literal["ws", "grpc", "h2", "httpupgrade"]
    path: str | None = None
    host: str | None = None
    service_name: str | None = None


class NodeBase(BaseModel):
    name: str
    server: str
    port: int = Field(ge=1, le=65535)
    udp: bool = True
    tls: TLSOptions | None = None
    transport: Transport | None = None
    # 仅由 resolver 写入：本节点经由哪个分组 / 节点（最终名称）出站
    via: str | None = None
    extra: dict = {}


class SSNode(NodeBase):
    type: Literal["ss"] = "ss"
    cipher: str
    password: str
    plugin: Literal["obfs", "v2ray-plugin"] | None = None
    plugin_opts: dict[str, str | bool] = {}


class VmessNode(NodeBase):
    type: Literal["vmess"] = "vmess"
    uuid: str
    alter_id: int = 0
    cipher: str = "auto"


class VlessNode(NodeBase):
    type: Literal["vless"] = "vless"
    uuid: str
    flow: str | None = None


class TrojanNode(NodeBase):
    type: Literal["trojan"] = "trojan"
    password: str
    tls: TLSOptions | None = Field(default_factory=TLSOptions)


class Hysteria2Node(NodeBase):
    type: Literal["hysteria2"] = "hysteria2"
    password: str
    obfs: str | None = None
    obfs_password: str | None = None
    up: str | None = None
    down: str | None = None
    tls: TLSOptions | None = Field(default_factory=TLSOptions)


class TuicNode(NodeBase):
    type: Literal["tuic"] = "tuic"
    uuid: str
    password: str
    congestion_control: str | None = None
    tls: TLSOptions | None = Field(default_factory=TLSOptions)


Node = Annotated[
    Union[SSNode, VmessNode, VlessNode, TrojanNode, Hysteria2Node, TuicNode],
    Field(discriminator="type"),
]

NodeAdapter: TypeAdapter[Node] = TypeAdapter(Node)
```

- [ ] **Step 5: 运行确认通过**

Run: `uv run pytest tests/test_ir_node.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

先在仓库根 `.gitignore` 确认已包含 `.venv/`（已有），然后：

```bash
git add backend/pyproject.toml backend/uv.lock backend/routeforge backend/tests/test_ir_node.py
git commit -m "feat(core): scaffold backend and node IR models"
```

### Task 2: 解析器基础设施 + Shadowsocks 分享链接

**Files:**
- Create: `backend/routeforge/parsers/__init__.py`（空）
- Create: `backend/routeforge/parsers/errors.py`
- Create: `backend/routeforge/parsers/uri/_common.py`
- Create: `backend/routeforge/parsers/uri/ss.py`
- Create: `backend/routeforge/parsers/uri/__init__.py`
- Test: `backend/tests/test_uri_ss.py`

**Interfaces:**
- Consumes: `routeforge.ir.node.SSNode`、`Node`
- Produces:
  - `routeforge.parsers.errors.ParseError(ValueError)`、`UnsupportedNode(Exception)`
  - `_common`: `b64decode_loose(data: str) -> str`、`b64encode_text(text: str, *, urlsafe: bool = False, padding: bool = True) -> str`、`split_hostport(hp: str) -> tuple[str, int]`、`host_for_uri(server: str) -> str`、`StdParts(userinfo, server, port, query: dict[str, str], name)`、`split_standard(uri: str) -> StdParts`、`build_uri(scheme, userinfo, server, port, params: dict[str, str], name) -> str`（userinfo 由调用方先转义）
  - 每个协议模块：`parse(uri: str) -> <XxxNode>`、`dump(node: <XxxNode>) -> str`
  - `routeforge.parsers.uri`: `parse_uri(uri: str) -> Node`、`to_uri(node: Node) -> str`、`parse_many(text: str) -> ParseOutcome`、`ParseOutcome(nodes: list[Node], errors: list[LineError])`、`LineError(line: str, message: str)`

- [ ] **Step 1: 写失败测试 `backend/tests/test_uri_ss.py`**

```python
import pytest

from routeforge.ir.node import SSNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_many, parse_uri, to_uri
from routeforge.parsers.uri import ss


def test_sip002_base64_userinfo_and_chinese_name():
    node = ss.parse("ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#%E9%A6%99%E6%B8%AF%2001")
    assert node == SSNode(name="香港 01", server="1.2.3.4", port=8388, cipher="aes-256-gcm", password="test")


def test_legacy_fully_base64_encoded():
    node = ss.parse("ss://YWVzLTEyOC1nY206cHdAZXhhbXBsZS5jb206NDQz#Legacy")
    assert (node.cipher, node.password, node.server, node.port, node.name) == (
        "aes-128-gcm", "pw", "example.com", 443, "Legacy",
    )


def test_plain_userinfo_2022_cipher_with_ipv6():
    node = ss.parse(
        "ss://2022-blake3-aes-128-gcm:YctPZ6U7xPPcU%2Bgp3u%2B0tx%2FtRizJN9K8y%2BuKlW2qjlI%3D@[2001:db8::1]:443#v6"
    )
    assert node.server == "2001:db8::1"
    assert node.password == "YctPZ6U7xPPcU+gp3u+0tx/tRizJN9K8y+uKlW2qjlI="


def test_obfs_plugin():
    node = ss.parse(
        "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388/?plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dbing.com#O"
    )
    assert node.plugin == "obfs"
    assert node.plugin_opts == {"mode": "http", "host": "bing.com"}


def test_missing_name_falls_back_to_host_port():
    assert ss.parse("ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388").name == "1.2.3.4:8388"


@pytest.mark.parametrize(
    "node",
    [
        SSNode(name="香港 01", server="1.2.3.4", port=8388, cipher="aes-256-gcm", password="p@ss:word"),
        SSNode(name="v6", server="2001:db8::1", port=443, cipher="aes-128-gcm", password="x"),
        SSNode(name="O", server="h.com", port=1, cipher="aes-128-gcm", password="x",
               plugin="obfs", plugin_opts={"mode": "tls", "host": "bing.com"}),
        SSNode(name="V", server="h.com", port=1, cipher="aes-128-gcm", password="x",
               plugin="v2ray-plugin", plugin_opts={"mode": "websocket", "tls": True, "host": "a.com", "path": "/ws"}),
    ],
)
def test_dump_parse_roundtrip(node):
    uri = ss.dump(node)
    assert ss.parse(uri) == node
    if node.server == "2001:db8::1":
        assert "@[2001:db8::1]:443" in uri


@pytest.mark.parametrize(
    "bad",
    ["ss://", "ss://!!!notbase64", "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:notaport#x",
     "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388/?plugin=kcptun#x"],
)
def test_malformed_raises_parse_error(bad):
    with pytest.raises(ParseError):
        ss.parse(bad)


def test_dispatcher_routes_by_scheme_and_rejects_unknown():
    assert isinstance(parse_uri("  ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B  "), SSNode)
    with pytest.raises(ParseError, match="不支持的协议"):
        parse_uri("socks5://1.2.3.4:1080")
    with pytest.raises(ParseError):
        parse_uri("not a link")


def test_to_uri_dispatches_by_node_type():
    node = SSNode(name="a", server="h.com", port=1, cipher="aes-128-gcm", password="x")
    assert to_uri(node).startswith("ss://")


def test_parse_many_skips_blank_and_comment_lines_and_collects_errors():
    text = "\n# comment\nss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#A\r\nss://broken\n\n"
    outcome = parse_many(text)
    assert [n.name for n in outcome.nodes] == ["A"]
    assert len(outcome.errors) == 1
    assert outcome.errors[0].line == "ss://broken"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_uri_ss.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.parsers'`）

- [ ] **Step 3: 实现 `backend/routeforge/parsers/errors.py`**

```python
class ParseError(ValueError):
    """输入（分享链接 / 订阅 / Clash proxy）无法解析为 IR。"""


class UnsupportedNode(Exception):
    """IR 节点包含目标格式无法表达的内容。"""
```

- [ ] **Step 4: 实现 `backend/routeforge/parsers/uri/_common.py`**

```python
"""分享链接解析的通用工具。"""

import base64
from typing import NamedTuple
from urllib.parse import parse_qs, quote, unquote, urlencode

from routeforge.parsers.errors import ParseError


def b64decode_loose(data: str) -> str:
    """容忍缺失填充、urlsafe 字符和换行的 base64 解码。"""
    s = "".join(data.split()).replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as e:
        raise ParseError(f"base64 解码失败：{e}") from e


def b64encode_text(text: str, *, urlsafe: bool = False, padding: bool = True) -> str:
    raw = text.encode("utf-8")
    out = (base64.urlsafe_b64encode(raw) if urlsafe else base64.b64encode(raw)).decode("ascii")
    return out if padding else out.rstrip("=")


def split_hostport(hp: str) -> tuple[str, int]:
    if hp.startswith("["):
        host, _, rest = hp[1:].partition("]")
        port_s = rest.removeprefix(":")
    else:
        host, _, port_s = hp.rpartition(":")
    if not host or not port_s.isdigit():
        raise ParseError(f"无效的地址或端口：{hp}")
    port = int(port_s)
    if not 1 <= port <= 65535:
        raise ParseError(f"端口超出范围：{port}")
    return host, port


def host_for_uri(server: str) -> str:
    return f"[{server}]" if ":" in server else server


class StdParts(NamedTuple):
    userinfo: str
    server: str
    port: int
    query: dict[str, str]
    name: str


def split_standard(uri: str) -> StdParts:
    """拆分 scheme://userinfo@host:port/?query#name 形式的链接（userinfo / name 已解码）。"""
    _, sep, rest = uri.strip().partition("://")
    if not sep:
        raise ParseError("不是分享链接")
    rest, _, frag = rest.partition("#")
    rest, _, qs = rest.partition("?")
    userinfo, at, hostport = rest.rstrip("/").rpartition("@")
    if not at or not userinfo:
        raise ParseError("缺少认证信息（@ 之前的部分）")
    server, port = split_hostport(hostport)
    query = {k: v[-1] for k, v in parse_qs(qs, keep_blank_values=True).items()}
    return StdParts(unquote(userinfo), server, port, query, unquote(frag))


def build_uri(scheme: str, userinfo: str, server: str, port: int, params: dict[str, str], name: str) -> str:
    uri = f"{scheme}://{userinfo}@{host_for_uri(server)}:{port}"
    if params:
        uri += "?" + urlencode(params, quote_via=quote)
    return uri + "#" + quote(name, safe="")
```

- [ ] **Step 5: 实现 `backend/routeforge/parsers/uri/ss.py`**

```python
"""Shadowsocks：SIP002（ss://b64(method:pass)@host:port/?plugin=...#name）与旧式全 base64 格式。"""

from urllib.parse import parse_qs, quote, unquote

from routeforge.ir.node import SSNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import b64decode_loose, b64encode_text, host_for_uri, split_hostport


def parse(uri: str) -> SSNode:
    body = uri.strip().removeprefix("ss://")
    body, _, frag = body.partition("#")
    main, _, qs = body.partition("?")
    main = main.rstrip("/")
    if "@" in main:
        userinfo, _, hostport = main.rpartition("@")
        userinfo = unquote(userinfo)
        if ":" not in userinfo:
            userinfo = b64decode_loose(userinfo)
    else:
        userinfo, _, hostport = b64decode_loose(main).rpartition("@")
    cipher, sep, password = userinfo.partition(":")
    if not sep or not cipher:
        raise ParseError("ss：缺少 加密方式:密码")
    server, port = split_hostport(hostport)
    params = {k: v[-1] for k, v in parse_qs(qs).items()}
    plugin, opts = _parse_plugin(params.get("plugin", ""))
    return SSNode(
        name=unquote(frag) or f"{server}:{port}",
        server=server,
        port=port,
        cipher=cipher,
        password=password,
        plugin=plugin,
        plugin_opts=opts,
    )


def dump(node: SSNode) -> str:
    userinfo = b64encode_text(f"{node.cipher}:{node.password}", urlsafe=True, padding=False)
    uri = f"ss://{userinfo}@{host_for_uri(node.server)}:{node.port}"
    if node.plugin:
        uri += "/?plugin=" + quote(_dump_plugin(node), safe="")
    return uri + "#" + quote(node.name, safe="")


def _parse_plugin(raw: str) -> tuple[str | None, dict[str, str | bool]]:
    if not raw:
        return None, {}
    name, *parts = raw.split(";")
    opts: dict[str, str | bool] = {}
    for part in parts:
        key, sep, value = part.partition("=")
        opts[key] = value if sep else True
    if name in ("obfs-local", "simple-obfs", "obfs"):
        out: dict[str, str | bool] = {"mode": opts.get("obfs", "http")}
        if opts.get("obfs-host"):
            out["host"] = opts["obfs-host"]
        return "obfs", out
    if name == "v2ray-plugin":
        out = {"mode": opts.get("mode", "websocket")}
        if opts.get("tls"):
            out["tls"] = True
        for key in ("host", "path"):
            if opts.get(key):
                out[key] = opts[key]
        return "v2ray-plugin", out
    raise ParseError(f"ss：不支持的插件 {name}")


def _dump_plugin(node: SSNode) -> str:
    o = node.plugin_opts
    if node.plugin == "obfs":
        parts = ["obfs-local", f"obfs={o.get('mode', 'http')}"]
        if o.get("host"):
            parts.append(f"obfs-host={o['host']}")
    else:
        parts = ["v2ray-plugin", f"mode={o.get('mode', 'websocket')}"]
        if o.get("tls"):
            parts.append("tls")
        parts += [f"{k}={o[k]}" for k in ("host", "path") if o.get(k)]
    return ";".join(parts)
```

- [ ] **Step 6: 实现 `backend/routeforge/parsers/uri/__init__.py`**

```python
"""分享链接解析入口：按 scheme 分发到各协议模块。"""

from dataclasses import dataclass, field
from typing import Callable

from routeforge.ir.node import Node
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import ss

_PARSERS: dict[str, Callable[[str], Node]] = {
    "ss": ss.parse,
}

_DUMPERS: dict[str, Callable] = {
    "ss": ss.dump,
}


@dataclass
class LineError:
    line: str
    message: str


@dataclass
class ParseOutcome:
    nodes: list[Node] = field(default_factory=list)
    errors: list[LineError] = field(default_factory=list)


def parse_uri(uri: str) -> Node:
    uri = uri.strip()
    scheme, sep, _ = uri.partition("://")
    if not sep:
        raise ParseError("不是分享链接")
    parser = _PARSERS.get(scheme.lower())
    if parser is None:
        raise ParseError(f"不支持的协议：{scheme}")
    try:
        return parser(uri)
    except ParseError:
        raise
    except (ValueError, KeyError, TypeError) as e:  # 包括 pydantic ValidationError
        raise ParseError(f"{scheme}：{e}") from e


def to_uri(node: Node) -> str:
    return _DUMPERS[node.type](node)


def parse_many(text: str) -> ParseOutcome:
    outcome = ParseOutcome()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            outcome.nodes.append(parse_uri(line))
        except ParseError as e:
            outcome.errors.append(LineError(line=line, message=str(e)))
    return outcome
```

- [ ] **Step 7: 运行确认通过**

Run: `uv run pytest tests/test_uri_ss.py -v`
Expected: 全部 passed

- [ ] **Step 8: 提交**

```bash
git add backend/routeforge/parsers backend/tests/test_uri_ss.py
git commit -m "feat(parsers): add share-link infrastructure and shadowsocks parser"
```

### Task 3: Trojan + VLESS 分享链接（TLS / Reality / 传输层）

**Files:**
- Modify: `backend/routeforge/parsers/uri/_common.py`（追加 TLS / 传输层 query 互转）
- Create: `backend/routeforge/parsers/uri/trojan.py`
- Create: `backend/routeforge/parsers/uri/vless.py`
- Modify: `backend/routeforge/parsers/uri/__init__.py`（注册）
- Test: `backend/tests/test_uri_trojan_vless.py`

**Interfaces:**
- Consumes: Task 2 的 `split_standard`、`build_uri`、`ParseError`；Task 1 的 `TrojanNode`、`VlessNode`、`TLSOptions`、`Reality`、`Transport`
- Produces（`_common`）：`tls_from_query(q: dict[str, str], *, default_on: bool) -> TLSOptions | None`、`tls_to_query(tls: TLSOptions | None) -> dict[str, str]`、`transport_from_query(q: dict[str, str]) -> Transport | None`、`transport_to_query(tr: Transport | None) -> dict[str, str]`；`trojan.parse/dump`、`vless.parse/dump`

- [ ] **Step 1: 写失败测试 `backend/tests/test_uri_trojan_vless.py`**

```python
import pytest

from routeforge.ir.node import Reality, TLSOptions, Transport, TrojanNode, VlessNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_uri, to_uri
from routeforge.parsers.uri import trojan, vless

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"


def test_trojan_ipv6_ws_emoji_name_and_encoded_password():
    node = trojan.parse(
        "trojan://pa%40ss@[2001:db8::1]:443?sni=a.com&type=ws&path=%2Fws&host=a.com"
        "#%F0%9F%87%AD%F0%9F%87%B0%20HK"
    )
    assert node == TrojanNode(
        name="🇭🇰 HK",
        server="2001:db8::1",
        port=443,
        password="pa@ss",
        tls=TLSOptions(sni="a.com"),
        transport=Transport(type="ws", path="/ws", host="a.com"),
    )


def test_trojan_peer_alias_and_allow_insecure():
    node = trojan.parse("trojan://pw@a.com:443?peer=b.com&allowInsecure=1#P")
    assert node.tls == TLSOptions(sni="b.com", insecure=True)
    assert node.transport is None


def test_vless_reality_vision():
    node = vless.parse(
        f"vless://{UUID}@ex.com:443?encryption=none&flow=xtls-rprx-vision&security=reality"
        "&sni=www.apple.com&fp=chrome&pbk=PUBKEY&sid=6ba8&type=tcp#R"
    )
    assert node == VlessNode(
        name="R",
        server="ex.com",
        port=443,
        uuid=UUID,
        flow="xtls-rprx-vision",
        tls=TLSOptions(sni="www.apple.com", fingerprint="chrome", reality=Reality(public_key="PUBKEY", short_id="6ba8")),
    )


def test_vless_without_security_has_no_tls_and_http_type_maps_to_h2():
    node = vless.parse(f"vless://{UUID}@ex.com:80?type=http&path=%2Fh2&host=ex.com#H")
    assert node.tls is None
    assert node.transport == Transport(type="h2", path="/h2", host="ex.com")


@pytest.mark.parametrize(
    "node",
    [
        TrojanNode(name="🇭🇰 HK", server="2001:db8::1", port=443, password="pa@ss",
                   tls=TLSOptions(sni="a.com", alpn=["h2", "http/1.1"]),
                   transport=Transport(type="ws", path="/ws", host="a.com")),
        TrojanNode(name="plain", server="a.com", port=443, password="pw"),
        VlessNode(name="R", server="ex.com", port=443, uuid=UUID, flow="xtls-rprx-vision",
                  tls=TLSOptions(sni="www.apple.com", fingerprint="chrome",
                                 reality=Reality(public_key="PUBKEY", short_id="6ba8"))),
        VlessNode(name="G", server="ex.com", port=443, uuid=UUID,
                  tls=TLSOptions(sni="ex.com", insecure=True), transport=Transport(type="grpc", service_name="gun")),
        VlessNode(name="W", server="ex.com", port=80, uuid=UUID, transport=Transport(type="httpupgrade", path="/up")),
    ],
)
def test_dump_parse_roundtrip(node):
    assert parse_uri(to_uri(node)) == node


@pytest.mark.parametrize(
    "bad",
    [
        f"vless://{UUID}@ex.com:443?type=kcp#x",
        f"vless://{UUID}@ex.com:443?security=reality&sni=a.com#x",
        "vless://@ex.com:443#x",
        "trojan://pw@a.com#noport",
        "trojan://pw@a.com:443?security=xyz#x",
    ],
)
def test_malformed_raises_parse_error(bad):
    with pytest.raises(ParseError):
        parse_uri(bad)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_uri_trojan_vless.py -v`
Expected: FAIL（`ImportError: cannot import name 'trojan'`）

- [ ] **Step 3: 在 `_common.py` 顶部导入处追加**

```python
from routeforge.ir.node import Reality, TLSOptions, Transport
```

并在文件末尾追加：

```python
_TRUTHY = {"1", "true", "True"}


def tls_from_query(q: dict[str, str], *, default_on: bool) -> TLSOptions | None:
    security = q.get("security") or ("tls" if default_on else "none")
    if security == "none":
        return None
    if security not in ("tls", "reality", "xtls"):
        raise ParseError(f"不支持的 security：{security}")
    reality = None
    if security == "reality":
        if not q.get("pbk"):
            raise ParseError("reality 缺少 pbk（公钥）")
        reality = Reality(public_key=q["pbk"], short_id=q.get("sid", ""))
    insecure = (q.get("allowInsecure") or q.get("insecure") or q.get("allow_insecure") or "") in _TRUTHY
    return TLSOptions(
        sni=q.get("sni") or q.get("peer") or None,
        alpn=[a for a in q.get("alpn", "").split(",") if a],
        insecure=insecure,
        fingerprint=q.get("fp") or None,
        reality=reality,
    )


def tls_to_query(tls: TLSOptions | None) -> dict[str, str]:
    if tls is None:
        return {"security": "none"}
    q = {"security": "reality" if tls.reality else "tls"}
    if tls.sni:
        q["sni"] = tls.sni
    if tls.alpn:
        q["alpn"] = ",".join(tls.alpn)
    if tls.insecure:
        q["allowInsecure"] = "1"
    if tls.fingerprint:
        q["fp"] = tls.fingerprint
    if tls.reality:
        q["pbk"] = tls.reality.public_key
        if tls.reality.short_id:
            q["sid"] = tls.reality.short_id
    return q


def transport_from_query(q: dict[str, str]) -> Transport | None:
    kind = q.get("type") or "tcp"
    if kind == "tcp":
        return None
    if kind == "http":  # xray 分享链接中 http 即 h2
        kind = "h2"
    if kind not in ("ws", "grpc", "h2", "httpupgrade"):
        raise ParseError(f"不支持的传输层：{kind}")
    return Transport(
        type=kind,
        path=q.get("path") or None,
        host=q.get("host") or None,
        service_name=q.get("serviceName") or None,
    )


def transport_to_query(tr: Transport | None) -> dict[str, str]:
    if tr is None:
        return {}
    q = {"type": tr.type}
    if tr.path:
        q["path"] = tr.path
    if tr.host:
        q["host"] = tr.host
    if tr.service_name:
        q["serviceName"] = tr.service_name
    return q
```

- [ ] **Step 4: 实现 `backend/routeforge/parsers/uri/trojan.py`**

```python
"""Trojan：trojan://password@host:port?sni=..&type=ws..#name（默认启用 TLS）。"""

from urllib.parse import quote

from routeforge.ir.node import TrojanNode
from routeforge.parsers.uri._common import (
    build_uri,
    split_standard,
    tls_from_query,
    tls_to_query,
    transport_from_query,
    transport_to_query,
)


def parse(uri: str) -> TrojanNode:
    p = split_standard(uri)
    return TrojanNode(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        password=p.userinfo,
        tls=tls_from_query(p.query, default_on=True),
        transport=transport_from_query(p.query),
    )


def dump(node: TrojanNode) -> str:
    params = {**tls_to_query(node.tls), **transport_to_query(node.transport)}
    if params.get("security") == "tls":
        del params["security"]
    return build_uri("trojan", quote(node.password, safe=""), node.server, node.port, params, node.name)
```

- [ ] **Step 5: 实现 `backend/routeforge/parsers/uri/vless.py`**

```python
"""VLESS：vless://uuid@host:port?security=tls|reality|none&type=..&flow=..#name。"""

from urllib.parse import quote

from routeforge.ir.node import VlessNode
from routeforge.parsers.uri._common import (
    build_uri,
    split_standard,
    tls_from_query,
    tls_to_query,
    transport_from_query,
    transport_to_query,
)


def parse(uri: str) -> VlessNode:
    p = split_standard(uri)
    return VlessNode(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        uuid=p.userinfo,
        flow=p.query.get("flow") or None,
        tls=tls_from_query(p.query, default_on=False),
        transport=transport_from_query(p.query),
    )


def dump(node: VlessNode) -> str:
    params = {"encryption": "none", **tls_to_query(node.tls), **transport_to_query(node.transport)}
    if node.flow:
        params["flow"] = node.flow
    return build_uri("vless", quote(node.uuid, safe=""), node.server, node.port, params, node.name)
```

- [ ] **Step 6: 在 `uri/__init__.py` 注册**

把 `from routeforge.parsers.uri import ss` 改为：

```python
from routeforge.parsers.uri import ss, trojan, vless
```

两个字典改为：

```python
_PARSERS: dict[str, Callable[[str], Node]] = {
    "ss": ss.parse,
    "trojan": trojan.parse,
    "vless": vless.parse,
}

_DUMPERS: dict[str, Callable] = {
    "ss": ss.dump,
    "trojan": trojan.dump,
    "vless": vless.dump,
}
```

- [ ] **Step 7: 运行确认通过（含之前的测试）**

Run: `uv run pytest -v`
Expected: 全部 passed

- [ ] **Step 8: 提交**

```bash
git add backend/routeforge/parsers backend/tests/test_uri_trojan_vless.py
git commit -m "feat(parsers): add trojan and vless share-link parsers"
```

### Task 4: VMess + Hysteria2 + TUIC 分享链接

**Files:**
- Create: `backend/routeforge/parsers/uri/vmess.py`
- Create: `backend/routeforge/parsers/uri/hysteria2.py`
- Create: `backend/routeforge/parsers/uri/tuic.py`
- Modify: `backend/routeforge/parsers/uri/__init__.py`（注册）
- Test: `backend/tests/test_uri_vmess_hy2_tuic.py`

**Interfaces:**
- Consumes: Task 2/3 的 `_common` 全部函数；Task 1 的 `VmessNode`、`Hysteria2Node`、`TuicNode`
- Produces: `vmess.parse/dump`、`hysteria2.parse/dump`、`tuic.parse/dump`；`parse_uri` 支持 scheme `vmess`、`hysteria2`、`hy2`、`tuic`

- [ ] **Step 1: 写失败测试 `backend/tests/test_uri_vmess_hy2_tuic.py`**

```python
import json

import pytest

from routeforge.ir.node import Hysteria2Node, TLSOptions, Transport, TuicNode, VmessNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_uri, to_uri
from routeforge.parsers.uri._common import b64encode_text

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"

VMESS_WS_TLS = (
    "vmess://eyJ2IjogIjIiLCAicHMiOiAi5pel5pysIDAxIiwgImFkZCI6ICJqcC5leGFtcGxlLmNvbSIsICJwb3J0IjogIjQ0MyIsICJp"
    "ZCI6ICJiODMxMzgxZC02MzI0LTRkNTMtYWQ0Zi04Y2RhNDhiMzA4MTEiLCAiYWlkIjogIjAiLCAic2N5IjogImF1dG8iLCAibmV0Ijog"
    "IndzIiwgInR5cGUiOiAibm9uZSIsICJob3N0IjogImpwLmV4YW1wbGUuY29tIiwgInBhdGgiOiAiL3JheSIsICJ0bHMiOiAidGxzIiwg"
    "InNuaSI6ICJqcC5leGFtcGxlLmNvbSJ9"
)


def test_vmess_ws_tls_with_chinese_name():
    assert parse_uri(VMESS_WS_TLS) == VmessNode(
        name="日本 01",
        server="jp.example.com",
        port=443,
        uuid=UUID,
        tls=TLSOptions(sni="jp.example.com"),
        transport=Transport(type="ws", path="/ray", host="jp.example.com"),
    )


def test_vmess_grpc_service_name_comes_from_path_field():
    payload = {"add": "a.com", "port": 443, "id": UUID, "net": "grpc", "path": "gun", "tls": "tls"}
    node = parse_uri("vmess://" + b64encode_text(json.dumps(payload)))
    assert node.transport == Transport(type="grpc", service_name="gun")
    assert node.name == "a.com:443"


def test_hysteria2_with_obfs_and_hy2_alias():
    uri = "hy2://pw@h.com:443?sni=a.com&insecure=1&obfs=salamander&obfs-password=x#H"
    assert parse_uri(uri) == Hysteria2Node(
        name="H", server="h.com", port=443, password="pw",
        obfs="salamander", obfs_password="x", tls=TLSOptions(sni="a.com", insecure=True),
    )
    assert isinstance(parse_uri(uri.replace("hy2://", "hysteria2://")), Hysteria2Node)


def test_tuic():
    node = parse_uri(f"tuic://{UUID}:pa%3Ass@h.com:443?congestion_control=bbr&alpn=h3&sni=a.com&allow_insecure=1#T")
    assert node == TuicNode(
        name="T", server="h.com", port=443, uuid=UUID, password="pa:ss",
        congestion_control="bbr", tls=TLSOptions(sni="a.com", alpn=["h3"], insecure=True),
    )


@pytest.mark.parametrize(
    "node",
    [
        VmessNode(name="日本 01", server="jp.example.com", port=443, uuid=UUID,
                  tls=TLSOptions(sni="jp.example.com", alpn=["h2"], fingerprint="chrome"),
                  transport=Transport(type="ws", path="/ray", host="jp.example.com")),
        VmessNode(name="tcp", server="1.2.3.4", port=10086, uuid=UUID, alter_id=64, cipher="aes-128-gcm"),
        VmessNode(name="g", server="a.com", port=443, uuid=UUID, tls=TLSOptions(),
                  transport=Transport(type="grpc", service_name="gun")),
        Hysteria2Node(name="H 🇯🇵", server="2001:db8::1", port=8443, password="p@ss",
                      obfs="salamander", obfs_password="x", tls=TLSOptions(sni="a.com", insecure=True)),
        TuicNode(name="T", server="h.com", port=443, uuid=UUID, password="pa:ss",
                 congestion_control="bbr", tls=TLSOptions(sni="a.com", alpn=["h3"])),
    ],
)
def test_dump_parse_roundtrip(node):
    assert parse_uri(to_uri(node)) == node


@pytest.mark.parametrize(
    "bad",
    [
        "vmess://!!!",
        "vmess://" + b64encode_text("[1, 2]"),
        "vmess://" + b64encode_text('{"port": "1", "id": "x"}'),
        "vmess://" + b64encode_text('{"add": "a", "port": "99999", "id": "x"}'),
        "vmess://" + b64encode_text('{"add": "a", "port": "1", "id": "x", "net": "kcp"}'),
        "hysteria2://pw@h.com:443,20000-30000#hop",
        f"tuic://{UUID}@h.com:443#nopassword",
    ],
)
def test_malformed_raises_parse_error(bad):
    with pytest.raises(ParseError):
        parse_uri(bad)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_uri_vmess_hy2_tuic.py -v`
Expected: FAIL（`ParseError: 不支持的协议：vmess` 等）

- [ ] **Step 3: 实现 `backend/routeforge/parsers/uri/vmess.py`**

```python
"""VMess：vmess://base64(json)，字段遵循 v2rayN 约定（grpc 的 serviceName 放在 path 字段）。"""

import json

from routeforge.ir.node import VmessNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import b64decode_loose, b64encode_text, tls_from_query, transport_from_query


def parse(uri: str) -> VmessNode:
    raw = b64decode_loose(uri.strip().removeprefix("vmess://"))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ParseError(f"vmess：JSON 无效：{e}") from e
    if not isinstance(data, dict):
        raise ParseError("vmess：内容不是 JSON 对象")
    try:
        server = str(data["add"])
        port = int(data["port"])
        uuid = str(data["id"])
    except (KeyError, ValueError) as e:
        raise ParseError(f"vmess：缺少或无效字段 {e}") from e
    net = str(data.get("net") or "tcp")
    tq = {"type": net, "path": str(data.get("path") or ""), "host": str(data.get("host") or "")}
    if net == "grpc":
        tq["serviceName"] = tq.pop("path")
    tls_q = {
        "security": "tls" if data.get("tls") == "tls" else "none",
        "sni": str(data.get("sni") or ""),
        "alpn": str(data.get("alpn") or ""),
        "fp": str(data.get("fp") or ""),
    }
    return VmessNode(
        name=str(data.get("ps") or f"{server}:{port}"),
        server=server,
        port=port,
        uuid=uuid,
        alter_id=int(data.get("aid") or 0),
        cipher=str(data.get("scy") or "auto"),
        tls=tls_from_query(tls_q, default_on=False),
        transport=transport_from_query(tq),
    )


def dump(node: VmessNode) -> str:
    d = {
        "v": "2", "ps": node.name, "add": node.server, "port": str(node.port), "id": node.uuid,
        "aid": str(node.alter_id), "scy": node.cipher, "net": "tcp", "type": "none",
        "host": "", "path": "", "tls": "",
    }
    tr = node.transport
    if tr:
        d["net"] = tr.type
        d["host"] = tr.host or ""
        d["path"] = (tr.service_name if tr.type == "grpc" else tr.path) or ""
    if node.tls:
        d["tls"] = "tls"
        if node.tls.sni:
            d["sni"] = node.tls.sni
        if node.tls.alpn:
            d["alpn"] = ",".join(node.tls.alpn)
        if node.tls.fingerprint:
            d["fp"] = node.tls.fingerprint
    return "vmess://" + b64encode_text(json.dumps(d, ensure_ascii=False))
```

- [ ] **Step 4: 实现 `backend/routeforge/parsers/uri/hysteria2.py`**

```python
"""Hysteria2：hysteria2://auth@host:port?sni=..&insecure=1&obfs=salamander&obfs-password=..#name（hy2:// 同义）。"""

from urllib.parse import quote

from routeforge.ir.node import Hysteria2Node
from routeforge.parsers.uri._common import build_uri, split_standard, tls_from_query, tls_to_query


def parse(uri: str) -> Hysteria2Node:
    p = split_standard(uri)
    q = p.query
    return Hysteria2Node(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        password=p.userinfo,
        obfs=q.get("obfs") or None,
        obfs_password=q.get("obfs-password") or None,
        tls=tls_from_query({**q, "security": "tls"}, default_on=True),
    )


def dump(node: Hysteria2Node) -> str:
    params = tls_to_query(node.tls)
    params.pop("security")
    if node.obfs:
        params["obfs"] = node.obfs
    if node.obfs_password:
        params["obfs-password"] = node.obfs_password
    return build_uri("hysteria2", quote(node.password, safe=""), node.server, node.port, params, node.name)
```

- [ ] **Step 5: 实现 `backend/routeforge/parsers/uri/tuic.py`**

```python
"""TUIC v5：tuic://uuid:password@host:port?congestion_control=bbr&alpn=h3&sni=..#name。"""

from urllib.parse import quote

from routeforge.ir.node import TuicNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import build_uri, split_standard, tls_from_query, tls_to_query


def parse(uri: str) -> TuicNode:
    p = split_standard(uri)
    uuid, sep, password = p.userinfo.partition(":")
    if not sep or not password:
        raise ParseError("tuic：缺少 uuid:password")
    return TuicNode(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        uuid=uuid,
        password=password,
        congestion_control=p.query.get("congestion_control") or None,
        tls=tls_from_query({**p.query, "security": "tls"}, default_on=True),
    )


def dump(node: TuicNode) -> str:
    params = tls_to_query(node.tls)
    params.pop("security")
    if node.congestion_control:
        params["congestion_control"] = node.congestion_control
    userinfo = f"{quote(node.uuid, safe='')}:{quote(node.password, safe='')}"
    return build_uri("tuic", userinfo, node.server, node.port, params, node.name)
```

- [ ] **Step 6: 在 `uri/__init__.py` 注册**

导入改为：

```python
from routeforge.parsers.uri import hysteria2, ss, trojan, tuic, vless, vmess
```

两个字典改为：

```python
_PARSERS: dict[str, Callable[[str], Node]] = {
    "ss": ss.parse,
    "trojan": trojan.parse,
    "vless": vless.parse,
    "vmess": vmess.parse,
    "hysteria2": hysteria2.parse,
    "hy2": hysteria2.parse,
    "tuic": tuic.parse,
}

_DUMPERS: dict[str, Callable] = {
    "ss": ss.dump,
    "trojan": trojan.dump,
    "vless": vless.dump,
    "vmess": vmess.dump,
    "hysteria2": hysteria2.dump,
    "tuic": tuic.dump,
}
```

- [ ] **Step 7: 运行确认通过**

Run: `uv run pytest -v`
Expected: 全部 passed。`port: "99999"` 一例由 pydantic `ValidationError` 经 `parse_uri` 包装为 `ParseError`；端口跳跃 `443,20000-30000` 因 `split_hostport` 不接受非数字端口而报错（第一期不支持端口跳跃）。

- [ ] **Step 8: 提交**

```bash
git add backend/routeforge/parsers backend/tests/test_uri_vmess_hy2_tuic.py
git commit -m "feat(parsers): add vmess, hysteria2 and tuic share-link parsers"
```

### Task 5: Clash / Mihomo proxy 字典 ↔ IR

**Files:**
- Create: `backend/routeforge/parsers/clash_proxy.py`
- Test: `backend/tests/test_clash_proxy.py`

**Interfaces:**
- Consumes: Task 1 全部节点模型；`ParseError`、`UnsupportedNode`
- Produces: `from_clash(d: dict) -> Node`（失败抛 `ParseError`）、`to_clash(node: Node) -> dict`（无法表达时抛 `UnsupportedNode`；`node.via` 输出为 `dialer-proxy`）。被订阅解析（Task 6）与 Mihomo 渲染器（Task 8）共用。

- [ ] **Step 1: 写失败测试 `backend/tests/test_clash_proxy.py`**

```python
import pytest

from routeforge.ir.node import (
    Hysteria2Node, Reality, SSNode, TLSOptions, Transport, TrojanNode, TuicNode, VlessNode, VmessNode,
)
from routeforge.parsers.clash_proxy import from_clash, to_clash
from routeforge.parsers.errors import ParseError, UnsupportedNode

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"


def test_vless_reality_to_clash_exact_dict():
    node = VlessNode(
        name="R", server="ex.com", port=443, uuid=UUID, flow="xtls-rprx-vision",
        tls=TLSOptions(sni="www.apple.com", fingerprint="chrome", reality=Reality(public_key="PK", short_id="ab")),
        via="前置",
    )
    assert to_clash(node) == {
        "name": "R", "type": "vless", "server": "ex.com", "port": 443, "udp": True,
        "uuid": UUID, "flow": "xtls-rprx-vision",
        "tls": True, "servername": "www.apple.com", "client-fingerprint": "chrome",
        "reality-opts": {"public-key": "PK", "short-id": "ab"},
        "dialer-proxy": "前置",
    }


def test_trojan_uses_sni_key_and_ws_opts():
    node = TrojanNode(name="T", server="a.com", port=443, password="pw",
                      tls=TLSOptions(sni="b.com", insecure=True),
                      transport=Transport(type="ws", path="/ws", host="b.com"))
    d = to_clash(node)
    assert d["sni"] == "b.com" and "servername" not in d and "tls" not in d
    assert d["skip-cert-verify"] is True
    assert d["network"] == "ws"
    assert d["ws-opts"] == {"path": "/ws", "headers": {"Host": "b.com"}}


def test_httpupgrade_maps_to_ws_with_flag():
    node = VlessNode(name="U", server="a.com", port=80, uuid=UUID, transport=Transport(type="httpupgrade", path="/up"))
    d = to_clash(node)
    assert d["tls"] is False
    assert d["network"] == "ws"
    assert d["ws-opts"] == {"path": "/up", "v2ray-http-upgrade": True}


@pytest.mark.parametrize(
    "node",
    [
        SSNode(name="s", server="1.2.3.4", port=8388, cipher="aes-128-gcm", password="p",
               plugin="obfs", plugin_opts={"mode": "http", "host": "bing.com"}),
        VmessNode(name="v", server="a.com", port=443, uuid=UUID, alter_id=0, cipher="auto",
                  tls=TLSOptions(sni="a.com", alpn=["h2"]), transport=Transport(type="grpc", service_name="gun")),
        VmessNode(name="v2", server="a.com", port=80, uuid=UUID, udp=False),
        VlessNode(name="h2", server="a.com", port=443, uuid=UUID, tls=TLSOptions(),
                  transport=Transport(type="h2", path="/p", host="a.com")),
        TrojanNode(name="t", server="a.com", port=443, password="pw"),
        Hysteria2Node(name="h", server="a.com", port=443, password="pw", obfs="salamander",
                      obfs_password="x", up="50 Mbps", down="200 Mbps", tls=TLSOptions(sni="a.com")),
        TuicNode(name="u", server="a.com", port=443, uuid=UUID, password="pw", congestion_control="bbr",
                 tls=TLSOptions(alpn=["h3"])),
    ],
)
def test_roundtrip(node):
    assert from_clash(to_clash(node)) == node


def test_from_clash_real_world_entry():
    d = {
        "name": "🇺🇸 美国 01", "type": "vmess", "server": "us.example.com", "port": "443",
        "uuid": UUID, "alterId": "0", "cipher": "auto", "tls": True, "servername": "us.example.com",
        "network": "ws", "ws-opts": {"path": "/v", "headers": {"Host": "us.example.com"}},
        "skip-cert-verify": False,
    }
    node = from_clash(d)
    assert node.port == 443
    assert node.transport == Transport(type="ws", path="/v", host="us.example.com")


@pytest.mark.parametrize(
    "d",
    [
        {"name": "x", "type": "snell", "server": "a", "port": 1},
        {"name": "x", "type": "ss", "server": "a", "port": 1},
        {"name": "x", "type": "ss", "server": "a", "port": 1, "cipher": "c", "password": "p", "plugin": "shadow-tls"},
        {"name": "x", "type": "vmess", "server": "a", "port": 1, "uuid": UUID, "network": "quic"},
        {"name": "x", "type": "trojan", "server": "a", "port": "abc", "password": "p"},
    ],
)
def test_from_clash_invalid_raises_parse_error(d):
    with pytest.raises(ParseError):
        from_clash(d)


def test_to_clash_rejects_transport_on_protocol_without_transport():
    node = Hysteria2Node(name="h", server="a.com", port=443, password="pw", transport=Transport(type="ws"))
    with pytest.raises(UnsupportedNode):
        to_clash(node)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_clash_proxy.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.parsers.clash_proxy'`）

- [ ] **Step 3: 实现 `backend/routeforge/parsers/clash_proxy.py`**

```python
"""Clash / Mihomo proxy 字典与 IR 互转。字段名参见 https://wiki.metacubex.one/config/proxies/"""

from pydantic import ValidationError

from routeforge.ir.node import (
    Hysteria2Node, Node, Reality, SSNode, TLSOptions, Transport, TrojanNode, TuicNode, VlessNode, VmessNode,
)
from routeforge.parsers.errors import ParseError, UnsupportedNode

_SNI_KEY = {"vmess": "servername", "vless": "servername", "trojan": "sni", "hysteria2": "sni", "tuic": "sni"}
_ALWAYS_TLS = {"trojan", "hysteria2", "tuic"}
_HAS_TRANSPORT = {"vmess", "vless", "trojan"}


def from_clash(d: dict) -> Node:
    try:
        return _from_clash(d)
    except ParseError:
        raise
    except (KeyError, TypeError, ValueError, ValidationError) as e:
        raise ParseError(f"节点「{d.get('name', '?')}」无效：{e}") from e


def _from_clash(d: dict) -> Node:
    t = d["type"]
    common = dict(name=str(d["name"]), server=str(d["server"]), port=int(d["port"]), udp=bool(d.get("udp", True)))
    match t:
        case "ss":
            plugin = d.get("plugin") or None
            if plugin not in (None, "obfs", "v2ray-plugin"):
                raise ParseError(f"ss：不支持的插件 {plugin}")
            return SSNode(**common, cipher=d["cipher"], password=str(d["password"]),
                          plugin=plugin, plugin_opts=dict(d.get("plugin-opts") or {}))
        case "vmess":
            return VmessNode(**common, uuid=d["uuid"], alter_id=int(d.get("alterId", 0)),
                             cipher=d.get("cipher", "auto"), tls=_tls_from(d, t), transport=_transport_from(d))
        case "vless":
            return VlessNode(**common, uuid=d["uuid"], flow=d.get("flow") or None,
                             tls=_tls_from(d, t), transport=_transport_from(d))
        case "trojan":
            return TrojanNode(**common, password=str(d["password"]), tls=_tls_from(d, t), transport=_transport_from(d))
        case "hysteria2":
            return Hysteria2Node(**common, password=str(d["password"]), obfs=d.get("obfs") or None,
                                 obfs_password=d.get("obfs-password") or None,
                                 up=_str_or_none(d.get("up")), down=_str_or_none(d.get("down")), tls=_tls_from(d, t))
        case "tuic":
            return TuicNode(**common, uuid=d["uuid"], password=str(d.get("password", "")),
                            congestion_control=d.get("congestion-controller") or None, tls=_tls_from(d, t))
        case _:
            raise ParseError(f"不支持的节点类型：{t}")


def _str_or_none(v) -> str | None:
    return None if v is None else str(v)


def _tls_from(d: dict, t: str) -> TLSOptions | None:
    if t not in _ALWAYS_TLS and not d.get("tls"):
        return None
    ro = d.get("reality-opts")
    reality = Reality(public_key=ro["public-key"], short_id=str(ro.get("short-id", ""))) if ro else None
    return TLSOptions(
        sni=d.get(_SNI_KEY[t]) or None,
        alpn=list(d.get("alpn") or []),
        insecure=bool(d.get("skip-cert-verify", False)),
        fingerprint=d.get("client-fingerprint") or None,
        reality=reality,
    )


def _transport_from(d: dict) -> Transport | None:
    net = d.get("network") or "tcp"
    match net:
        case "tcp":
            return None
        case "ws":
            o = d.get("ws-opts") or {}
            return Transport(
                type="httpupgrade" if o.get("v2ray-http-upgrade") else "ws",
                path=o.get("path") or None,
                host=(o.get("headers") or {}).get("Host") or None,
            )
        case "grpc":
            o = d.get("grpc-opts") or {}
            return Transport(type="grpc", service_name=o.get("grpc-service-name") or None)
        case "h2":
            o = d.get("h2-opts") or {}
            hosts = o.get("host") or []
            return Transport(type="h2", path=o.get("path") or None, host=hosts[0] if hosts else None)
        case _:
            raise ParseError(f"不支持的传输层：{net}")


def to_clash(node: Node) -> dict:
    d: dict = {"name": node.name, "type": node.type, "server": node.server, "port": node.port, "udp": node.udp}
    match node:
        case SSNode():
            d["cipher"] = node.cipher
            d["password"] = node.password
            if node.plugin:
                d["plugin"] = node.plugin
                d["plugin-opts"] = dict(node.plugin_opts)
        case VmessNode():
            d.update({"uuid": node.uuid, "alterId": node.alter_id, "cipher": node.cipher})
        case VlessNode():
            d["uuid"] = node.uuid
            if node.flow:
                d["flow"] = node.flow
        case TrojanNode():
            d["password"] = node.password
        case Hysteria2Node():
            d["password"] = node.password
            for key, value in (("obfs", node.obfs), ("obfs-password", node.obfs_password),
                               ("up", node.up), ("down", node.down)):
                if value:
                    d[key] = value
        case TuicNode():
            d["uuid"] = node.uuid
            d["password"] = node.password
            if node.congestion_control:
                d["congestion-controller"] = node.congestion_control
    _tls_to(d, node)
    _transport_to(d, node)
    if node.via:
        d["dialer-proxy"] = node.via
    return d


def _tls_to(d: dict, node: Node) -> None:
    tls = node.tls
    if node.type in ("vmess", "vless"):
        d["tls"] = tls is not None
    if tls is None:
        return
    if node.type == "ss":
        raise UnsupportedNode("ss 节点不支持 TLS 字段")
    if tls.sni:
        d[_SNI_KEY[node.type]] = tls.sni
    if tls.alpn:
        d["alpn"] = list(tls.alpn)
    if tls.insecure:
        d["skip-cert-verify"] = True
    if tls.fingerprint:
        d["client-fingerprint"] = tls.fingerprint
    if tls.reality:
        if node.type != "vless":
            raise UnsupportedNode(f"{node.type} 不支持 Reality")
        d["reality-opts"] = {"public-key": tls.reality.public_key, "short-id": tls.reality.short_id}


def _transport_to(d: dict, node: Node) -> None:
    tr = node.transport
    if tr is None:
        return
    if node.type not in _HAS_TRANSPORT:
        raise UnsupportedNode(f"{node.type} 不支持传输层 {tr.type}")
    match tr.type:
        case "ws" | "httpupgrade":
            d["network"] = "ws"
            opts: dict = {}
            if tr.path:
                opts["path"] = tr.path
            if tr.host:
                opts["headers"] = {"Host": tr.host}
            if tr.type == "httpupgrade":
                opts["v2ray-http-upgrade"] = True
            d["ws-opts"] = opts
        case "grpc":
            d["network"] = "grpc"
            d["grpc-opts"] = {"grpc-service-name": tr.service_name or ""}
        case "h2":
            d["network"] = "h2"
            opts = {"host": [tr.host]} if tr.host else {}
            if tr.path:
                opts["path"] = tr.path
            d["h2-opts"] = opts
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_clash_proxy.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add backend/routeforge/parsers/clash_proxy.py backend/tests/test_clash_proxy.py
git commit -m "feat(parsers): convert between clash proxy dicts and node IR"
```

### Task 6: 订阅内容解析（格式自动识别）

**Files:**
- Create: `backend/routeforge/parsers/subscription.py`
- Test: `backend/tests/test_subscription.py`

**Interfaces:**
- Consumes: `parse_many`、`ParseOutcome`、`LineError`（Task 2）；`from_clash`（Task 5）；`b64decode_loose`（Task 2）
- Produces: `parse_subscription(text: str) -> ParseOutcome`。P2 的订阅源拉取调用它。

识别顺序：Clash YAML（顶层 dict 且含 `proxies` 列表）→ 明文分享链接（含 `://`）→ Base64 编码的分享链接列表。

- [ ] **Step 1: 写失败测试 `backend/tests/test_subscription.py`**

```python
from routeforge.ir.node import SSNode, TrojanNode
from routeforge.parsers.subscription import parse_subscription

# base64url（无填充）编码的 "trojan://pw@a.example.com:443#A\r\nss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B\r\n"
B64_SUB = (
    "dHJvamFuOi8vcHdAYS5leGFtcGxlLmNvbTo0NDMjQQ0Kc3M6Ly9ZV1Z6TFRJMU5pMW5ZMjA2ZEdWemRBQDEuMi4zLjQ6ODM4OCNCDQo"
)


def test_base64_without_padding_and_crlf_lines():
    outcome = parse_subscription(B64_SUB)
    assert [type(n) for n in outcome.nodes] == [TrojanNode, SSNode]
    assert [n.name for n in outcome.nodes] == ["A", "B"]
    assert outcome.errors == []


def test_base64_wrapped_over_multiple_lines():
    wrapped = "\n".join(B64_SUB[i:i + 40] for i in range(0, len(B64_SUB), 40))
    assert [n.name for n in parse_subscription(wrapped).nodes] == ["A", "B"]


def test_plain_share_links_with_bom():
    text = "﻿trojan://pw@a.example.com:443#A\nss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B\n"
    assert [n.name for n in parse_subscription(text).nodes] == ["A", "B"]


def test_clash_yaml_keeps_good_proxies_and_reports_bad_ones():
    text = """
mixed-port: 7890
proxies:
  - {name: 香港 01, type: ss, server: 1.2.3.4, port: 8388, cipher: aes-128-gcm, password: p}
  - {name: 坏节点, type: snell, server: 1.2.3.4, port: 1}
  - just-a-string
proxy-groups: []
"""
    outcome = parse_subscription(text)
    assert [n.name for n in outcome.nodes] == ["香港 01"]
    assert [e.line for e in outcome.errors] == ["坏节点", "just-a-string"]


def test_empty_and_garbage():
    assert parse_subscription("   \n").nodes == []
    garbage = parse_subscription("<html>502 Bad Gateway</html>")
    assert garbage.nodes == []
    assert len(garbage.errors) == 1
    assert "无法识别" in garbage.errors[0].message
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_subscription.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `backend/routeforge/parsers/subscription.py`**

```python
"""机场订阅内容解析：自动识别 Clash YAML / 明文分享链接 / Base64 分享链接列表。"""

import yaml

from routeforge.parsers.clash_proxy import from_clash
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import LineError, ParseOutcome, parse_many
from routeforge.parsers.uri._common import b64decode_loose


def parse_subscription(text: str) -> ParseOutcome:
    stripped = text.lstrip("﻿").strip()
    if not stripped:
        return ParseOutcome()
    clash = _try_clash_yaml(stripped)
    if clash is not None:
        return clash
    if "://" not in stripped:
        try:
            stripped = b64decode_loose(stripped)
        except ParseError:
            return ParseOutcome(errors=[LineError(line=stripped[:80], message="无法识别的订阅格式")])
        if "://" not in stripped:
            return ParseOutcome(errors=[LineError(line=stripped[:80], message="无法识别的订阅格式")])
    return parse_many(stripped)


def _try_clash_yaml(text: str) -> ParseOutcome | None:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
        return None
    outcome = ParseOutcome()
    for item in data["proxies"]:
        if not isinstance(item, dict):
            outcome.errors.append(LineError(line=str(item)[:80], message="proxies 中的条目不是映射"))
            continue
        try:
            outcome.nodes.append(from_clash(item))
        except ParseError as e:
            outcome.errors.append(LineError(line=str(item.get("name", "?")), message=str(e)))
    return outcome
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_subscription.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add backend/routeforge/parsers/subscription.py backend/tests/test_subscription.py
git commit -m "feat(parsers): auto-detect and parse subscription content"
```

### Task 7: 方案 IR + Resolver

**Files:**
- Create: `backend/routeforge/ir/profile.py`
- Create: `backend/routeforge/ir/resolved.py`
- Create: `backend/routeforge/resolver.py`
- Test: `backend/tests/test_resolver.py`

**Interfaces:**
- Consumes: `Node`（Task 1）
- Produces:
  - `routeforge.ir.profile`: `BUILTIN_TARGETS: frozenset[str]`（`{"DIRECT", "REJECT"}`）、`GroupType`、`RuleType`、`NodeRef(node_id: int)`、`GroupRef(name: str)`、`Builtin(name: "DIRECT" | "REJECT")`、`Filter(source_id: int | None, name_regex: str, exclude_regex: str | None)`、`Member`（按 `kind` 判别：`"node" | "group" | "builtin" | "filter"`）、`ProxyGroup(name, type, members, url, interval, tolerance)`、`Rule(type, value, target, no_resolve)`、`RuleProvider(name, behavior, format, url, interval)`、`Chain(node: NodeRef, via: GroupRef | NodeRef)`、`Profile(name, groups, rules, rule_providers, chains)`
  - `routeforge.ir.resolved`: `ResolvedGroup(name, type, members: list[str], url, interval, tolerance)`、`ResolvedProfile(name, proxies: list[Node], groups, rules, rule_providers, source_ids: list[int])`
  - `routeforge.resolver`: `LibraryNode(id: int, source_id: int, enabled: bool, node: Node)`（frozen dataclass）、`ResolveResult(profile: ResolvedProfile | None, errors: list[str], warnings: list[str])`（`.ok` 属性）、`resolve(profile: Profile, library: list[LibraryNode]) -> ResolveResult`、`match_filter(library: list[LibraryNode], f: Filter) -> list[LibraryNode]`（正则无效抛 `re.error`；P2 的过滤器预览接口使用）

行为约定（来自 spec 第 5 节）：
- `library` 的顺序即节点库顺序；过滤器展开结果按此顺序
- 错误（errors 非空）→ `profile=None`；警告不阻止渲染
- 最终名称冲突（与分组名、`DIRECT`/`REJECT`、先出现的节点名）→ 追加 ` 2`、` 3`…
- 环检测覆盖：分组嵌套环；落地节点经 `via` 回到自身（直接或经分组）
- 空分组 → 成员补 `DIRECT` 并警告
- 规则：必须且仅有一条 `MATCH`，且在末尾；`RULE-SET` 的 value 必须是已定义规则集；目标必须是分组或 `DIRECT`/`REJECT`

- [ ] **Step 1: 写失败测试 `backend/tests/test_resolver.py`**

```python
import re

import pytest

from routeforge.ir.node import SSNode
from routeforge.ir.profile import (
    Builtin, Chain, Filter, GroupRef, NodeRef, Profile, ProxyGroup, Rule, RuleProvider,
)
from routeforge.resolver import LibraryNode, match_filter, resolve


def ss(name: str) -> SSNode:
    return SSNode(name=name, server="1.1.1.1", port=8388, cipher="aes-128-gcm", password="p")


def lib(*rows: tuple) -> list[LibraryNode]:
    """rows: (id, source_id, name) 或 (id, source_id, name, enabled)"""
    return [LibraryNode(id=r[0], source_id=r[1], enabled=r[3] if len(r) > 3 else True, node=ss(r[2])) for r in rows]


MATCH_PROXY = [Rule(type="MATCH", target="Proxy")]


def make(groups, rules=None, **kw) -> Profile:
    return Profile(name="p", groups=groups, rules=MATCH_PROXY if rules is None else rules, **kw)


def group(name, *members, type="select") -> ProxyGroup:
    return ProxyGroup(name=name, type=type, members=list(members))


def members_of(result, name):
    return next(g.members for g in result.profile.groups if g.name == name)


def test_filter_expands_by_source_and_regex_in_library_order_skipping_disabled():
    library = lib((1, 10, "香港 01"), (2, 10, "日本 01"), (3, 20, "香港 02"), (4, 10, "香港 03", False), (5, 10, "香港 04 x0.1"))
    p = make([group("Proxy", Filter(source_id=10, name_regex="香港|HK", exclude_regex=r"x0\.\d"))])
    result = resolve(p, library)
    assert result.ok, result.errors
    assert members_of(result, "Proxy") == ["香港 01"]
    assert [n.name for n in result.profile.proxies] == ["香港 01"]
    assert result.profile.source_ids == [10]


def test_filter_without_source_matches_all_sources():
    library = lib((1, 10, "HK1"), (2, 20, "HK2"))
    result = resolve(make([group("Proxy", Filter(name_regex="HK"))]), library)
    assert members_of(result, "Proxy") == ["HK1", "HK2"]
    assert result.profile.source_ids == [10, 20]


def test_invalid_regex_is_an_error_not_an_exception():
    result = resolve(make([group("Proxy", Filter(name_regex="("))]), lib((1, 10, "a")))
    assert not result.ok
    assert any("正则" in e for e in result.errors)


def test_match_filter_public_helper():
    library = lib((1, 10, "HK1"), (2, 10, "JP1"))
    assert [ln.id for ln in match_filter(library, Filter(name_regex="HK"))] == [1]
    with pytest.raises(re.error):
        match_filter(library, Filter(name_regex="("))


def test_missing_or_disabled_node_ref_warns_and_empty_group_gets_direct():
    library = lib((1, 10, "a", False))
    result = resolve(make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=99))]), library)
    assert result.ok
    assert members_of(result, "Proxy") == ["DIRECT"]
    assert len([w for w in result.warnings if "不存在或已禁用" in w]) == 2
    assert any("DIRECT" in w for w in result.warnings)


def test_duplicate_member_listed_once():
    library = lib((1, 10, "a"))
    p = make([group("Proxy", NodeRef(node_id=1), Filter(name_regex="a"))])
    assert members_of(resolve(p, library), "Proxy") == ["a"]


def test_name_collisions_with_nodes_groups_and_builtins_get_suffix():
    library = lib((1, 10, "HK"), (2, 20, "HK"), (3, 10, "Proxy"), (4, 10, "DIRECT"))
    p = make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=2), NodeRef(node_id=3), NodeRef(node_id=4))])
    result = resolve(p, library)
    assert members_of(result, "Proxy") == ["HK", "HK 2", "Proxy 2", "DIRECT 2"]
    assert [n.name for n in result.profile.proxies] == ["HK", "HK 2", "Proxy 2", "DIRECT 2"]


def test_group_ref_builtin_and_nested_group():
    library = lib((1, 10, "a"))
    p = make([group("Proxy", GroupRef(name="Auto"), Builtin(name="DIRECT")),
              group("Auto", NodeRef(node_id=1), type="url-test")])
    result = resolve(p, library)
    assert members_of(result, "Proxy") == ["Auto", "DIRECT"]
    auto = next(g for g in result.profile.groups if g.name == "Auto")
    assert auto.type == "url-test" and auto.interval == 300


def test_unknown_group_ref_and_rule_target_are_errors():
    p = make([group("Proxy", GroupRef(name="Nope"))],
             rules=[Rule(type="DOMAIN-SUFFIX", value="a.com", target="Ghost"), *MATCH_PROXY])
    result = resolve(p, lib())
    assert not result.ok
    assert any("Nope" in e for e in result.errors)
    assert any("Ghost" in e for e in result.errors)


def test_duplicate_or_reserved_group_names_are_errors():
    result = resolve(make([group("Proxy"), group("Proxy"), group("DIRECT")]), lib())
    assert any("重复" in e for e in result.errors)
    assert any("保留" in e for e in result.errors)


def test_group_cycle_is_an_error():
    p = make([group("Proxy", GroupRef(name="B")), group("B", GroupRef(name="Proxy"))])
    result = resolve(p, lib())
    assert not result.ok
    assert any("循环" in e for e in result.errors)


def test_chain_via_group_sets_via_on_landing_node():
    library = lib((1, 10, "落地"), (2, 20, "机场 HK"))
    p = make(
        [group("Proxy", NodeRef(node_id=1)), group("前置", NodeRef(node_id=2))],
        chains=[Chain(node=NodeRef(node_id=1), via=GroupRef(name="前置"))],
    )
    result = resolve(p, library)
    assert result.ok, result.errors
    proxies = {n.name: n for n in result.profile.proxies}
    assert proxies["落地"].via == "前置"
    assert proxies["机场 HK"].via is None


def test_chain_via_node_includes_and_renames_the_dialer():
    library = lib((1, 10, "落地"), (2, 20, "Proxy"))
    p = make([group("Proxy", NodeRef(node_id=1))], chains=[Chain(node=NodeRef(node_id=1), via=NodeRef(node_id=2))])
    result = resolve(p, library)
    proxies = {n.name: n for n in result.profile.proxies}
    assert set(proxies) == {"落地", "Proxy 2"}
    assert proxies["落地"].via == "Proxy 2"


def test_chain_via_group_containing_landing_node_is_a_cycle():
    library = lib((1, 10, "落地"), (2, 20, "HK"))
    p = make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=2))],
             chains=[Chain(node=NodeRef(node_id=1), via=GroupRef(name="Proxy"))])
    result = resolve(p, library)
    assert not result.ok
    assert any("循环" in e and "落地" in e for e in result.errors)


def test_mutual_node_chains_are_a_cycle():
    library = lib((1, 10, "A"), (2, 10, "B"))
    p = make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=2))],
             chains=[Chain(node=NodeRef(node_id=1), via=NodeRef(node_id=2)),
                     Chain(node=NodeRef(node_id=2), via=NodeRef(node_id=1))])
    assert any("循环" in e for e in resolve(p, library).errors)


def test_chain_problems():
    library = lib((1, 10, "落地"), (2, 10, "孤立"))
    p = make(
        [group("Proxy", NodeRef(node_id=1))],
        chains=[
            Chain(node=NodeRef(node_id=1), via=GroupRef(name="不存在")),
            Chain(node=NodeRef(node_id=2), via=NodeRef(node_id=1)),
        ],
    )
    result = resolve(p, library)
    assert any("不存在" in e for e in result.errors)
    assert any("孤立" in w and "不会生效" in w for w in result.warnings)


def test_rule_validation():
    no_match = resolve(make([group("Proxy")], rules=[]), lib())
    assert any("MATCH" in e for e in no_match.errors)

    match_not_last = resolve(make([group("Proxy")], rules=[*MATCH_PROXY, Rule(type="DOMAIN", value="a", target="DIRECT")]), lib())
    assert any("MATCH" in e for e in match_not_last.errors)

    unknown_set = resolve(make([group("Proxy")], rules=[Rule(type="RULE-SET", value="ads", target="REJECT"), *MATCH_PROXY]), lib())
    assert any("ads" in e for e in unknown_set.errors)

    ok = resolve(
        make([group("Proxy")],
             rules=[Rule(type="RULE-SET", value="ads", target="REJECT"), *MATCH_PROXY],
             rule_providers=[RuleProvider(name="ads", behavior="domain", format="mrs", url="https://x/ads.mrs")]),
        lib(),
    )
    assert ok.ok, ok.errors
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_resolver.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.ir.profile'`）

- [ ] **Step 3: 实现 `backend/routeforge/ir/profile.py`**

```python
"""配置方案（Profile）中间模型。"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

BUILTIN_TARGETS: frozenset[str] = frozenset({"DIRECT", "REJECT"})

GroupType = Literal["select", "url-test", "fallback", "load-balance"]
RuleType = Literal[
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6",
    "GEOSITE", "GEOIP", "PROCESS-NAME", "RULE-SET", "MATCH",
]


class NodeRef(BaseModel):
    kind: Literal["node"] = "node"
    node_id: int


class GroupRef(BaseModel):
    kind: Literal["group"] = "group"
    name: str


class Builtin(BaseModel):
    kind: Literal["builtin"] = "builtin"
    name: Literal["DIRECT", "REJECT"]


class Filter(BaseModel):
    """按节点源与名称正则动态匹配节点；source_id 为 None 表示所有源。"""

    kind: Literal["filter"] = "filter"
    source_id: int | None = None
    name_regex: str = ""
    exclude_regex: str | None = None


Member = Annotated[Union[NodeRef, GroupRef, Builtin, Filter], Field(discriminator="kind")]


class ProxyGroup(BaseModel):
    name: str
    type: GroupType = "select"
    members: list[Member] = []
    url: str = "https://www.gstatic.com/generate_204"
    interval: int = 300
    tolerance: int = 50


class Rule(BaseModel):
    type: RuleType
    value: str = ""
    target: str
    no_resolve: bool = False


class RuleProvider(BaseModel):
    name: str
    behavior: Literal["domain", "ipcidr", "classical"]
    format: Literal["yaml", "text", "mrs"] = "yaml"
    url: str
    interval: int = 86400


class Chain(BaseModel):
    """落地节点 node 在本方案中经由 via（分组或节点）出站。"""

    node: NodeRef
    via: Annotated[Union[GroupRef, NodeRef], Field(discriminator="kind")]


class Profile(BaseModel):
    name: str
    groups: list[ProxyGroup] = []
    rules: list[Rule] = []
    rule_providers: list[RuleProvider] = []
    chains: list[Chain] = []
```

- [ ] **Step 4: 实现 `backend/routeforge/ir/resolved.py`**

```python
"""resolver 输出、渲染器输入：所有引用已展开为最终名称。"""

from pydantic import BaseModel

from routeforge.ir.node import Node
from routeforge.ir.profile import GroupType, Rule, RuleProvider


class ResolvedGroup(BaseModel):
    name: str
    type: GroupType
    members: list[str]  # 节点最终名称 / 分组名 / DIRECT / REJECT
    url: str
    interval: int
    tolerance: int


class ResolvedProfile(BaseModel):
    name: str
    proxies: list[Node]
    groups: list[ResolvedGroup]
    rules: list[Rule]
    rule_providers: list[RuleProvider]
    source_ids: list[int]  # 本方案实际用到的节点源，升序
```

- [ ] **Step 5: 实现 `backend/routeforge/resolver.py`**

```python
"""Profile + 节点库 → ResolvedProfile：展开过滤器、校验引用、检测环、处理重名。"""

import re
from dataclasses import dataclass, field

from routeforge.ir.node import Node
from routeforge.ir.profile import BUILTIN_TARGETS, Builtin, Filter, GroupRef, NodeRef, Profile, ProxyGroup
from routeforge.ir.resolved import ResolvedGroup, ResolvedProfile

# 展开后的成员：("node", 节点 id) | ("group", 分组名) | ("builtin", "DIRECT"/"REJECT")
Entry = tuple[str, int | str]


@dataclass(frozen=True)
class LibraryNode:
    id: int
    source_id: int
    enabled: bool
    node: Node


@dataclass
class ResolveResult:
    profile: ResolvedProfile | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.profile is not None


def resolve(profile: Profile, library: list[LibraryNode]) -> ResolveResult:
    return _Resolver(profile, library).run()


def match_filter(library: list[LibraryNode], f: Filter) -> list[LibraryNode]:
    """返回过滤器匹配的已启用节点（保持节点库顺序）；正则无效时抛 re.error。"""
    include = re.compile(f.name_regex)
    exclude = re.compile(f.exclude_regex) if f.exclude_regex else None
    return [
        ln for ln in library
        if ln.enabled
        and (f.source_id is None or ln.source_id == f.source_id)
        and include.search(ln.node.name)
        and not (exclude and exclude.search(ln.node.name))
    ]


class _Resolver:
    def __init__(self, profile: Profile, library: list[LibraryNode]):
        self.profile = profile
        self.library = library
        self.by_id = {n.id: n for n in library}
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def run(self) -> ResolveResult:
        group_names = self._check_group_names()
        expanded = {g.name: self._expand(g) for g in self.profile.groups}
        chains = self._resolve_chains(group_names)
        used = self._used_nodes(expanded, chains)
        names = self._assign_names(used, group_names)
        self._check_group_refs(expanded, group_names)
        self._check_cycles(expanded, chains)
        self._check_rules(group_names)
        if self.errors:
            return ResolveResult(None, self.errors, self.warnings)
        return ResolveResult(self._build(expanded, chains, used, names), [], self.warnings)

    def _check_group_names(self) -> set[str]:
        names: set[str] = set()
        for g in self.profile.groups:
            if g.name in BUILTIN_TARGETS:
                self.errors.append(f"分组名不能使用保留名「{g.name}」")
            elif g.name in names:
                self.errors.append(f"分组名重复：「{g.name}」")
            names.add(g.name)
        return names

    def _expand(self, g: ProxyGroup) -> list[Entry]:
        out: list[Entry] = []
        for m in g.members:
            match m:
                case NodeRef(node_id=nid):
                    ln = self.by_id.get(nid)
                    if ln is None or not ln.enabled:
                        self.warnings.append(f"分组「{g.name}」引用的节点 #{nid} 不存在或已禁用，已忽略")
                        continue
                    out.append(("node", nid))
                case GroupRef(name=name):
                    out.append(("group", name))
                case Builtin(name=name):
                    out.append(("builtin", name))
                case Filter():
                    out.extend(("node", ln.id) for ln in self._match_filter(g.name, m))
        return list(dict.fromkeys(out))

    def _match_filter(self, group_name: str, f: Filter) -> list[LibraryNode]:
        try:
            return match_filter(self.library, f)
        except re.error as e:
            self.errors.append(f"分组「{group_name}」的过滤器正则无效：{e}")
            return []

    def _resolve_chains(self, group_names: set[str]) -> dict[int, Entry]:
        chains: dict[int, Entry] = {}
        for c in self.profile.chains:
            ln = self.by_id.get(c.node.node_id)
            if ln is None or not ln.enabled:
                self.warnings.append(f"链式代理的落地节点 #{c.node.node_id} 不存在或已禁用，已忽略")
                continue
            match c.via:
                case GroupRef(name=name):
                    if name not in group_names:
                        self.errors.append(f"链式代理「{ln.node.name}」的前置分组「{name}」不存在")
                        continue
                    chains[ln.id] = ("group", name)
                case NodeRef(node_id=vid):
                    v = self.by_id.get(vid)
                    if v is None or not v.enabled:
                        self.errors.append(f"链式代理「{ln.node.name}」的前置节点 #{vid} 不存在或已禁用")
                        continue
                    chains[ln.id] = ("node", vid)
        return chains

    def _used_nodes(self, expanded: dict[str, list[Entry]], chains: dict[int, Entry]) -> list[int]:
        used = [v for entries in expanded.values() for kind, v in entries if kind == "node"]
        in_groups = set(used)
        for nid, (kind, value) in chains.items():
            if nid not in in_groups:
                self.warnings.append(f"落地节点「{self.by_id[nid].node.name}」未出现在任何分组中，链式代理不会生效")
                continue
            if kind == "node":
                used.append(value)
        return list(dict.fromkeys(used))

    def _assign_names(self, used: list[int], group_names: set[str]) -> dict[int, str]:
        taken = set(group_names) | BUILTIN_TARGETS
        names: dict[int, str] = {}
        for nid in used:
            base = self.by_id[nid].node.name
            name, i = base, 2
            while name in taken:
                name = f"{base} {i}"
                i += 1
            taken.add(name)
            names[nid] = name
        return names

    def _check_group_refs(self, expanded: dict[str, list[Entry]], group_names: set[str]) -> None:
        for g, entries in expanded.items():
            for kind, value in entries:
                if kind == "group" and value not in group_names:
                    self.errors.append(f"分组「{g}」引用了不存在的分组「{value}」")

    def _check_cycles(self, expanded: dict[str, list[Entry]], chains: dict[int, Entry]) -> None:
        graph: dict[Entry, list[Entry]] = {}
        for g, entries in expanded.items():
            graph[("group", g)] = [e for e in entries if e[0] == "node" or (e[0] == "group" and e[1] in expanded)]
        for nid, target in chains.items():
            graph[("node", nid)] = [target]

        state: dict[Entry, int] = {}  # 1 = 访问中, 2 = 已完成

        def visit(v: Entry, stack: list[Entry]) -> None:
            state[v] = 1
            stack.append(v)
            for w in graph.get(v, []):
                if state.get(w) == 1:
                    cycle = stack[stack.index(w):] + [w]
                    self.errors.append("检测到循环引用：" + " → ".join(self._label(x) for x in cycle))
                elif w not in state:
                    visit(w, stack)
            stack.pop()
            state[v] = 2

        for v in graph:
            if v not in state:
                visit(v, [])

    def _label(self, e: Entry) -> str:
        kind, value = e
        return f"分组「{value}」" if kind == "group" else f"节点「{self.by_id[value].node.name}」"

    def _check_rules(self, group_names: set[str]) -> None:
        rules = self.profile.rules
        matches = [i for i, r in enumerate(rules) if r.type == "MATCH"]
        if len(matches) != 1 or matches[0] != len(rules) - 1:
            self.errors.append("规则必须以且仅以一条 MATCH 规则结尾")
        provider_names = [p.name for p in self.profile.rule_providers]
        if len(provider_names) != len(set(provider_names)):
            self.errors.append("规则集名称重复")
        for r in rules:
            if r.target not in group_names and r.target not in BUILTIN_TARGETS:
                self.errors.append(f"规则「{r.type},{r.value}」的目标「{r.target}」不存在")
            if r.type == "RULE-SET" and r.value not in provider_names:
                self.errors.append(f"规则引用的规则集「{r.value}」不存在")

    def _build(self, expanded, chains, used, names) -> ResolvedProfile:
        proxies: list[Node] = []
        for nid in used:
            via = None
            if nid in chains:
                kind, value = chains[nid]
                via = value if kind == "group" else names[value]
            proxies.append(self.by_id[nid].node.model_copy(update={"name": names[nid], "via": via}))
        groups: list[ResolvedGroup] = []
        for g in self.profile.groups:
            members = [names[v] if kind == "node" else v for kind, v in expanded[g.name]]
            if not members:
                self.warnings.append(f"分组「{g.name}」没有可用成员，已自动加入 DIRECT")
                members = ["DIRECT"]
            groups.append(ResolvedGroup(name=g.name, type=g.type, members=members,
                                        url=g.url, interval=g.interval, tolerance=g.tolerance))
        return ResolvedProfile(
            name=self.profile.name,
            proxies=proxies,
            groups=groups,
            rules=list(self.profile.rules),
            rule_providers=list(self.profile.rule_providers),
            source_ids=sorted({self.by_id[n].source_id for n in used}),
        )
```

- [ ] **Step 6: 运行确认通过**

Run: `uv run pytest tests/test_resolver.py -v`
Expected: 全部 passed

- [ ] **Step 7: 提交**

```bash
git add backend/routeforge/ir/profile.py backend/routeforge/ir/resolved.py backend/routeforge/resolver.py backend/tests/test_resolver.py
git commit -m "feat(core): add profile IR and resolver with validation and cycle detection"
```

### Task 8: 渲染器接口 + Mihomo 渲染器

**Files:**
- Create: `backend/routeforge/renderers/base.py`
- Create: `backend/routeforge/renderers/mihomo.py`
- Create: `backend/routeforge/renderers/__init__.py`
- Test: `backend/tests/test_mihomo.py`

**Interfaces:**
- Consumes: `ResolvedProfile`、`ResolvedGroup`（Task 7）；`Rule`、`RuleProvider`（Task 7）；`to_clash`、`UnsupportedNode`（Task 5）
- Produces:
  - `routeforge.renderers.base`: `RenderResult(content: str, content_type: str, file_ext: str, warnings: list[str])`、`Renderer`（Protocol：`target: str`、`render(profile: ResolvedProfile) -> RenderResult`）
  - `routeforge.renderers`: `RENDERERS: dict[str, Renderer]`、`get_renderer(target: str) -> Renderer`（未知 target 抛 `KeyError`）
  - `routeforge.renderers.mihomo`: `MihomoRenderer`、`BASE_CONFIG: dict`

- [ ] **Step 1: 写失败测试 `backend/tests/test_mihomo.py`**

```python
import shutil
import subprocess

import pytest
import yaml

from routeforge.ir.node import Hysteria2Node, Reality, SSNode, TLSOptions, Transport, VlessNode
from routeforge.ir.profile import Rule, RuleProvider
from routeforge.ir.resolved import ResolvedGroup, ResolvedProfile
from routeforge.renderers import get_renderer
from routeforge.renderers.mihomo import BASE_CONFIG, MihomoRenderer

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"


def group(name, members, type="select") -> ResolvedGroup:
    return ResolvedGroup(name=name, type=type, members=members,
                         url="https://www.gstatic.com/generate_204", interval=300, tolerance=50)


def sample() -> ResolvedProfile:
    return ResolvedProfile(
        name="我的方案",
        proxies=[
            SSNode(name="香港 01", server="1.2.3.4", port=8388, cipher="aes-128-gcm", password="p"),
            VlessNode(name="落地", server="ex.com", port=443, uuid=UUID, flow="xtls-rprx-vision",
                      tls=TLSOptions(sni="www.apple.com", fingerprint="chrome",
                                     reality=Reality(public_key="PK", short_id="ab")),
                      via="前置"),
        ],
        groups=[
            group("节点选择", ["落地", "前置", "DIRECT"]),
            group("前置", ["香港 01"], type="url-test"),
            group("广告拦截", ["REJECT", "DIRECT"]),
        ],
        rules=[
            Rule(type="RULE-SET", value="ads", target="广告拦截"),
            Rule(type="IP-CIDR", value="10.0.0.0/8", target="DIRECT", no_resolve=True),
            Rule(type="MATCH", target="节点选择"),
        ],
        rule_providers=[RuleProvider(name="ads", behavior="domain", format="mrs",
                                     url="https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/category-ads-all.mrs")],
        source_ids=[1, 2],
    )


def test_render_structure():
    result = MihomoRenderer().render(sample())
    assert result.content_type == "text/yaml; charset=utf-8"
    assert result.file_ext == "yaml"
    assert result.warnings == []
    config = yaml.safe_load(result.content)
    assert list(config) == [*BASE_CONFIG, "proxies", "proxy-groups", "rule-providers", "rules"]
    assert [p["name"] for p in config["proxies"]] == ["香港 01", "落地"]
    assert config["proxies"][1]["dialer-proxy"] == "前置"
    assert config["proxy-groups"] == [
        {"name": "节点选择", "type": "select", "proxies": ["落地", "前置", "DIRECT"]},
        {"name": "前置", "type": "url-test", "proxies": ["香港 01"],
         "url": "https://www.gstatic.com/generate_204", "interval": 300, "tolerance": 50},
        {"name": "广告拦截", "type": "select", "proxies": ["REJECT", "DIRECT"]},
    ]
    assert config["rule-providers"] == {
        "ads": {"type": "http", "behavior": "domain", "format": "mrs",
                "url": "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/category-ads-all.mrs",
                "interval": 86400, "path": "./ruleset/ads.mrs"},
    }
    assert config["rules"] == ["RULE-SET,ads,广告拦截", "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve", "MATCH,节点选择"]


def test_output_is_deterministic_and_keeps_unicode_literal():
    a = MihomoRenderer().render(sample()).content
    b = MihomoRenderer().render(sample()).content
    assert a == b
    assert "香港 01" in a


def test_no_rule_providers_key_when_none_defined():
    p = sample().model_copy(update={"rule_providers": [], "rules": [Rule(type="MATCH", target="节点选择")]})
    assert "rule-providers" not in yaml.safe_load(MihomoRenderer().render(p).content)


def test_unsupported_node_is_skipped_with_warning_and_removed_from_groups():
    bad = Hysteria2Node(name="坏", server="a.com", port=443, password="pw", transport=Transport(type="ws"))
    p = sample()
    p = p.model_copy(update={
        "proxies": [*p.proxies, bad],
        "groups": [group("节点选择", ["坏"]), *p.groups[1:]],
    })
    result = MihomoRenderer().render(p)
    config = yaml.safe_load(result.content)
    assert "坏" not in [x["name"] for x in config["proxies"]]
    assert config["proxy-groups"][0]["proxies"] == ["DIRECT"]
    assert any("坏" in w for w in result.warnings)


def test_dialer_proxy_pointing_to_skipped_node_is_dropped():
    bad = Hysteria2Node(name="坏", server="a.com", port=443, password="pw", transport=Transport(type="ws"))
    landing = SSNode(name="L", server="1.1.1.1", port=1, cipher="aes-128-gcm", password="p", via="坏")
    p = ResolvedProfile(name="x", proxies=[landing, bad], groups=[group("G", ["L", "坏"])],
                        rules=[Rule(type="MATCH", target="G")], rule_providers=[], source_ids=[])
    result = MihomoRenderer().render(p)
    config = yaml.safe_load(result.content)
    assert "dialer-proxy" not in config["proxies"][0]
    assert any("L" in w and "前置" in w for w in result.warnings)


def test_registry():
    assert isinstance(get_renderer("mihomo"), MihomoRenderer)
    with pytest.raises(KeyError):
        get_renderer("surge")


@pytest.mark.skipif(shutil.which("mihomo") is None, reason="mihomo 不在 PATH 中")
def test_mihomo_binary_accepts_config(tmp_path):
    p = sample().model_copy(update={"rule_providers": [], "rules": [Rule(type="MATCH", target="节点选择")]})
    path = tmp_path / "config.yaml"
    path.write_text(MihomoRenderer().render(p).content, encoding="utf-8")
    proc = subprocess.run(["mihomo", "-t", "-d", str(tmp_path), "-f", str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_mihomo.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.renderers'`）

- [ ] **Step 3: 实现 `backend/routeforge/renderers/base.py`**

```python
from dataclasses import dataclass, field
from typing import Protocol

from routeforge.ir.resolved import ResolvedProfile


@dataclass
class RenderResult:
    content: str
    content_type: str
    file_ext: str
    warnings: list[str] = field(default_factory=list)


class Renderer(Protocol):
    target: str

    def render(self, profile: ResolvedProfile) -> RenderResult: ...
```

- [ ] **Step 4: 实现 `backend/routeforge/renderers/mihomo.py`**

```python
"""Mihomo（Clash Meta）YAML 渲染器。"""

import copy

import yaml

from routeforge.ir.profile import Rule, RuleProvider
from routeforge.ir.resolved import ResolvedProfile
from routeforge.parsers.clash_proxy import to_clash
from routeforge.parsers.errors import UnsupportedNode
from routeforge.renderers.base import RenderResult

BASE_CONFIG: dict = {
    "mixed-port": 7890,
    "allow-lan": False,
    "mode": "rule",
    "log-level": "info",
    "ipv6": False,
    "dns": {
        "enable": True,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "nameserver": ["https://doh.pub/dns-query", "https://dns.alidns.com/dns-query"],
    },
}

_PROVIDER_EXT = {"yaml": "yaml", "text": "list", "mrs": "mrs"}


class MihomoRenderer:
    target = "mihomo"

    def render(self, profile: ResolvedProfile) -> RenderResult:
        warnings: list[str] = []
        proxies: list[dict] = []
        skipped: set[str] = set()
        for node in profile.proxies:
            try:
                proxies.append(to_clash(node))
            except UnsupportedNode as e:
                warnings.append(f"节点「{node.name}」无法用于 Mihomo，已跳过：{e}")
                skipped.add(node.name)
        for p in proxies:
            if p.get("dialer-proxy") in skipped:
                warnings.append(f"节点「{p['name']}」的前置「{p['dialer-proxy']}」已被跳过，链式代理已移除")
                del p["dialer-proxy"]

        groups = []
        for g in profile.groups:
            entry: dict = {"name": g.name, "type": g.type, "proxies": [m for m in g.members if m not in skipped] or ["DIRECT"]}
            if g.type != "select":
                entry["url"] = g.url
                entry["interval"] = g.interval
            if g.type == "url-test":
                entry["tolerance"] = g.tolerance
            groups.append(entry)

        config = copy.deepcopy(BASE_CONFIG)
        config["proxies"] = proxies
        config["proxy-groups"] = groups
        if profile.rule_providers:
            config["rule-providers"] = {p.name: _provider(p) for p in profile.rule_providers}
        config["rules"] = [_rule_line(r) for r in profile.rules]

        content = yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return RenderResult(content=content, content_type="text/yaml; charset=utf-8", file_ext="yaml", warnings=warnings)


def _provider(p: RuleProvider) -> dict:
    return {
        "type": "http",
        "behavior": p.behavior,
        "format": p.format,
        "url": p.url,
        "interval": p.interval,
        "path": f"./ruleset/{p.name}.{_PROVIDER_EXT[p.format]}",
    }


def _rule_line(r: Rule) -> str:
    if r.type == "MATCH":
        return f"MATCH,{r.target}"
    parts = [r.type, r.value, r.target]
    if r.no_resolve:
        parts.append("no-resolve")
    return ",".join(parts)
```

- [ ] **Step 5: 实现 `backend/routeforge/renderers/__init__.py`**

```python
from routeforge.renderers.base import Renderer, RenderResult
from routeforge.renderers.mihomo import MihomoRenderer

RENDERERS: dict[str, Renderer] = {
    "mihomo": MihomoRenderer(),
}


def get_renderer(target: str) -> Renderer:
    return RENDERERS[target]


__all__ = ["RENDERERS", "Renderer", "RenderResult", "get_renderer"]
```

- [ ] **Step 6: 运行确认通过**

Run: `uv run pytest tests/test_mihomo.py -v`
Expected: 全部 passed；`test_mihomo_binary_accepts_config` 在本机 SKIPPED（未安装 mihomo）。

- [ ] **Step 7: 提交**

```bash
git add backend/routeforge/renderers backend/tests/test_mihomo.py
git commit -m "feat(renderers): add renderer protocol and mihomo yaml renderer"
```

### Task 9: 内置分流模板 + 套用模板

**Files:**
- Create: `backend/routeforge/templates/__init__.py`
- Create: `backend/routeforge/templates/ads.yaml`、`ai.yaml`、`streaming.yaml`、`telegram.yaml`、`cn-direct.yaml`、`final.yaml`
- Test: `backend/tests/test_templates.py`

**Interfaces:**
- Consumes: `Profile`、`ProxyGroup`、`Rule`、`RuleProvider`、`GroupRef`（Task 7）；`resolve`、`LibraryNode`（Task 7，仅测试）
- Produces（`routeforge.templates`）：`PLACEHOLDER_GROUP = "节点选择"`、`Template(id, name, description, groups, rules, rule_providers)`、`load_templates() -> dict[str, Template]`（按文件名排序，id = 文件名去扩展名）、`apply_template(profile: Profile, template: Template) -> tuple[Profile, list[str]]`（返回新方案与给用户的中文提示）

套用规则（spec 4.4）：
- 模板分组 / 规则集与方案同名 → 跳过并提示
- 模板引用了「节点选择」而方案中没有 → 在方案最前面创建空的「节点选择」并提示
- 普通规则插到方案现有 `MATCH` 之前（没有 MATCH 则追加），与已有规则完全相同（type、value、target）的跳过
- 模板的 `MATCH`：方案已有 MATCH 则跳过并提示，否则追加到末尾
- 返回新对象，不修改传入的 profile

- [ ] **Step 1: 写失败测试 `backend/tests/test_templates.py`**

```python
from routeforge.ir.node import SSNode
from routeforge.ir.profile import NodeRef, Profile, ProxyGroup, Rule
from routeforge.resolver import LibraryNode, resolve
from routeforge.templates import PLACEHOLDER_GROUP, apply_template, load_templates

ALL_IDS = ["ads", "ai", "cn-direct", "final", "streaming", "telegram"]


def test_all_builtin_templates_load_and_use_metacubex_rule_sets():
    templates = load_templates()
    assert sorted(templates) == ALL_IDS
    for t in templates.values():
        assert t.name and t.description
        for p in t.rule_providers:
            assert p.url.startswith("https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/")
            assert p.format == "mrs"


def test_applying_every_template_to_empty_profile_resolves_cleanly():
    templates = load_templates()
    profile = Profile(name="p")
    for tid in ALL_IDS:
        profile, _ = apply_template(profile, templates[tid])
    # 给「节点选择」加一个节点，模拟用户后续操作
    groups = [g.model_copy(update={"members": [NodeRef(node_id=1)]}) if g.name == PLACEHOLDER_GROUP else g
              for g in profile.groups]
    profile = profile.model_copy(update={"groups": groups})
    library = [LibraryNode(id=1, source_id=1, enabled=True,
                           node=SSNode(name="HK", server="1.1.1.1", port=1, cipher="aes-128-gcm", password="p"))]
    result = resolve(profile, library)
    assert result.ok, result.errors
    assert profile.groups[0].name == PLACEHOLDER_GROUP
    assert profile.rules[-1].type == "MATCH"


def test_placeholder_created_once_with_note():
    templates = load_templates()
    profile, notes = apply_template(Profile(name="p"), templates["ai"])
    assert [g.name for g in profile.groups].count(PLACEHOLDER_GROUP) == 1
    assert any(PLACEHOLDER_GROUP in n for n in notes)
    profile, notes = apply_template(profile, templates["streaming"])
    assert [g.name for g in profile.groups].count(PLACEHOLDER_GROUP) == 1
    assert not any("已创建" in n for n in notes)


def test_reapplying_is_idempotent():
    templates = load_templates()
    once, _ = apply_template(Profile(name="p"), templates["telegram"])
    twice, notes = apply_template(once, templates["telegram"])
    assert twice.groups == once.groups
    assert twice.rules == once.rules
    assert twice.rule_providers == once.rule_providers
    assert any("已存在" in n for n in notes)


def test_rules_inserted_before_existing_match_and_template_match_skipped():
    templates = load_templates()
    base = Profile(
        name="p",
        groups=[ProxyGroup(name="Proxy")],
        rules=[Rule(type="DOMAIN", value="a.com", target="DIRECT"), Rule(type="MATCH", target="Proxy")],
    )
    after_ads, _ = apply_template(base, templates["ads"])
    assert [r.type for r in after_ads.rules] == ["DOMAIN", "RULE-SET", "MATCH"]
    after_final, notes = apply_template(after_ads, templates["final"])
    assert [r.type for r in after_final.rules].count("MATCH") == 1
    assert after_final.rules[-1].target == "Proxy"
    assert any("MATCH" in n for n in notes)


def test_input_profile_not_mutated():
    templates = load_templates()
    base = Profile(name="p")
    apply_template(base, templates["ads"])
    assert base.groups == [] and base.rules == [] and base.rule_providers == []
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_templates.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'routeforge.templates'`）

- [ ] **Step 3: 创建模板文件**

`backend/routeforge/templates/ads.yaml`：

```yaml
name: 广告拦截
description: 拦截常见广告与跟踪域名（默认 REJECT，可切换为 DIRECT）
groups:
  - name: 广告拦截
    type: select
    members:
      - {kind: builtin, name: REJECT}
      - {kind: builtin, name: DIRECT}
rule_providers:
  - name: category-ads-all
    behavior: domain
    format: mrs
    url: https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/category-ads-all.mrs
rules:
  - {type: RULE-SET, value: category-ads-all, target: 广告拦截}
```

`backend/routeforge/templates/ai.yaml`：

```yaml
name: AI 服务
description: OpenAI、Claude、Gemini 等境外 AI 服务单独分流
groups:
  - name: AI 服务
    type: select
    members:
      - {kind: group, name: 节点选择}
rule_providers:
  - name: category-ai-not-cn
    behavior: domain
    format: mrs
    url: https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/category-ai-!cn.mrs
rules:
  - {type: RULE-SET, value: category-ai-not-cn, target: AI 服务}
```

`backend/routeforge/templates/streaming.yaml`：

```yaml
name: 流媒体
description: Netflix、YouTube、Disney+ 走单独分组，便于指定解锁节点
groups:
  - name: 流媒体
    type: select
    members:
      - {kind: group, name: 节点选择}
rule_providers:
  - {name: netflix, behavior: domain, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/netflix.mrs"}
  - {name: youtube, behavior: domain, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/youtube.mrs"}
  - {name: disney, behavior: domain, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/disney.mrs"}
rules:
  - {type: RULE-SET, value: netflix, target: 流媒体}
  - {type: RULE-SET, value: youtube, target: 流媒体}
  - {type: RULE-SET, value: disney, target: 流媒体}
```

`backend/routeforge/templates/telegram.yaml`：

```yaml
name: Telegram
description: Telegram 域名与 IP 段单独分流
groups:
  - name: Telegram
    type: select
    members:
      - {kind: group, name: 节点选择}
rule_providers:
  - {name: telegram-domain, behavior: domain, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/telegram.mrs"}
  - {name: telegram-ip, behavior: ipcidr, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geoip/telegram.mrs"}
rules:
  - {type: RULE-SET, value: telegram-domain, target: Telegram}
  - {type: RULE-SET, value: telegram-ip, target: Telegram, no_resolve: true}
```

`backend/routeforge/templates/cn-direct.yaml`：

```yaml
name: 国内直连
description: 局域网、中国大陆域名与 IP 直连
rule_providers:
  - {name: private-domain, behavior: domain, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/private.mrs"}
  - {name: cn-domain, behavior: domain, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/cn.mrs"}
  - {name: private-ip, behavior: ipcidr, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geoip/private.mrs"}
  - {name: cn-ip, behavior: ipcidr, format: mrs, url: "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geoip/cn.mrs"}
rules:
  - {type: RULE-SET, value: private-domain, target: DIRECT}
  - {type: RULE-SET, value: cn-domain, target: DIRECT}
  - {type: RULE-SET, value: private-ip, target: DIRECT, no_resolve: true}
  - {type: RULE-SET, value: cn-ip, target: DIRECT}
```

`backend/routeforge/templates/final.yaml`：

```yaml
name: 漏网之鱼
description: 未匹配任何规则的流量走此分组（MATCH 规则）
groups:
  - name: 漏网之鱼
    type: select
    members:
      - {kind: group, name: 节点选择}
      - {kind: builtin, name: DIRECT}
rules:
  - {type: MATCH, target: 漏网之鱼}
```

- [ ] **Step 4: 实现 `backend/routeforge/templates/__init__.py`**

```python
"""内置分流模板：数据在同目录 *.yaml，套用时复制进方案。"""

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from routeforge.ir.profile import GroupRef, Profile, ProxyGroup, Rule, RuleProvider

PLACEHOLDER_GROUP = "节点选择"
_DIR = Path(__file__).parent


class Template(BaseModel):
    id: str
    name: str
    description: str
    groups: list[ProxyGroup] = []
    rules: list[Rule] = []
    rule_providers: list[RuleProvider] = []


@cache
def load_templates() -> dict[str, Template]:
    templates: dict[str, Template] = {}
    for path in sorted(_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        templates[path.stem] = Template(id=path.stem, **data)
    return templates


def apply_template(profile: Profile, template: Template) -> tuple[Profile, list[str]]:
    notes: list[str] = []

    groups = list(profile.groups)
    group_names = {g.name for g in groups}
    needs_placeholder = any(
        isinstance(m, GroupRef) and m.name == PLACEHOLDER_GROUP for g in template.groups for m in g.members
    )
    if needs_placeholder and PLACEHOLDER_GROUP not in group_names:
        groups.insert(0, ProxyGroup(name=PLACEHOLDER_GROUP))
        group_names.add(PLACEHOLDER_GROUP)
        notes.append(f"已创建分组「{PLACEHOLDER_GROUP}」，请向其中添加节点")
    for g in template.groups:
        if g.name in group_names:
            notes.append(f"分组「{g.name}」已存在，已跳过")
            continue
        groups.append(g.model_copy(deep=True))
        group_names.add(g.name)

    providers = list(profile.rule_providers)
    provider_names = {p.name for p in providers}
    for p in template.rule_providers:
        if p.name in provider_names:
            notes.append(f"规则集「{p.name}」已存在，已跳过")
            continue
        providers.append(p.model_copy())
        provider_names.add(p.name)

    rules = list(profile.rules)
    existing = {(r.type, r.value, r.target) for r in rules}
    has_match = any(r.type == "MATCH" for r in rules)
    insert_at = next((i for i, r in enumerate(rules) if r.type == "MATCH"), len(rules))
    new_rules: list[Rule] = []
    template_match: Rule | None = None
    for r in template.rules:
        if r.type == "MATCH":
            if has_match:
                notes.append("方案已有 MATCH 规则，模板中的 MATCH 已跳过")
            else:
                template_match = r
            continue
        if (r.type, r.value, r.target) not in existing:
            new_rules.append(r.model_copy())
    rules[insert_at:insert_at] = new_rules
    if template_match is not None:
        rules.append(template_match.model_copy())

    return profile.model_copy(update={"groups": groups, "rules": rules, "rule_providers": providers}), notes
```

- [ ] **Step 5: 运行确认通过**

Run: `uv run pytest tests/test_templates.py -v`
Expected: 全部 passed

- [ ] **Step 6: 全量测试并提交**

Run: `uv run pytest -v`
Expected: 全部 passed（mihomo 二进制测试 SKIPPED）

```bash
git add backend/routeforge/templates backend/tests/test_templates.py
git commit -m "feat(templates): add built-in routing templates and apply_template"
```

---

## P1 完成标准

- `cd backend && uv run pytest` 全部通过
- 核心库不依赖数据库、网络或 Web 框架；P2 只通过 `parse_many`、`parse_subscription`、`resolve`、`get_renderer`、`load_templates`、`apply_template` 和 IR 模型使用它
