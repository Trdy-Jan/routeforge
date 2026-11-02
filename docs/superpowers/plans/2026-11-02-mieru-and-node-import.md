# Mieru 协议支持 + 两步式节点导入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 RouteForge 正式支持 mieru 节点（IR、Clash 互转、`mierus://`），并把手动节点源的导入改成「粘贴 → 解析 → 勾选/改名 → 导入所选」。

**Architecture:** 后端在 IR 加 `MieruNode`，`clash_proxy` 与 `parsers/uri/mieru.py` 负责互转；URI 解析入口改为一行可产出多个节点。新增 `parsers/manual.py` 包在 `parse_subscription` 外面识别额外的 YAML 形式；导入拆成 `parse`（只读）和 `import`（重新校验后写库）两个接口。前端把勾选/重名/改名逻辑放在纯函数模块 `lib/nodeImport.ts`，`SourcesView.vue` 只负责两步弹窗。

**Tech Stack:** Python 3.12 / FastAPI / pydantic v2 / SQLModel / pytest（`uv run pytest`）；Vue 3 + Naive UI + TypeScript / vitest（`npm test`、`npm run build`）。

**Spec:** `docs/superpowers/specs/2026-11-02-mieru-and-node-import-design.md`

## Global Constraints

- 测试数据**不得**使用用户提供的真实服务器地址、用户名和密码；mieru 测试一律用 `203.0.113.10`、`user1`、`pass1` 之类的假数据。
- mieru 输出到 Clash 时**不得同时**写 `port` 和 `port-range`。
- `multiplexing`、`handshake-mode`、`traffic-pattern` 原样放行（`str | None`）；`transport` 只接受 TCP/UDP（读入不区分大小写，存大写）；`port-range` 必须是 `起-止` 且 1 ≤ 起 ≤ 止 ≤ 65535。
- 可选字段为空时不输出。
- `mierus://` 的 `profile`、`mtu` 解析时丢弃；导出时 `profile` 固定为 `default`，并附 `#节点名`。
- 无名 mieru 链接自动命名 `mieru-<服务器>-<端口或区间>-<协议>`。
- `mieru://` 链接报错文案：`暂不支持 mieru:// 标准链接，请使用 mierus:// 简易链接或 Clash YAML`。
- `parse_subscription` 行为不变（订阅源刷新不认识裸列表 / 单个映射）。
- 导入只对手动节点源开放；导入时后端重新校验，任一节点无效则整体 400、不写入任何节点。
- 现有 6 种协议的解析、导入测试全部保持通过。
- 界面文案：弹窗标题与按钮「导入节点」；按钮「解析」「返回修改」「导入所选 (x)」；计数「已选 x / y」；重名标注「已存在同名」；成功提示「已导入 x 个节点」。

## Review Focus

1. 用户名/密码里含 `:`、`@`、`%` 等需百分号编码的字符的 `mierus://` 链接——应正确解码，导出再解析得到同一节点。（Task 2 测试 `test_mierus_percent_encoded_credentials_roundtrip`）
2. IPv6 主机的 `mierus://` 链接（`[2001:db8::1]`，主机后不带端口）——应正确解析，导出时带方括号。（Task 2 测试 `test_mierus_ipv6_host`）
3. 前端回传的 config 被篡改（类型改成不支持的、缺字段）或其中一个无效——整批 400，数据库里不多出任何节点。（Task 4 测试 `test_import_rejects_invalid_node_atomically`）
4. 第 2 步改名时名字前后带空格——导入后名称被去掉首尾空格；全空格名称不可导入。（Task 4 测试 `test_import_trims_names`；Task 5 测试 `toImportItems skips blank names`）
5. 订阅源返回单个节点映射或裸节点列表——仍然报「无法识别的订阅格式」，不因本次改动被同步进来。（Task 3 测试 `test_subscription_still_rejects_bare_list`）

---

### Task 1: `MieruNode` IR 与 Clash 互转

