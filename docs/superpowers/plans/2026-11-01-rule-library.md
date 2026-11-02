# 在线规则库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 routeforge 内搜索、预览 MetaCubeX/meta-rules-dat 的 geosite / geoip / geo-lite 规则，并一键加入方案。

**Architecture:** 后端 `RuleLibrary` 服务通过 GitHub trees API 拉取三个目录的文件列表，内存缓存 24h，按需从 raw.githubusercontent.com 拉取 `.list` 预览（LRU）。前端一次拿全量索引在本地搜索；共用组件 `RuleLibraryBrowser` 被独立页面和方案编辑页抽屉复用；加入逻辑是 `lib/ruleLibrary.ts` 里的纯函数。

**Tech Stack:** FastAPI + httpx（同步 Client，复用 `app.state.http`）+ pytest；Vue 3 + naive-ui + vitest。

**Spec:** `docs/superpowers/specs/2026-11-01-rule-library-design.md`

## Global Constraints

- 仓库分支 `meta`；分类 → 目录 / behavior：`geosite`→`geo/geosite`/domain，`geoip`→`geo/geoip`/ipcidr，`geo-lite`→`geo-lite/geosite`/domain。
- 列表接口：`https://api.github.com/repos/MetaCubeX/meta-rules-dat/git/trees/meta:<目录>`；规则名 = `.mrs` 文件去扩展名；只取 `type == "blob"`（排除 `classical` 子目录）。
- 写入配置的 URL：`https://github.com/MetaCubeX/meta-rules-dat/raw/meta/<目录>/<quote(name, safe='@!-_.')>.mrs`，与 `renderers/mihomo.py` 的 `GEOSITE_MRS_BASE` + quote 规则**逐字一致**，保证复用判断成立。
- 预览 URL：`https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/<目录>/<同上 quote>.list`。
- 索引 TTL 86400s；内容 LRU 50 条、TTL 86400s；内容最多返回 50000 行。
- 新建规则集：`name = <geosite-|geoip-|geolite->` + 规则名（保留 `!`），重名加 `-2`、`-3`…；`format: 'mrs'`，`interval: 86400`。
- geoip 分类插入的规则 `no_resolve: true`；geo-lite 不允许 GEOSITE/GEOIP 模式。
- 所有 API 需管理员登录；所有用户可见文案为中文。

## Review Focus

1. **首次打开时 GitHub 不可达 / 被限流**：期望接口返回 502 + 中文 detail，前端显示错误和「重试」，而不是空列表。→ Task 2 `test_index_unavailable_returns_502`。
2. **名字带 `!` 的规则（`category-ai-!cn`）**：期望 URL 与内置模板 `ai.yaml` 中的 URL 完全相同，从而复用模板创建的 `category-ai-not-cn` 规则集。→ Task 1 `test_item_url_matches_template`，Task 3 `reuses provider created by template`。
3. **方案里没有 MATCH 规则**：期望新规则追加到末尾，不报错。→ Task 3 `appends when there is no MATCH`。
4. **大小写混合搜索（输入 `OpenAI`）**：期望命中 `openai` 且排第一。→ Task 3 `search is case-insensitive`。
5. **索引里有但上游 `.list` 已删除（404）**：期望预览接口 502 + 中文报错，不返回空内容冒充"0 条"。→ Task 2 `test_content_upstream_missing_returns_502`。

---

### Task 1: 后端 RuleLibrary 服务

**Files:**
- Create: `backend/routeforge/rule_library.py`
- Test: `backend/tests/test_rule_library.py`
- Modify: `.gitignore`（已加 `.superpowers/`）、提交 spec 与本计划

**Interfaces:**
- Produces:
  - `CATEGORIES: dict[str, tuple[str, str]]`（分类 → (目录, behavior)）
  - `item_url(category: str, name: str) -> str`；`list_url(category: str, name: str) -> str`
  - `@dataclass(frozen=True) LibraryItem(category: str, name: str, behavior: str, url: str)`
  - `@dataclass LibraryIndex(items: list[LibraryItem], updated_at: datetime | None, error: str | None)`
  - `@dataclass RuleContent(total: int, lines: list[str], truncated: bool)`
  - `class LibraryUnavailable(Exception)`（消息为中文，可直接给用户看）
  - `class RuleLibrary(client: httpx.Client, clock: Callable[[], float] = time.time)`：
    - `index(force: bool = False) -> LibraryIndex` — 过期或 force 时拉取；失败时有旧数据则返回旧 items + `error`，无数据则抛 `LibraryUnavailable`
    - `content(category: str, name: str) -> RuleContent` — 分类/名字不在索引中抛 `KeyError`；拉取失败（含非 2xx）抛 `LibraryUnavailable`

