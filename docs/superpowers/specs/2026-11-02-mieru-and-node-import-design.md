# Mieru 协议支持 + 两步式节点导入 设计

日期：2026-11-02

## 背景与目的

RouteForge 目前不认识 mieru：机场 Clash 订阅里的 `type: mieru` 条目会被当成解析错误丢掉，`mierus://` 分享链接也会报「不支持的协议」。用户手上确实有 mieru 节点，拿到的形式是两种：

1. `mierus://` 简易分享链接
2. Mihomo / Clash Meta 的 YAML 片段（`proxies:` 列表）

同时，手动节点源现在只有「导入分享链接」一个入口（每行一个链接、直接写库），不接受 YAML，也不能挑选要哪些节点、不能在导入前改名。mieru 链接没有节点名、且一条链接可能解析出多个节点，这个问题在 mieru 上尤其明显。

所以本次做两件事：

- **A. mieru 正式支持**：IR 新增 `MieruNode`，Clash ↔ IR 互转，`mierus://` 解析与导出。
- **B. 两步式导入**：手动节点源的导入弹窗改为「粘贴 → 解析 → 勾选/改名 → 导入所选」，输入框同时接受分享链接与 Clash YAML。

## 目标

- 机场订阅（Clash YAML）里的 mieru 节点能正常进入节点库，并原样渲染到 mihomo 配置中。
- 手动节点源可以粘贴 `mierus://` 链接或 Clash YAML 片段添加 mieru 节点（以及其它已支持协议）。
- 解析出多个节点时，先列出来，用户勾选、可直接改名，再导入。
- 已导入的 mieru 节点可以用现有的「编辑 YAML」功能修改。

## 非目标

- mieru 原生客户端 JSON 配置导入（用户明确不要）。
- `mieru://`（标准分享链接，base64 编码的完整客户端配置）解析。遇到时报错并提示改用 `mierus://` 链接或 YAML。
- 为 mihomo 以外的输出格式（目前也只有 mihomo 渲染器）做 mieru 渲染。
- 未知协议的通用透传（之前讨论过的方案 B），不在本次范围。
- 订阅源的刷新流程不变：订阅源仍然自动全量同步，不走勾选。

## 反目标（做成这样就算失败）

- 导入前用户看不到将要导入什么，或者看到的和最终写入的不一致。
- 解析失败的条目被悄悄丢弃，没有任何提示。
- 现有 6 种协议的链接导入行为退化（原来能导的，现在导不了）。
- mieru 节点渲染出 mihomo 不接受的配置（比如同时写 `port` 和 `port-range`）。

## A. mieru 协议支持

### 字段（以 mihomo 文档为准）

参考 https://wiki.metacubex.one/en/config/proxies/mieru/：

| mihomo 字段 | 说明 |
|---|---|
| `server` | 服务器地址 |
| `port` | 单端口；与 `port-range` 互斥 |
| `port-range` | 端口区间，如 `2090-2099`；与 `port` 互斥 |
| `transport` | `TCP` 或 `UDP` |
| `username` / `password` | 认证 |
| `multiplexing` | `MULTIPLEXING_OFF` / `_LOW` / `_MIDDLE` / `_HIGH`，mihomo 默认 `_LOW` |
| `handshake-mode` | `HANDSHAKE_STANDARD` / `HANDSHAKE_NO_WAIT`，mihomo 默认 `_STANDARD` |
| `traffic-pattern` | base64 字符串，可选 |
| `udp` | 通用字段 |

mieru 没有 TLS，也没有 ws/grpc 之类的传输层。

### IR：`MieruNode`