**Files:**
- Modify: `backend/routeforge/ir/node.py`
- Modify: `backend/routeforge/parsers/clash_proxy.py`
- Test: `backend/tests/test_clash_proxy.py`、`backend/tests/test_mihomo.py`

**Interfaces:**
- Produces:
  - `class MieruNode(NodeBase)`：`type: Literal["mieru"] = "mieru"`、`username: str`、`password: str`、`protocol: Literal["TCP", "UDP"]`、`port_range: str | None = None`、`multiplexing: str | None = None`、`handshake_mode: str | None = None`、`traffic_pattern: str | None = None`；加入 `Node` 联合。
  - `port_range` 校验器：格式 `^\d+-\d+$`，1 ≤ 起 ≤ 止 ≤ 65535，否则 `ValueError`。`protocol` 用 `field_validator(mode="before")` 转大写。
  - `model_validator(mode="after")`：有 `port_range` 时把 `port` 设为区间起始端口。
  - `from_clash` 的 `mieru` 分支；`to_clash` 的 `MieruNode` 分支。

- [ ] **Step 1: 写失败测试**（`test_clash_proxy.py`）

```python
MIERU = {"name": "M", "type": "mieru", "server": "203.0.113.10", "port": 11811, "transport": "TCP",
         "udp": True, "username": "user1", "password": "pass1",
         "multiplexing": "MULTIPLEXING_OFF", "handshake-mode": "HANDSHAKE_NO_WAIT"}

def test_mieru_roundtrip_single_port():
    node = from_clash(MIERU)
    assert isinstance(node, MieruNode) and node.protocol == "TCP" and node.handshake_mode == "HANDSHAKE_NO_WAIT"
    assert to_clash(node) == MIERU

def test_mieru_port_range_wins_and_port_not_emitted():
    d = {**MIERU, "port-range": "2090-2099", "transport": "udp"}
    node = from_clash(d)
    assert (node.port, node.port_range, node.protocol) == (2090, "2090-2099", "UDP")
    out = to_clash(node)
    assert out["port-range"] == "2090-2099" and "port" not in out

def test_mieru_optional_fields_omitted():
    d = {k: v for k, v in MIERU.items() if k not in ("multiplexing", "handshake-mode")}
    assert to_clash(from_clash(d)) == d

def test_mieru_unknown_multiplexing_passes_through():
    assert to_clash(from_clash({**MIERU, "multiplexing": "MULTIPLEXING_FUTURE"}))["multiplexing"] == "MULTIPLEXING_FUTURE"

@pytest.mark.parametrize("patch", [
    {"transport": "QUIC"}, {"port-range": "2099-2090"}, {"port-range": "0-10"}, {"port-range": "abc"},
])
def test_mieru_invalid_fields(patch):
    with pytest.raises(ParseError):
        from_clash({**MIERU, **patch})

def test_mieru_missing_port_and_range():
    d = {k: v for k, v in MIERU.items() if k != "port"}
    with pytest.raises(ParseError):
        from_clash(d)

def test_mieru_with_tls_is_unsupported():
    node = from_clash(MIERU).model_copy(update={"tls": TLSOptions()})
    with pytest.raises(UnsupportedNode):
        to_clash(node)
```