- [ ] **Step 1: 写失败测试**（用 `tests.helpers.mock_client`，可变 `clock`）

```python
TREE = "https://api.github.com/repos/MetaCubeX/meta-rules-dat/git/trees/meta:{}"
def tree(*paths): return httpx.Response(200, json={"tree": [{"path": p, "type": "tree" if p == "classical" else "blob"} for p in paths]})
ROUTES = {TREE.format("geo/geosite"): tree("openai.mrs", "openai.list", "openai.yaml", "category-ai-!cn.mrs", "classical"),
          TREE.format("geo/geoip"): tree("telegram.mrs", "telegram.list"),
          TREE.format("geo-lite/geosite"): tree("apple.mrs")}

def test_index_parses_three_categories():
    idx = RuleLibrary(mock_client(ROUTES)).index()
    assert {(i.category, i.name, i.behavior) for i in idx.items} == {
        ("geosite", "openai", "domain"), ("geosite", "category-ai-!cn", "domain"),
        ("geoip", "telegram", "ipcidr"), ("geo-lite", "apple", "domain")}
    assert idx.error is None and idx.updated_at is not None

def test_item_url_matches_template():
    assert item_url("geosite", "category-ai-!cn") == load_templates()["ai"].rule_providers[0].url
    assert item_url("geo-lite", "apple") == "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo-lite/geosite/apple.mrs"

def test_index_cached_until_ttl():  # 计数 handler 调用次数：TTL 内第二次 index() 不发请求；clock 前进 86401 后重新拉取；force=True 立即重拉

def test_refresh_failure_keeps_stale_items():  # 先成功，再让路由返回 httpx.ConnectError，force=True → items 不变且 error 非空

def test_no_data_raises_unavailable():  # 路由返回 403 → pytest.raises(LibraryUnavailable)

def test_content_strips_and_truncates(monkeypatch):
    # .list 文本 "# c\n\nopenai.com\n+.chatgpt.com\n" → total 2，lines ["openai.com", "+.chatgpt.com"]，truncated False
    # monkeypatch MAX_LINES=1 → lines 只有 1 行，total 2，truncated True

def test_content_unknown_raises_keyerror():  # content("geosite", "nope") 和 content("bad", "openai") 都 KeyError

def test_content_lru_cache():  # 同一规则第二次 content() 不发请求
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_rule_library.py -v`
Expected: FAIL（`ModuleNotFoundError: routeforge.rule_library`）

- [ ] **Step 3: 实现 `backend/routeforge/rule_library.py`**

模块常量 `INDEX_TTL = 86400`、`CONTENT_TTL = 86400`、`CONTENT_CACHE_SIZE = 50`、`MAX_LINES = 50000`。用 `threading.Lock` 保护状态；内容 LRU 用 `OrderedDict`（键 `(category, name)`，值 `(fetched_at, RuleContent)`）。三个目录全部成功才替换索引。行处理：`strip()` 后丢弃空行和以 `#` 开头的行。`LibraryUnavailable` 消息示例：`"无法从 GitHub 获取规则列表：<原因>"`、`"无法获取规则内容：<原因>"`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_rule_library.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add .gitignore docs/superpowers backend/routeforge/rule_library.py backend/tests/test_rule_library.py
git commit -m "feat(rule-library): 新增 meta-rules-dat 规则索引与内容缓存服务"
```

---

### Task 2: 后端 API

**Files:**
- Create: `backend/routeforge/api/rule_library.py`
- Modify: `backend/routeforge/app.py`（`app.state.rule_library = RuleLibrary(client)`；`include_router`）
- Test: `backend/tests/test_api_rule_library.py`

**Interfaces:**
- Consumes: Task 1 全部。
- Produces（路由 prefix `/api/rule-library`，`dependencies=[Depends(require_admin)]`）：
  - `GET ""` 与 `POST "/refresh"` → `{"updated_at": str | null (ISO 8601), "error": str | null, "items": [{"category","name","behavior","url"}]}`；`LibraryUnavailable` → 502，`detail` 为其消息
  - `GET "/{category}/{name}/content"` → `{"total": int, "lines": [str], "truncated": bool}`；`KeyError` → 404 `"规则不存在"`；`LibraryUnavailable` → 502

- [ ] **Step 1: 写失败测试**（`routes` fixture 注入 Task 1 的 `ROUTES` 及 `.list` URL）

```python
def test_requires_login(client): assert client.get("/api/rule-library").status_code == 401