- `type: "mieru"`，加入 `Node` 判别联合。
- 新字段：`username`、`password`、`transport: Literal["TCP", "UDP"]`、`port_range: str | None`、`multiplexing: str | None`、`handshake_mode: str | None`、`traffic_pattern: str | None`。
- `tls` 和 `transport`（NodeBase 中的传输层）对 mieru 必须为空。注意命名冲突：NodeBase 已有 `transport` 字段（传输层对象），mieru 的 TCP/UDP 需要另起字段名（建议 `mieru_transport` 或 `protocol`，由实现者定，Clash 侧仍映射到 `transport` 键）。
- **端口区间的表示（我的决定）**：NodeBase 的 `port` 是必填且被很多地方使用（`NodeOut.port`、节点列表显示等）。为了不动这些地方，`MieruNode` 在有区间时 `port` 存区间起始端口，`port_range` 存原始区间字符串；输出到 Clash 时只要 `port_range` 有值就只写 `port-range`、不写 `port`。界面上显示地址时，有区间就显示区间。
- 可选字段为空时不输出，交给 mihomo 默认值。
- **校验松紧（我的决定）**：结构性字段严格校验——`transport` 只接受 TCP/UDP（不区分大小写），`port-range` 必须是 `起-止` 且 1 ≤ 起 ≤ 止 ≤ 65535。取值型字段放行——`multiplexing`、`handshake_mode`、`traffic_pattern` 用 `str | None`，不认识的值原样保存、原样输出，交给 mihomo 判断。理由：机场以后加新取值时，节点不会在订阅刷新时被丢掉。
- **mihomo 版本兼容（我的决定）**：不针对具体版本做裁剪。可选字段只在来源里有值时才输出，所以不会凭空多写出旧版 mihomo 不认识的字段。

### Clash ↔ IR

- `from_clash` 增加 `mieru` 分支：`port` 与 `port-range` 都缺失时报错；两者都有时以 `port-range` 为准（mihomo 文档的示例里两个都写了，所以宽容接受）。`transport` 值不区分大小写读入，统一存成大写。
- `to_clash` 增加 `mieru` 分支，按上面的字段表输出；`dialer-proxy`（链式代理）照常生效。
- `_tls_to` / `_transport_to` 遇到 mieru 节点带 TLS 或传输层时抛 `UnsupportedNode`（与现有 ss 的处理方式一致）。

### `mierus://` 分享链接

格式（来自 mieru 官方文档 `docs/client-install.md`）：

```
mierus://用户名:密码@服务器?profile=...&port=...&protocol=...[&port=...&protocol=...][&mtu=...][&multiplexing=...][&handshake-mode=...][&traffic-pattern=...]
```

- `port` 与 `protocol` 可以出现多次，按出现顺序一一配对；`port` 可以是单端口或区间。
- **一条链接按 port/protocol 配对数解析成多个节点**，每对一个 `MieruNode`。
- `profile`、`mtu`：mihomo 没有对应字段，解析时丢弃。
- `multiplexing`、`handshake-mode`、`traffic-pattern` 映射到同名字段。
- 用户名、密码、主机按 URL 规则做百分号解码；IPv6 主机按 `[...]` 处理（沿用 `_common.py` 现有的工具函数）。
- `port` 与 `protocol` 数量不一致、缺少 `port`、端口非法、protocol 不是 TCP/UDP 时报错。
- **节点命名（我的决定）**：链接里没有节点名，自动生成 `mieru-<服务器>-<端口或区间>-<协议>`，例如 `mieru-202.0.2.34-11811-TCP`。用户可在导入第 2 步改名。若链接带 `#片段`，以片段作名称，多节点时在后面加 `-<端口>-<协议>` 区分。
- 解析入口：现有 `parse_many` 是逐行解析、一行一个节点，需要改成一行可以产出多个节点。
- **导出（我的决定）**：`to_uri` 为单个 `MieruNode` 生成一条只含一组 port/protocol 的链接，`profile` 固定写 `default`（mieru 要求必须有），并附上 `#节点名`。
- `mieru://` 开头的链接：报错「暂不支持 mieru:// 标准链接，请使用 mierus:// 简易链接或 Clash YAML」。

## B. 两步式节点导入

适用范围：只对手动节点源开放，和现在一样。订阅源不受影响。

### 界面（用户选定的方案 A：两步走）

弹窗标题与按钮文字从「导入分享链接」改为「导入节点」。