`test_mihomo.py` 加一条：含 mieru 节点且 `via="前置"` 的 profile 渲染后，该 proxy 有 `dialer-proxy: 前置`、`type: mieru`，且 `port` 与 `port-range` 不同时存在（照该文件现有构造 `ResolvedProfile` 的方式写）。

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && uv run pytest tests/test_clash_proxy.py tests/test_mihomo.py -v`
Expected: FAIL（`MieruNode` 不存在 / 不支持的节点类型：mieru）

- [ ] **Step 3: 实现 `MieruNode` 与互转**

- `from_clash`：`port-range` 有值时 `port` 取区间起始端口（`common["port"]` 不能直接用 `int(d["port"])`，mieru 分支自己算）；`port` 与 `port-range` 都没有时 `ParseError("mieru：缺少 port 或 port-range")`。Clash 键 `transport` → IR `protocol`，`handshake-mode` → `handshake_mode`，`traffic-pattern` → `traffic_pattern`。
- `to_clash`：有 `port_range` 时删掉基础字典里的 `port` 再写 `port-range`。
- `_tls_to`：`node.type in ("ss", "mieru")` 时有 TLS 就抛 `UnsupportedNode(f"{node.type} 节点不支持 TLS 字段")`。`_transport_to` 现有 `_HAS_TRANSPORT` 已覆盖。

- [ ] **Step 4: 运行全部后端测试**

Run: `cd backend && uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routeforge/ir/node.py backend/routeforge/parsers/clash_proxy.py backend/tests/test_clash_proxy.py backend/tests/test_mihomo.py
git commit -m "feat(mieru): 新增 MieruNode 及 Clash 互转"
```

---

### Task 2: `mierus://` 解析/导出，URI 入口支持一行多节点

**Files:**
- Create: `backend/routeforge/parsers/uri/mieru.py`
- Modify: `backend/routeforge/parsers/uri/__init__.py`
- Test: `backend/tests/test_uri_mieru.py`（新建）

**Interfaces:**
- Consumes: `MieruNode`（Task 1）；`host_for_uri`（`_common.py`）。
- Produces:
  - `mieru.parse(uri: str) -> list[MieruNode]`、`mieru.dump(node: MieruNode) -> str`、`mieru.parse_standard(uri: str) -> list[Node]`（总是抛 `ParseError`，文案见 Global Constraints）。
  - `parse_uri_nodes(uri: str) -> list[Node]`（新，`parsers/uri/__init__.py`）：所有协议的统一入口；单节点协议包成一元素列表。
  - `parse_uri(uri: str) -> Node` 保留，内部调 `parse_uri_nodes`，结果不是恰好 1 个时 `ParseError("该链接包含多个节点")`。
  - `parse_many` 改为用 `parse_uri_nodes` 并 `extend`。
  - `_PARSERS` 注册 `"mierus": mieru.parse`、`"mieru": mieru.parse_standard`；`_DUMPERS` 注册 `"mieru": mieru.dump`。

- [ ] **Step 1: 写失败测试**

