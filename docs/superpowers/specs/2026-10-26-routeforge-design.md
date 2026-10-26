# RouteForge 设计文档 — 第一期（核心 + Mihomo）

日期：2026-10-26

## 1. 目标

RouteForge 是一个自托管的订阅转换与规则管理服务。管理员在 Web 界面中维护节点库（手动录入的分享链接 + 定时刷新的机场订阅），从中挑选节点组成「配置方案」，为方案配置代理分组、分流规则和链式代理，并为每个方案生成一个带 token 的订阅链接，客户端直接订阅使用。

### 成功标准
- 客户端（第一期：Clash Verge Rev 等 Mihomo 内核客户端）订阅 `/sub/{token}` 后无需手动修改即可使用。
- 分组、规则、链式代理在客户端中按方案配置生效。
- 机场订阅中的节点变化后，客户端刷新订阅即可同步，无需重新编辑方案。

### 范围
| 项 | 第一期 | 后续 |
|---|---|---|
| 节点来源：手动分享链接、机场订阅 | ✅ | |
| 协议：ss、vmess、vless（含 Reality）、trojan、hysteria2、tuic | ✅ | |
| 输出：Mihomo YAML | ✅ | |
| 输出：sing-box、Base64、Surge/Shadowrocket/QX | | 各自独立计划，新增渲染器 |
| 内置分流模板、自定义规则、链式代理 | ✅ | |
| Web 管理界面、单管理员 | ✅ | |

### 非目标（第一期）
- 多用户 / 权限体系
- 按地区自动分组（可用「过滤器」手动实现同等效果）
- 节点测速、在线检测
- 导入现有 Clash YAML 作为手动节点源（订阅解析器会支持 Clash YAML 格式的机场订阅）

## 2. 技术栈与部署

- 后端：Python 3.12、FastAPI、SQLModel（SQLite）、Pydantic v2、httpx、APScheduler、PyYAML、argon2-cffi
- 前端：Vue 3、Vite、Naive UI、TypeScript
- 部署：单个 Docker 镜像（多阶段构建：Node 构建前端 → Python 运行时，FastAPI 托管前端静态文件），数据卷 `/data` 存放 SQLite 数据库；提供 `docker-compose.yml`
- 运行环境：公网 VPS，建议置于反向代理（HTTPS）之后

## 3. 架构

核心原则：**统一中间模型（IR）+ 每个客户端一个渲染器**。所有输入先解析为 IR；方案也以 IR 描述；渲染器只依赖 IR，互不依赖。

```
分享链接 ─┐
          ├─► parsers ─► Node(IR) ─► 节点库(DB)
机场订阅 ─┘                              │
                                         ▼
                 Profile(IR) ──► resolver ──► ResolvedProfile ──► renderers/mihomo ──► YAML
                                                                └─► (后续) sing-box / base64 / surge
```

### 目录结构
```
backend/
  routeforge/
    ir/           node.py, profile.py —— Pydantic 模型
    parsers/      uri/{ss,vmess,vless,trojan,hysteria2,tuic}.py；subscription.py
    sources/      manual.py, subscription.py
    templates/    *.yaml 内置分流模板 + loader.py
    resolver.py
    renderers/    base.py, mihomo.py
    api/          auth.py, sources.py, nodes.py, profiles.py, templates.py, subscribe.py
    db/           models.py, session.py
    scheduler.py
    config.py     环境变量配置
    main.py       FastAPI app 组装 + 静态文件托管
  tests/
frontend/
Dockerfile
docker-compose.yml
```

每个单元职责单一：parsers 只做文本 ↔ IR；resolver 只做 IR → 已展开、已校验的 IR；renderers 只做 IR → 文本；api 只做 HTTP ↔ 服务调用。

## 4. 数据模型

### 4.1 Node（IR）
公共字段：
- `name: str`
- `server: str`，`port: int`
- `udp: bool = True`

协议配置（以 `type` 字段为判别的联合类型）：
- `ss`：cipher、password、plugin（obfs / v2ray-plugin，含 plugin_opts）
- `vmess`：uuid、alter_id、cipher
- `vless`：uuid、flow
- `trojan`：password
- `hysteria2`：password、obfs、obfs_password、up/down 带宽
- `tuic`：uuid、password、congestion_control、alpn

可选子结构：
- `tls: TLSOptions | None` —— sni、alpn、insecure、fingerprint、reality（public_key、short_id）
- `transport: Transport | None` —— tcp / ws（path、host）/ grpc（service_name）/ h2（path、host）/ httpupgrade

未知或无法映射的字段保存在 `extra: dict`，不丢弃，渲染器按需使用。

### 4.2 Source
- `manual`：存放手动粘贴的节点。
- `subscription`：`url`、`refresh_interval`（分钟，默认 360）、`user_agent`（默认 `clash.meta`）、`last_fetched_at`、`last_error`、`userinfo`（解析自响应头 `subscription-userinfo`：上传/下载/总量/到期）。