def test_list_and_refresh(admin, routes):  # GET 返回 4 个 items；POST /refresh 200 且结构相同

def test_index_unavailable_returns_502(admin):  # routes 为空（全部 404）→ 502，detail 含 "GitHub"

def test_content_ok(admin, routes):  # GET /api/rule-library/geosite/openai/content → total/lines 正确

def test_content_name_with_bang(admin, routes):  # /geosite/category-ai-!cn/content 200（路由注册 raw .list URL）

def test_content_unknown_404(admin, routes):  # /geosite/nope/content 与 /bad/openai/content → 404

def test_content_upstream_missing_returns_502(admin, routes):  # 索引含 openai 但 .list 路由缺失 → 502
```

- [ ] **Step 2: 运行确认失败** — `cd backend && uv run pytest tests/test_api_rule_library.py -v`，Expected: 404 断言失败
- [ ] **Step 3: 实现路由并在 `create_app` 注册**（同步 `def` 端点；FastAPI 自动放入线程池）
- [ ] **Step 4: 运行全部后端测试** — `cd backend && uv run pytest -q`，Expected: 全部 PASS
- [ ] **Step 5: 提交** — `git commit -m "feat(rule-library): 新增规则库 API"`

---

### Task 3: 前端类型、API 与纯逻辑

**Files:**
- Modify: `frontend/src/api/types.ts`、`frontend/src/api/index.ts`
- Create: `frontend/src/lib/ruleLibrary.ts`
- Test: `frontend/src/lib/ruleLibrary.test.ts`

**Interfaces:**
- Consumes: Task 2 的 JSON 结构；`insertBeforeMatch`（`lib/profile.ts`）。
- Produces:
  - types: `LibraryCategory = 'geosite' | 'geoip' | 'geo-lite'`；`LibraryItem { category: LibraryCategory; name: string; behavior: 'domain' | 'ipcidr'; url: string }`；`LibraryIndex { updated_at: string | null; error: string | null; items: LibraryItem[] }`；`RuleContent { total: number; lines: string[]; truncated: boolean }`
  - api: `ruleLibrary(): Promise<LibraryIndex>`、`refreshRuleLibrary(): Promise<LibraryIndex>`、`ruleContent(category, name): Promise<RuleContent>`（name 用 `encodeURIComponent`）
  - `LIBRARY_CATEGORIES: { value: LibraryCategory; label: string }[]`
  - `searchLibrary(items: LibraryItem[], category: LibraryCategory, query: string): LibraryItem[]`
  - `canUseGeoRule(item: LibraryItem): boolean`
  - `type AddMode = 'rule-set' | 'geo'`
  - `interface AddResult { profile: Profile; status: 'added' | 'exists'; index: number; target: string }`（`index` 为新增/已存在规则的 0 基下标，`target` 为该规则的目标）
  - `addLibraryRule(profile: Profile, item: LibraryItem, mode: AddMode, target: string): AddResult` — 不修改入参

- [ ] **Step 1: 写失败测试**

```ts
const openai: LibraryItem = { category: 'geosite', name: 'openai', behavior: 'domain', url: '.../geo/geosite/openai.mrs' }
// 用真实 URL 常量；另建 tg(geoip/telegram)、aiNotCn(geosite/category-ai-!cn，URL 与 ai.yaml 相同)、apple(geo-lite)