```python
def test_mierus_single_port():
    uri = ("mierus://user1:pass1@203.0.113.10?handshake-mode=HANDSHAKE_NO_WAIT&mtu=1400"
           "&multiplexing=MULTIPLEXING_OFF&port=11811&profile=default&protocol=TCP")
    assert parse_uri_nodes(uri) == [MieruNode(
        name="mieru-203.0.113.10-11811-TCP", server="203.0.113.10", port=11811, protocol="TCP",
        username="user1", password="pass1", multiplexing="MULTIPLEXING_OFF", handshake_mode="HANDSHAKE_NO_WAIT")]

def test_mierus_multi_pairs_and_range():  # 官方文档示例
    uri = ("mierus://user1:pass1@203.0.113.10?port=6666&port=9998-9999&port=6489&profile=default"
           "&protocol=TCP&protocol=TCP&protocol=UDP&traffic-pattern=CCoQAQ")
    nodes = parse_uri_nodes(uri)
    assert [(n.name, n.port, n.port_range, n.protocol) for n in nodes] == [
        ("mieru-203.0.113.10-6666-TCP", 6666, None, "TCP"),
        ("mieru-203.0.113.10-9998-9999-TCP", 9998, "9998-9999", "TCP"),
        ("mieru-203.0.113.10-6489-UDP", 6489, None, "UDP"),
    ]
    assert all(n.traffic_pattern == "CCoQAQ" for n in nodes)

def test_mierus_fragment_names():
    base = "mierus://u:p@h.example.com?profile=default&port=1000&protocol=TCP"
    assert parse_uri_nodes(base + "#My%20Node")[0].name == "My Node"
    two = base + "&port=2000&protocol=UDP#My"
    assert [n.name for n in parse_uri_nodes(two)] == ["My-1000-TCP", "My-2000-UDP"]

def test_mierus_percent_encoded_credentials_roundtrip():
    node = parse_uri_nodes("mierus://us%3Aer:p%40ss%25@h.example.com?profile=d&port=1&protocol=TCP#N")[0]
    assert (node.username, node.password) == ("us:er", "p@ss%")
    assert parse_uri_nodes(to_uri(node)) == [node]

def test_mierus_ipv6_host():
    node = parse_uri_nodes("mierus://u:p@[2001:db8::1]?profile=d&port=443&protocol=UDP#V6")[0]
    assert node.server == "2001:db8::1"
    assert "@[2001:db8::1]?" in to_uri(node)

def test_mierus_dump_shape_and_roundtrip():
    node = MieruNode(name="香港 M", server="203.0.113.10", port=2090, port_range="2090-2099", protocol="UDP",
                     username="user1", password="pass1", handshake_mode="HANDSHAKE_STANDARD")
    uri = to_uri(node)
    assert uri.startswith("mierus://user1:pass1@203.0.113.10?") and "profile=default" in uri and "port=2090-2099" in uri
    assert parse_uri_nodes(uri) == [node]

@pytest.mark.parametrize("bad", [
    "mierus://u:p@h?profile=d&port=1&port=2&protocol=TCP",   # 数量不一致
    "mierus://u:p@h?profile=d&protocol=TCP",                 # 缺 port
    "mierus://u:p@h?profile=d&port=70000&protocol=TCP",      # 端口越界
    "mierus://u:p@h?profile=d&port=1&protocol=QUIC",         # 协议非法
    "mierus://h?profile=d&port=1&protocol=TCP",              # 缺认证
    "mierus://u@h?profile=d&port=1&protocol=TCP",            # 缺密码
])
def test_mierus_errors(bad):
    with pytest.raises(ParseError):
        parse_uri_nodes(bad)

def test_mieru_standard_link_rejected():
    with pytest.raises(ParseError, match="暂不支持 mieru:// 标准链接"):
        parse_uri_nodes("mieru://QUJD")

def test_parse_uri_rejects_multi_node_link():
    with pytest.raises(ParseError):
        parse_uri("mierus://u:p@h?profile=d&port=1&port=2&protocol=TCP&protocol=UDP")

def test_parse_many_expands_mieru_links():
    text = "mierus://u:p@h?profile=d&port=1&port=2&protocol=TCP&protocol=UDP\nbroken"
    outcome = parse_many(text)
    assert len(outcome.nodes) == 2 and len(outcome.errors) == 1
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && uv run pytest tests/test_uri_mieru.py -v`
Expected: FAIL（ImportError：`parse_uri_nodes` 不存在）

- [ ] **Step 3: 实现**

- `mieru.parse`：不能用 `split_standard`（它要求 `host:port` 且把 query 压成单值）。自己拆：`#` 片段 → `?` query（`parse_qs(qs, keep_blank_values=True)` 保留多值）→ `rpartition("@")` 得 userinfo 与主机；userinfo 先 `partition(":")` 再分别 `unquote`（先拆后解码，才能支持编码过的 `:`）；主机以 `[` 开头时取方括号内。端口区间的合法性交给 `MieruNode` 校验，`ValidationError` 由 `parse_uri` 外层现有的 `except ValueError` 转成 `ParseError`。
- `mieru.dump`：参数顺序 `profile, port, protocol, multiplexing, handshake-mode, traffic-pattern`（只写有值的）；userinfo 用 `quote(..., safe='')`；主机用 `host_for_uri`；结尾 `#` + `quote(name, safe='')`。
- `parse_uri_nodes` 承接现有 `parse_uri` 的 scheme 识别、大小写处理和异常转换；解析器返回单个 `Node` 时包成列表。