### 4.3 Profile
- `name`、`token`（32 字节随机，URL 安全 base64）
- `groups: list[ProxyGroup]`
- `rules: list[Rule]`
- `rule_providers: list[RuleProvider]`
- `chains: list[Chain]` —— 链式代理：`Chain(node: NodeRef, via: GroupRef | NodeRef)`，表示该（落地）节点在本方案中经由某个分组或节点出站。链式配置属于方案而非节点，因为 via 引用的分组是方案私有的；同一节点在不同方案中可有不同的前置。

`ProxyGroup`：
- `name`、`type: select | url-test | fallback | load-balance`
- `members: list[Member]`，其中 Member 为以下之一：
  - `NodeRef(node_id)`
  - `GroupRef(name)`
  - `Builtin(DIRECT | REJECT)`
  - `Filter(source_id | None, name_regex, exclude_regex | None)` —— 在解析时展开为匹配的节点，机场节点变化后自动跟随
- `url`、`interval`、`tolerance`（仅 url-test / fallback / load-balance）

`Rule`：`type`（DOMAIN、DOMAIN-SUFFIX、DOMAIN-KEYWORD、IP-CIDR、IP-CIDR6、GEOSITE、GEOIP、PROCESS-NAME、RULE-SET、MATCH）、`value`、`target`（分组名或 DIRECT/REJECT）、`no_resolve: bool`。`MATCH` 必须且只能出现一次，且位于末尾（resolver 校验）。

`RuleProvider`：`name`、`behavior: domain | ipcidr | classical`、`format: yaml | text | mrs`、`url`、`interval`。

### 4.4 内置模板
模板是 YAML 数据文件，包含一组分组、规则、规则集（MetaCubeX meta-rules-dat 的 geosite/geoip rule-set）。第一期提供：广告拦截、AI 服务、流媒体、Telegram、国内直连、漏网之鱼。

套用模板 = 将模板中的分组 / 规则 / 规则集**复制**进方案（名称冲突时跳过并提示），之后可自由编辑；模板更新不影响已有方案。模板中引用「节点」的位置用占位分组「节点选择」表示，套用时若方案中不存在则自动创建（成员为空，由用户填充）。

### 4.5 数据库表（SQLModel）
- `source`：id、kind、name、url、refresh_interval、user_agent、last_fetched_at、last_error、userinfo(JSON)
- `node`：id、source_id、name、data(JSON, Node IR)、enabled、position
  - 订阅刷新时按 `(source_id, name)` 匹配以保留 `enabled` 状态与稳定 id；消失的节点删除，新增的节点插入
- `profile`：id、name、token、data(JSON：groups/rules/rule_providers)、last_good_render(TEXT)、last_good_at
- `setting`：key、value（管理员密码哈希、会话密钥）

## 5. Resolver

输入：Profile + 当前节点库。输出：`ResolvedProfile`（所有成员均为具体节点或分组名，可直接渲染）或校验错误列表。

步骤：
1. 展开 `Filter`：按 source 和正则匹配启用中的节点，保持节点库顺序。
2. 解析 `NodeRef`：引用的节点不存在或被禁用 → 移除并产生警告。
3. 节点重名：在最终集合中追加 ` 2`、` 3` 后缀去重，并同步更新引用。
4. 校验分组引用：`GroupRef` / 规则 `target` / `Chain.via` 指向不存在的分组或节点 → 错误；`Chain.node` 不在方案任何分组中 → 警告（链不生效）。解析后把 via 写入 ResolvedProfile 中对应节点的 `via` 字段。
5. 环检测：分组之间的嵌套环、`via` 链环（含 via 指向的分组包含该节点自身）→ 错误。
6. 空分组：成员为空的分组自动补 `DIRECT` 并产生警告（避免客户端加载失败）。
7. 规则：MATCH 校验；引用的 RULE-SET 必须在 rule_providers 中存在。

错误（error）使方案无法渲染；警告（warning）不阻止渲染。

## 6. 渲染器

```python
class Renderer(Protocol):
    target: str
    def render(self, profile: ResolvedProfile) -> RenderResult: ...

@dataclass
class RenderResult:
    content: str
    content_type: str
    warnings: list[str]
```

### Mihomo 渲染器
- 输出基础配置（mixed-port、allow-lan、mode: rule、log-level、dns 段默认值），再加 `proxies`、`proxy-groups`、`rule-providers`、`rules`。
- 已解析节点的 `via` → `dialer-proxy: <分组或节点名>`。
- 不支持的协议 / 字段 → 跳过节点并产生警告，同时从分组中移除。
- 输出顺序确定（便于快照测试与客户端 diff）。

## 7. API