it('search ranks exact > prefix > contains and filters category')
  // items: openai, openai-extra, category-ai-!cn(包含 "ai")，query 'ai' 无完全匹配；query 'openai' → ['openai','openai-extra']
it('search is case-insensitive')  // query 'OpenAI' → 第一个是 openai
it('rule-set mode creates provider and inserts before MATCH')
  // r.status 'added'；provider {name:'geosite-openai', behavior:'domain', format:'mrs', url, interval:86400}；
  // rules[r.index] = {type:'RULE-SET', value:'geosite-openai', values:[], target, no_resolve:false}；最后一条仍是 MATCH
it('reuses provider created by template')
  // profile 已有 {name:'category-ai-not-cn', url: aiNotCn.url} 且无规则引用 → 不新增 provider，新规则 value 'category-ai-not-cn'
it('suffixes name on conflict')  // 已有 name 'geosite-openai' 但 URL 不同 → 新 provider 'geosite-openai-2'
it('geoip defaults no_resolve and geo mode')  // geo 模式 tg → {type:'GEOIP', value:'telegram', no_resolve:true}；rule-set 模式也 no_resolve:true
it('geo-lite cannot use geo mode')  // canUseGeoRule(apple) false；addLibraryRule(..., 'geo') 抛 Error
it('skips duplicate and reports existing rule')
  // 已有 GEOSITE openai → 'X'：rule-set 模式加 openai 到 'Y' → status 'exists'，index 指向它，target 'X'，profile 未新增 provider/rule
  // 已有 RULE-SET 引用 URL 相同的 provider → geo 模式同样 'exists'
it('appends when there is no MATCH')
it('does not mutate input')
```

- [ ] **Step 2: 运行确认失败** — `cd frontend && npx vitest run src/lib/ruleLibrary.test.ts`，Expected: 找不到模块
- [ ] **Step 3: 实现**

重复判断：某条非 MATCH 规则满足以下任一即视为重复——`RULE-SET` 且其 provider 的 `url === item.url`；或 `type` 等于该分类对应的 GEOSITE/GEOIP 且 `value.toLowerCase() === item.name.toLowerCase()`。重复时直接返回原 profile。前缀映射 `{geosite:'geosite-', geoip:'geoip-', 'geo-lite':'geolite-'}`。搜索同一档内按名字字母序；空 query 返回该分类全部（字母序）。

- [ ] **Step 4: 运行确认通过** — `cd frontend && npx vitest run`，Expected: 全部 PASS
- [ ] **Step 5: 提交** — `git commit -m "feat(rule-library): 前端类型、API 与加入规则逻辑"`

---

### Task 4: 共用组件 RuleLibraryBrowser

**Files:**
- Create: `frontend/src/components/RuleLibraryBrowser.vue`

**Interfaces:**
- Consumes: Task 3 的 api、`searchLibrary`、`LIBRARY_CATEGORIES`。
- Produces: `<RuleLibraryBrowser>`，无 props；作用域插槽 `#actions="{ item }"`（`item: LibraryItem`，仅在选中时渲染）。

行为：
- 索引存放在模块级 `ref`（`<script>` 非 setup 块或单独模块变量），同一页面会话内重开抽屉不重新请求；「刷新」调用 `refreshRuleLibrary`。
- 加载失败（ApiError）时显示 `NResult`/`NAlert` 错误文案 + 「重试」按钮；`index.error` 非空时在列表上方显示黄色提示（数据可能过期）。
- 顶部：`NTabs`（分类）+ 搜索 `NInput`（clearable）+ 更新时间（`formatTime(index.updated_at)`，来自 `lib/format.ts`）+ 刷新按钮。
- 左：`NVirtualList` 结果列表（item-size 32），点击选中，高亮当前项；显示结果数量。
- 右（窄于 768px 时在下方）：选中项的分类/名字、可选中的 mono URL、`total` 条数、`truncated` 提示（"仅显示前 50000 条"）、「在结果内筛选」输入框、`NVirtualList` 条目列表；内容加载中 `NSpin`，失败显示错误文案。切换选中项时丢弃过期请求的结果（比较请求时的 item 与当前 item）。
- 插槽区放在预览上方。