- [ ] **Step 4: 运行全部后端测试**

Run: `cd backend && uv run pytest -q`
Expected: 全部 PASS（包括 `test_uri_ss.py` 等旧测试）

- [ ] **Step 5: Commit**

```bash
git add backend/routeforge/parsers/uri/ backend/tests/test_uri_mieru.py
git commit -m "feat(mieru): 支持 mierus:// 分享链接解析与导出"
```

---

### Task 3: 手动导入的格式识别

**Files:**
- Create: `backend/routeforge/parsers/manual.py`
- Test: `backend/tests/test_manual_input.py`（新建）、`backend/tests/test_subscription.py`

**Interfaces:**
- Consumes: `parse_subscription`、`from_clash`、`name_label`、`ParseOutcome`、`LineError`。
- Produces: `parse_manual_input(text: str) -> ParseOutcome`。

识别顺序：`yaml.safe_load` 成功且结果是含 `type` 键的 dict → 单节点；是 list 且每个元素都是含 `type` 键的 dict → 节点列表；否则交给 `parse_subscription(text)`（覆盖 `proxies:`、明文链接、base64）。单节点/列表的逐项错误处理与 `subscription._try_clash_yaml` 一致（抽出一个共用的 `_clash_items(items) -> ParseOutcome` 放在 `subscription.py`，两处都用）。

- [ ] **Step 1: 写失败测试**

```python
SINGLE = "name: M\ntype: mieru\nserver: 203.0.113.10\nport: 1\ntransport: TCP\nusername: u\npassword: p\n"

def test_single_mapping():
    assert [n.name for n in parse_manual_input(SINGLE).nodes] == ["M"]

def test_bare_list_with_one_bad_item():
    text = "- " + SINGLE.replace("\n", "\n  ").rstrip() + "\n- {name: X, type: snell, server: a, port: 1}\n"
    out = parse_manual_input(text)
    assert [n.name for n in out.nodes] == ["M"]
    assert out.errors[0].line == "X" and "snell" in out.errors[0].message

def test_proxies_document_and_links_still_work():
    assert len(parse_manual_input("proxies:\n  - " + SINGLE.replace("\n", "\n    ")).nodes) == 1
    assert len(parse_manual_input("mierus://u:p@h?profile=d&port=1&protocol=TCP").nodes) == 1

def test_plain_garbage_reports_error():
    out = parse_manual_input("hello world")
    assert out.nodes == [] and out.errors
```

`test_subscription.py` 加：

```python
def test_subscription_still_rejects_bare_list():
    out = parse_subscription("- {name: A, type: ss, server: a, port: 1, cipher: aes-128-gcm, password: x}")
    assert out.nodes == [] and out.errors[0].message == "无法识别的订阅格式"

def test_subscription_parses_mieru_in_proxies():
    text = "proxies:\n  - {name: M, type: mieru, server: 203.0.113.10, port: 1, transport: TCP, username: u, password: p}"
    assert [n.type for n in parse_subscription(text).nodes] == ["mieru"]
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && uv run pytest tests/test_manual_input.py tests/test_subscription.py -v`
Expected: `test_manual_input.py` FAIL（模块不存在）；`test_subscription_still_rejects_bare_list` PASS（锁定现状）

- [ ] **Step 3: 实现 `parse_manual_input` 与共用的 `_clash_items`**

- [ ] **Step 4: 运行全部后端测试**

Run: `cd backend && uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routeforge/parsers/ backend/tests/test_manual_input.py backend/tests/test_subscription.py
git commit -m "feat(import): 手动导入识别单个节点与裸节点列表"
```

---

### Task 4: 解析预览 / 导入所选 接口

**Files:**
- Modify: `backend/routeforge/services/library.py`（删除 `import_links`，新增两个函数）
- Modify: `backend/routeforge/api/sources.py`
- Modify: `backend/routeforge/api/nodes.py`（`NodeOut` 加 `port_range`）
- Test: `backend/tests/test_library.py`、`backend/tests/test_api_sources_nodes.py`