### 管理 API（需登录，前缀 `/api`）
- `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`
- `GET/POST /api/sources`、`PATCH/DELETE /api/sources/{id}`、`POST /api/sources/{id}/refresh`
- `POST /api/sources/{id}/nodes/import`（粘贴多行分享链接，返回成功数量与逐条失败原因）
- `GET /api/nodes`（支持按 source / 名称筛选）、`PATCH/DELETE /api/nodes/{id}`
- `GET/POST /api/profiles`、`GET/PUT/DELETE /api/profiles/{id}`
- `POST /api/profiles/{id}/apply-template`、`POST /api/profiles/{id}/rotate-token`
- `GET /api/profiles/{id}/preview?target=mihomo` → 渲染内容 + errors + warnings
- `GET /api/templates`

### 公开订阅接口
`GET /sub/{token}?target=mihomo`
- token 无效 → 404（不区分「不存在」与「错误」）。
- 渲染成功 → 返回内容，并更新 `last_good_render`。
- resolver 出错 → 返回 `last_good_render`（若有），否则 500 并附简短说明。
- 响应头：`Content-Disposition: attachment; filename*=UTF-8''<方案名>.yaml`、`profile-update-interval: 24`；若方案中的节点只来自一个订阅源，则透传其 `subscription-userinfo`。
- 渲染结果按 (profile_id, target) 缓存于内存，节点 / 源 / 方案写操作时失效。
- 第一期未指定 target 时默认 mihomo。

## 8. 订阅源拉取

- 使用 httpx，超时 30 秒，User-Agent 可配置（默认 `clash.meta`，以便机场返回 Clash YAML 及 userinfo）。
- 内容格式自动识别：先尝试 YAML 且含 `proxies` → Clash YAML；否则尝试 Base64 解码为多行分享链接；否则按明文多行分享链接处理。
- Clash YAML 中的 proxy 字典 → Node IR 的转换与 Mihomo 渲染器互为逆操作，放在 `parsers/clash_proxy.py`。
- 失败（网络错误、非 2xx、解析出 0 个节点）→ 保留原节点，记录 `last_error` 与时间。
- APScheduler 每分钟检查一次，到期的源依次刷新；手动刷新走同一函数。

## 9. 安全

- 首次启动时若数据库中没有管理员密码，读取环境变量 `ROUTEFORGE_ADMIN_PASSWORD` 并以 argon2 哈希存储；未设置则拒绝启动并给出提示。
- 会话：签名的 HttpOnly、SameSite=Lax cookie（itsdangerous 或 starlette SessionMiddleware），会话密钥首次启动随机生成并存库；`ROUTEFORGE_COOKIE_SECURE` 控制 Secure 标记（默认 true）。
- 登录失败限速：同一 IP 5 分钟内 5 次失败后锁定 5 分钟（内存实现）。
- 订阅 token 使用 `secrets.token_urlsafe(32)`，可一键重置；比较使用常量时间（按 token 查库后无需额外比较）。
- 管理 API 只接受 JSON，配合 SameSite cookie 防 CSRF。

## 10. 错误处理汇总

| 场景 | 行为 |
|---|---|
| 单条分享链接解析失败 | 跳过，在导入结果中逐条返回原因 |
| 订阅拉取 / 解析失败 | 保留旧节点，源上记录错误，UI 标红 |
| resolver 错误 | 预览页显示错误列表；订阅接口返回上次成功结果 |
| 渲染器不支持某节点 | 跳过节点并产生警告，预览页可见 |
| 空分组 | 补 DIRECT，产生警告 |

## 11. 前端

页面：
- 登录
- 节点源：列表（类型、节点数、上次刷新、错误标红、流量信息）、新建/编辑、立即刷新、粘贴导入分享链接
- 节点：表格（来源、协议、地址、启用开关）、编辑名称、批量启用/禁用
- 方案列表 → 方案编辑：
  - 分组：增删、排序、类型、成员选择（节点 / 分组 / DIRECT/REJECT / 过滤器，过滤器可实时预览匹配的节点）
  - 规则：增删、排序、类型/值/目标
  - 规则集：增删
  - 链式代理：选择落地节点 + 前置分组/节点
  - 套用模板
- 预览：渲染结果（只读代码框）、错误/警告、订阅链接复制、重置 token

## 12. 测试

- `parsers`：每种协议的分享链接测试数据（含 Reality、ws、grpc、hy2 obfs 等变体）→ 期望 IR；IR → 链接 → IR 往返一致；订阅内容格式识别。
- `resolver`：过滤器展开、引用缺失、分组环、via 环、重名、空分组、MATCH 校验。
- `renderers/mihomo`：golden 快照（`tests/golden/*.yaml`）；可选：若 PATH 中有 `mihomo`，运行 `mihomo -t -d <tmp> -f <file>` 验证可加载。
- `api`：TestClient 覆盖登录/限速、CRUD、导入、预览、`/sub/{token}`（含 404、last_good 回退、响应头）。
- 订阅拉取：用 httpx MockTransport 模拟机场响应。
- 前端：第一期手动冒烟测试。

## 13. 后续扩展（不在本期）

- sing-box、Base64、Surge/Shadowrocket/QX 渲染器；`/sub/{token}` 根据 User-Agent 自动选择 target
- 按地区自动分组
- 节点测速