- [ ] **Step 1: 实现组件**
- [ ] **Step 2: 类型检查** — `cd frontend && npx vue-tsc --noEmit`，Expected: 无错误
- [ ] **Step 3: 提交** — `git commit -m "feat(rule-library): 规则库浏览组件"`

（组件交互在 Task 5/6 接入后用浏览器手动验证。）

---

### Task 5: 独立「规则库」页面

**Files:**
- Create: `frontend/src/views/RuleLibraryView.vue`
- Modify: `frontend/src/router.ts`（`{ path: '/rule-library', name: 'rule-library', component: RuleLibraryView, meta: { title: '规则库', order: 4 } }`，`settings` 的 order 改为 5）

**Interfaces:**
- Consumes: `RuleLibraryBrowser`、`addLibraryRule`、`canUseGeoRule`、`copyText`、`api.listProfiles/getProfile/saveProfile`、`targetOptions`。

行为：`PageHeader` + `RuleLibraryBrowser`，`#actions` 中三个按钮：「复制名称」「复制 URL」（成功/失败用 `useMessage` 提示）、「加入到方案」。后者打开 `NModal`：方案下拉（`listProfiles`）→ 选中后 `getProfile` 取分组生成目标下拉（默认第一个分组，否则 `DIRECT`）→ 加入方式单选（RULE-SET 默认；`canUseGeoRule` 为 false 时 geo 选项禁用）→ 确认：对**刚获取的** profile 调 `addLibraryRule`；`exists` → `message.warning(\`已存在：第 ${index + 1} 条 → ${target}\`)` 不保存；`added` → `saveProfile`，成功提示「已加入「方案名」」，保存失败显示 ApiError 消息。

- [ ] **Step 1: 实现页面与路由**
- [ ] **Step 2: 类型检查与构建** — `cd frontend && npm run build`，Expected: 成功
- [ ] **Step 3: 手动验证**（`run` skill 启动前后端）：菜单出现「规则库」且位于「配置方案」与「设置」之间；搜索 `openai` → 预览出现 `openai.com` 等；复制 URL 与 `ai.yaml` 格式一致；加入到某方案后在方案编辑页「规则集」「规则」中可见；再次加入提示「已存在」。
- [ ] **Step 4: 提交** — `git commit -m "feat(rule-library): 新增规则库页面"`

---

### Task 6: 方案编辑页抽屉

**Files:**
- Modify: `frontend/src/components/RuleEditor.vue`

**Interfaces:**
- Consumes: `RuleLibraryBrowser`、`addLibraryRule`、`canUseGeoRule`、`targets` / `defaultTarget`（组件内已有）。

行为：在底部「添加规则」按钮旁加「从规则库添加」按钮（两者并排）；`NDrawer`（宽度 `min(760px, 100vw)`，`placement="right"`）内放 `RuleLibraryBrowser`；`#actions`：目标分组 `NSelect`（选项 `targets`，初值 `defaultTarget`，抽屉关闭后保留用户选择）+「加入为 RULE-SET」+「用 GEOSITE 规则」/「用 GEOIP 规则」（按分类显示文字，`canUseGeoRule` 为 false 时禁用并 title 提示"精简规则只能以规则集方式加入"）。点击后 `addLibraryRule(profile.value, ...)`：`exists` → warning「已存在：第 N 条 → X」；`added` → `profile.value = result.profile`，success「已加入：<名字> → <目标>」。抽屉保持打开；不自动保存（沿用编辑页现有的保存流程）。

- [ ] **Step 1: 实现**
- [ ] **Step 2: 构建与全部测试** — `cd frontend && npm run build && npm test`，`cd backend && uv run pytest -q`，Expected: 全部成功
- [ ] **Step 3: 手动验证**：编辑方案 → 规则 → 从规则库添加 → 连续加入 `openai`（RULE-SET）、geoip `telegram`（GEOIP，no-resolve 已勾）→ 规则列表在 MATCH 前出现两条、规则集标签出现 `geosite-openai`；重复加入提示已存在；geo-lite 项的 GEOSITE 按钮禁用；保存后「预览与订阅」无报错。
- [ ] **Step 4: 提交** — `git commit -m "feat(rule-library): 方案编辑页支持从规则库添加规则"`