**Interfaces:**
- Consumes: `parse_manual_input`（Task 3）、`from_clash` / `to_clash`。
- Produces:
  - `library.existing_names(session, source_id: int) -> list[str]`
  - `library.append_nodes(session, source_id: int, nodes: list[Node]) -> int`：按 position 末尾顺序追加，返回数量（承接 `import_links` 的 position 逻辑）。
  - `POST /api/sources/{id}/nodes/parse`，入参 `ParseIn{text: str (1..500000 字符)}`，出参 `ParseOut{nodes: list[ParsedNode], errors: list[LineError], existing_names: list[str]}`；`ParsedNode{name: str, type: str, server: str, port: int, port_range: str | None, config: dict}`，`config = to_clash(node)`（`UnsupportedNode` 转为一条 error）。
  - `POST /api/sources/{id}/nodes/import`，入参 `ImportIn{nodes: list[ImportItem]}`（1..5000 项），`ImportItem{name: str (1..200), config: dict}`；出参 `ImportOut{added: int}`。
  - `NodeOut.port_range: str | None`（取自 `row.data.get("port_range")`）。
  - 两个接口对非手动源都返回 400，文案沿用现有「订阅源的节点由订阅内容决定，不能手动导入」。

`import` 逻辑：对每项 `from_clash({**config, "name": name.strip()})`；名称去空格后为空或 `ParseError` → `HTTPException(400, f"第 {i} 个节点「{名称}」无效：{原因}")`（i 从 1 开始），在写库前全部校验完。重名不拦截（前端只做提示）。

- [ ] **Step 1: 写失败测试**（`test_api_sources_nodes.py`；同时把文件里现有的 `nodes/import` 调用改成新的辅助函数）

```python
def import_text(admin, sid, text):
    parsed = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": text}).json()
    items = [{"name": n["name"], "config": n["config"]} for n in parsed["nodes"]]
    return parsed, admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": items})

def test_parse_does_not_write_and_lists_existing(admin):
    sid = create_manual(admin)
    parsed = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()
    assert [n["name"] for n in parsed["nodes"]] == ["A", "B"]
    assert parsed["errors"] == [{"line": "broken", "message": "不是分享链接"}]
    assert parsed["existing_names"] == [] and admin.get("/api/nodes").json() == []
    import_text(admin, sid, LINKS)
    again = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()
    assert sorted(again["existing_names"]) == ["A", "B"]

def test_import_selected_mieru_with_rename(admin):
    sid = create_manual(admin)
    text = "mierus://u:p@203.0.113.10?profile=d&port=2090-2099&port=443&protocol=TCP&protocol=UDP"
    parsed = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": text}).json()
    first = parsed["nodes"][0]
    assert (first["type"], first["port"], first["port_range"]) == ("mieru", 2090, "2090-2099")
    r = admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [{"name": "香港 M", "config": first["config"]}]})
    assert r.json() == {"added": 1}
    node = admin.get("/api/nodes").json()[0]
    assert (node["name"], node["port_range"]) == ("香港 M", "2090-2099")

def test_import_trims_names(admin):
    sid = create_manual(admin)
    cfg = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()["nodes"][0]["config"]
    assert admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [{"name": "  X  ", "config": cfg}]}).status_code == 200
    assert admin.get("/api/nodes").json()[0]["name"] == "X"
    assert admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [{"name": "   ", "config": cfg}]}).status_code == 400

def test_import_rejects_invalid_node_atomically(admin):
    sid = create_manual(admin)
    good = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()["nodes"][0]
    bad = {"name": "坏", "config": {**good["config"], "type": "snell"}}
    r = admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [good, bad]})
    assert r.status_code == 400 and "第 2 个节点「坏」" in r.json()["detail"]
    assert admin.get("/api/nodes").json() == []
```