**第 1 步：粘贴**
- 一个多行输入框，提示文字说明可以粘分享链接（每行一个，列出支持的协议，包括 `mierus://`）或 Clash YAML。
- 点「解析」。此时不写数据库。
- 解析出 0 个节点时停留在第 1 步，显示错误。

**第 2 步：勾选与改名**
- 表格列：勾选框、名称（可直接编辑的输入框）、类型、地址:端口（mieru 有区间时显示区间）。
- 表头有全选。
- 与目标节点源中已有节点同名的条目，默认不勾选，并标注「已存在同名」（我的决定）。用户改名后标注随之更新；同名仍可强行勾选导入（现有导入也允许同名）。
- 本批次内部重名也同样标注（我的决定）。
- 名称为空的行不能勾选导入。
- 解析失败的条目在表格下方单独列出（原始行或节点名 + 原因），不进表格。
- 底部：「已选 x / y」、「返回修改」（回到第 1 步，保留输入内容）、「导入所选 (x)」。
- 导入成功：关闭弹窗，提示「已导入 x 个节点」，刷新列表。

### 格式自动识别

在同一个输入框里自动判断：
- 能解析为 YAML 映射且含 `proxies` 列表 → 按 Clash 列表处理。
- 能解析为单个含 `type` 的 YAML 映射 → 按单个 Clash 节点处理。
- 能解析为 YAML 列表且元素是含 `type` 的映射 → 按节点列表处理（我的决定，方便直接粘 `proxies:` 下面的内容）。
- 否则按分享链接逐行处理（与现有 `parse_many` 一致，包括 base64 订阅内容的兼容可以复用 `parse_subscription` 的逻辑）。

**订阅刷新行为不变（我的决定）**：`parse_subscription` 本身不改（只是因为 `from_clash` 新增了 mieru 分支而能解析 mieru 节点）。新增一个只给手动导入用的入口（如 `parse_manual_input`），先识别「单个节点映射」和「裸节点列表」这两种额外形式，其余情况交给 `parse_subscription`。这样订阅源遇到裸列表或单个映射时，行为仍和现在一样。

### 后端接口（我的决定）

拆成两个接口：

1. `POST /api/sources/{id}/nodes/parse`：入参 `{ text }`，返回 `{ nodes: [{ data, name, type, server, port, port_range?, duplicate }], errors: [{ line, message }] }`。不写库。`data` 是节点的 Clash 字典（或 IR JSON，由实现者定，前端只需原样回传）。
2. `POST /api/sources/{id}/nodes/import`：入参改为 `{ nodes: [{ data, name }] }`（勾选后的节点及最终名称）。后端对每个节点重新校验（`from_clash` / IR 校验），不信任前端传来的内容；任何一个无效则整体返回 400 并说明哪一个。成功返回 `{ added }`。

旧的「传一段文本直接导入」接口行为由新接口取代，前端同步修改。若担心兼容，可以保留旧入参形式一段时间，由实现者决定。

## 测试要求

- `MieruNode`：Clash → IR → Clash 往返（单端口、端口区间、可选字段缺省、`port` 与 `port-range` 并存）。
- `mierus://`：用户给的单端口示例（用假数据替换真实地址和凭据）、官方文档里的多 port/protocol + 区间示例、各类报错、导出再解析的往返。
- `mieru://` 报出明确的不支持提示。
- 订阅解析：Clash YAML 中含 mieru 节点时被正常解析。
- mihomo 渲染：mieru 节点输出正确，`dialer-proxy` 生效，不同时输出 `port` 与 `port-range`。
- 导入接口：parse 不写库；duplicate 标注正确；import 重新校验、拒绝无效数据、按顺序追加到 position 末尾；非手动源被拒绝。
- 现有 6 种协议的导入与解析测试全部保持通过。
- **测试数据不得使用用户提供的真实服务器地址、用户名和密码。**

## 交给实现者决定的事

- `MieruNode` 中 TCP/UDP 字段的具体命名。
- parse 接口返回 Clash 字典还是 IR JSON。
- 前端表格组件的具体实现（沿用 Naive UI，风格与现有 `SourcesView.vue` 一致）。
- 是否在过渡期保留旧的 import 入参形式。