把现有 `test_manual_source_import_list_and_edit`、`test_delete_source_removes_nodes`、`test_match_filter` 以及订阅源 400 那条改用 `import_text` / 新接口；订阅源上 `parse` 与 `import` 都断言 400。`test_library.py` 中 `import_links` 的用例改为测 `append_nodes`（追加到末尾、position 连续）和 `existing_names`。

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && uv run pytest tests/test_api_sources_nodes.py tests/test_library.py -v`
Expected: FAIL（`/nodes/parse` 404 等）

- [ ] **Step 3: 实现服务函数与两个接口，`NodeOut` 加 `port_range`**

- [ ] **Step 4: 运行全部后端测试**

Run: `cd backend && uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routeforge/services/library.py backend/routeforge/api/ backend/tests/
git commit -m "feat(import): 节点导入拆分为解析预览与导入所选两个接口"
```

---

### Task 5: 前端 API 类型与导入勾选逻辑

**Files:**
- Modify: `frontend/src/api/types.ts`、`frontend/src/api/index.ts`
- Create: `frontend/src/lib/nodeImport.ts`
- Test: `frontend/src/lib/nodeImport.test.ts`

**Interfaces:**
- Consumes: Task 4 的接口形状。
- Produces:
  - 类型：`ParsedNode {name; type; server; port: number; port_range: string | null; config: Record<string, unknown>}`、`ParseResult {nodes: ParsedNode[]; errors: LineError[]; existing_names: string[]}`、`ImportItem {name: string; config: Record<string, unknown>}`；`ImportResult` 改为 `{added: number}`；`NodeItem` 加 `port_range: string | null`。
  - `api.parseNodes(id: number, text: string): Promise<ParseResult>`；`api.importNodes(id: number, nodes: ImportItem[]): Promise<ImportResult>`。
  - `interface ImportRow { key: number; node: ParsedNode; name: string; checked: boolean }`
  - `buildRows(result: ParseResult): ImportRow[]`：`name` 初值为 `node.name`；与 `existing_names` 同名或与本批次更早的行同名时 `checked = false`，否则 `true`。
  - `duplicateKeys(rows: ImportRow[], existing: string[]): Set<number>`：按 `name.trim()` 比较；与已有节点同名，或在本批次里出现不止一次的行，都算重名。
  - `toImportItems(rows: ImportRow[]): ImportItem[]`：只取 `checked` 且 `name.trim()` 非空的行，名称去首尾空格。
  - `addressText(server: string, port: number, portRange: string | null): string` → `` `${server}:${portRange ?? port}` ``。

- [ ] **Step 1: 写失败测试**

```ts
const n = (name: string, over: Partial<ParsedNode> = {}): ParsedNode =>
  ({ name, type: 'mieru', server: '203.0.113.10', port: 1, port_range: null, config: { name }, ...over })

describe('buildRows', () => {
  it('unchecks names that exist or repeat within the batch', () => {
    const rows = buildRows({ nodes: [n('A'), n('B'), n('A')], errors: [], existing_names: ['B'] })
    expect(rows.map((r) => r.checked)).toEqual([true, false, false])
  })
})

describe('duplicateKeys', () => {
  it('updates after rename and ignores surrounding spaces', () => {
    const rows = buildRows({ nodes: [n('A'), n('A')], errors: [], existing_names: [] })
    expect([...duplicateKeys(rows, [])]).toEqual([rows[0].key, rows[1].key])
    rows[1].name = 'A2'
    expect(duplicateKeys(rows, []).size).toBe(0)
    rows[1].name = ' A '
    expect(duplicateKeys(rows, []).size).toBe(2)
  })
})

describe('toImportItems', () => {
  it('skips blank names and unchecked rows, trims names', () => {
    const rows = buildRows({ nodes: [n('A'), n('B'), n('C')], errors: [], existing_names: [] })
    rows[0].name = '  香港  '; rows[1].name = '   '; rows[2].checked = false
    expect(toImportItems(rows)).toEqual([{ name: '香港', config: { name: 'A' } }])
  })
})

it('addressText prefers port range', () => {
  expect(addressText('h', 2090, '2090-2099')).toBe('h:2090-2099')
  expect(addressText('h', 443, null)).toBe('h:443')
})
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd frontend && npm test -- nodeImport`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `nodeImport.ts`、类型与 API 方法**

- [ ] **Step 4: 运行测试**

Run: `cd frontend && npm test`
Expected: 全部 PASS（此时 `SourcesView.vue` 仍调用旧签名，`npm run build` 会失败，留给 Task 6）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/ frontend/src/lib/nodeImport.ts frontend/src/lib/nodeImport.test.ts
git commit -m "feat(import): 前端导入类型、API 与勾选逻辑"
```

---

### Task 6: 两步导入弹窗、节点列表显示端口区间、README

**Files:**
- Modify: `frontend/src/views/SourcesView.vue`（`// —— 导入分享链接 ——` 段和对应 `NModal`）
- Modify: `frontend/src/views/NodesView.vue:149`（地址列用 `addressText`）
- Modify: `README.md:7`（协议列表加 mieru，说明手动导入支持 Clash YAML 并可勾选）

**Interfaces:**
- Consumes: Task 5 的 `api.parseNodes`、`api.importNodes`、`buildRows`、`duplicateKeys`、`toImportItems`、`addressText`。

弹窗状态：`step: 1 | 2`、`importText`、`parseResult: ParseResult | null`、`rows: ImportRow[]`。
- 第 1 步：多行输入框，placeholder `每行一个分享链接（ss / vmess / vless / trojan / hysteria2 / tuic / mierus），或粘贴 Clash YAML`；按钮「解析」：调用 `parseNodes`，0 个节点时留在第 1 步并用 `NAlert` 列错误，否则 `rows = buildRows(...)`、`step = 2`。
- 第 2 步：`NDataTable`（`row-key = key`，受控 `checked-row-keys` 与 `rows[].checked` 同步，名称为空的行 `disabled`）；列：勾选、名称（`NInput size="small"`，在 `duplicateKeys` 中的行后面跟一个 `NTag type="warning"`「已存在同名」）、类型（同 NodesView 的 `NTag`）、地址（`addressText`）。表格下方 `NAlert` 列 `parseResult.errors`。底部左侧「已选 x / y」，右侧「返回修改」（`step = 1`，保留 `importText`）和「导入所选 (x)」（x 为 0 时禁用）。
- 导入成功：`message.success(`已导入 ${added} 个节点`)`，关闭弹窗，`load()`；失败用 `message.error` 显示后端的 detail，停留在第 2 步。
- 弹窗宽度改为 `760px`，打开时重置为第 1 步。

- [ ] **Step 1: 实现弹窗、NodesView 地址列、README**

- [ ] **Step 2: 类型检查与构建**

Run: `cd frontend && npm run build && npm test`
Expected: 构建成功，测试全部 PASS

- [ ] **Step 3: 在真实应用里走一遍**

用 `run` skill 启动后端 + 前端，在一个手动节点源上：
1. 粘贴两端口的 `mierus://` 假链接 → 解析 → 表格显示 2 行，地址显示端口/区间；
2. 改其中一行名称、取消另一行 → 导入所选 (1) → 提示「已导入 1 个节点」，节点页地址列显示区间；
3. 再次粘贴同样内容 → 新出现的同名行默认不勾选并标「已存在同名」，改名后标注消失；
4. 粘贴含一个 `snell` 条目的 `proxies:` YAML → 错误单独列出；
5. 点「返回修改」能回到输入框且内容还在。
截图第 2、3 步给用户看。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/SourcesView.vue frontend/src/views/NodesView.vue README.md
git commit -m "feat(import): 两步式导入节点弹窗，节点列表显示端口区间"
```
