# 在线规则库（Rule Library）设计

日期：2026-11-01

## 意图

现在给方案写 GEOSITE / GEOIP 规则或添加规则集时，用户要去 GitHub 上的 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) 翻目录，找到准确的规则名，再把名字或 URL 复制回 routeforge。这个过程很麻烦，而且容易拼错（比如 `category-ai-!cn`）。

目标是在 routeforge 里直接**搜索规则名、查看规则内容（包含哪些域名/IP 段）、一键加入方案**，以后不用再打开 GitHub。

用户在美国，服务器可以直连 GitHub，不需要镜像或代理。

## 目标

1. 能按名字搜索 meta-rules-dat 中的 geosite、geoip、geo-lite/geosite 三类规则。
2. 能预览某条规则里的全部条目（域名或 IP 段），用来判断它是不是自己要的那条。
3. 能一键加入方案，支持两种方式：
   - **RULE-SET**（默认）：自动创建规则集（名称、behavior、format、URL 全部填好），并插入一条引用它的规则；
   - **GEOSITE / GEOIP**：插入一条单独的规则。
4. 有两个入口，共用同一个浏览组件：
   - 侧边栏新增独立的「规则库」页面，用来浏览和查阅；
   - 方案编辑页「规则」标签下的「从规则库添加」抽屉，用来边编辑边添加。

## 非目标

- `asn` 目录、其他规则仓库、自定义规则源。
- 镜像、代理、jsDelivr 等加速（用户可以直连 GitHub）。
- 在 routeforge 里编辑规则内容。
- 离线可用（GitHub 不可达时，只要求给出清楚的报错）。

## 反目标（技术上能跑，但做成这样就算失败）

- 每敲一个字就去请求 GitHub，或者很容易撞上 GitHub API 的限流（未认证时 60 次/小时）。
- 重复加入同一条规则时，生成多个一样的规则集。
- 预览像 `geosite/cn` 这种几万行的大规则时，页面卡死。

## 数据来源（已确认的事实）

仓库默认分支是 `meta`，相关目录如下：

| 分类 | 目录 | 数量（2026-11） | behavior |
|---|---|---|---|
| geosite | `geo/geosite` | 约 2018 | domain |
| geoip | `geo/geoip` | 约 260 | ipcidr |
| geo-lite | `geo-lite/geosite` | 24 | domain |

- 每条规则都有 `.mrs`、`.yaml`、`.list` 三种文件；每个目录下另有一个 `classical` 子目录，不纳入规则库。
- 用 `GET https://api.github.com/repos/MetaCubeX/meta-rules-dat/git/trees/meta:<目录>` 一次请求就能拿到整个目录的列表（没有被截断）。刷新一次索引只需要 3 次请求。
- 规则名 = 去掉扩展名的文件名，以 `.mrs` 文件为准。
- 写进配置的 URL 沿用现有模板 `templates/ai.yaml` 的格式：
  `https://github.com/MetaCubeX/meta-rules-dat/raw/meta/<目录>/<name>.mrs`
- 预览内容读取同名的 `.list` 文件（纯文本，一行一条）。

## 后端

新建 `routeforge/rule_library.py`（负责拉取和缓存）和 `routeforge/api/rule_library.py`（路由，需要管理员权限，写法和 `api/templates.py` 一样）。HTTP 请求统一使用 `app.state.http`。

**索引缓存**
- 放在内存里，有效期 24 小时。第一次请求时才去拉取。
- 刷新失败时：如果有旧数据，就继续返回旧数据，并带上错误信息；如果完全没有数据，返回 502 和一条清楚的中文报错。
- 提供手动刷新接口。

**接口**
- `GET /api/rule-library` → `{updated_at, error?, items: [{category, name, behavior, url}]}`。总共约 2300 条，一次性全部返回，**搜索在前端做**，不会每敲一个字就请求一次。
- `POST /api/rule-library/refresh` → 强制刷新索引，返回内容和上面一样。
- `GET /api/rule-library/{category}/{name}/content` → `{total, lines, truncated}`。
  - 去掉空行和注释行。
  - 最多返回 50000 行；超过时 `truncated=true`，`total` 仍然是真实的总行数。
  - 结果放进 LRU 缓存（大约保留 50 条，有效期 24 小时）。
  - `category` 必须是那三个分类之一，`name` 必须在索引里存在，否则返回 404。这样也避免了被拿来拼接任意 URL。

**测试**：用 mock 的 httpx client 测试（沿用 `tests/conftest.py` 里现有的写法），覆盖以下情况：解析目录列表、排除 `classical`、缓存命中、刷新失败时返回旧数据、内容截断、非法分类或规则名返回 404。

## 前端

**共用组件 `components/RuleLibraryBrowser.vue`**
- 顶部是分类标签（geosite / geoip / geo-lite），下面是搜索框。
- 搜索结果的排序：完全匹配 > 前缀匹配 > 包含匹配。用虚拟列表展示（`NVirtualList`）。
- 选中一条后，右侧（窄屏时在下方）显示预览：
  - 完整 URL；
  - 总条数；
  - 条目列表，使用虚拟滚动，并带一个"在结果内筛选"的输入框；
  - 被截断时显示提示。
- 显示索引的更新时间，并提供「刷新」按钮。
- 操作按钮通过 slot 由外层传入，两个入口各放各的按钮。

**独立页面 `views/RuleLibraryView.vue`**
- 路由 `/rule-library`，菜单名「规则库」，在菜单中排在「配置方案」和「设置」之间。
- 操作按钮：复制名称、复制 URL（使用 `lib/clipboard`）、「加入到方案 ▾」。
- 点「加入到方案」后，选择方案和目标分组，再选择加入方式（RULE-SET 或 GEOSITE/GEOIP）。确认后先 GET 该方案，在前端套用下面的加入逻辑，再 PUT 回去，最后提示成功。

**编辑页抽屉**
- 在 `RuleEditor.vue` 的「添加规则」按钮旁边，加一个「从规则库添加」按钮，点击后打开右侧 `NDrawer`，里面放 `RuleLibraryBrowser`。
- 抽屉里的操作区：目标分组下拉框（默认值和现在新建规则时一样），加上「加入为 RULE-SET」和「用 GEOSITE/GEOIP 规则」两个按钮。
- 加入后抽屉**保持打开**，方便连续添加多条，并提示成功。改动和其他编辑一样，要等用户点保存才生效。

**加入逻辑：`lib/profile.ts` 里的纯函数 `addLibraryRule(profile, item, mode, target)`，两个入口共用**
- **RULE-SET 模式**
  - 如果方案里已经有 URL 相同的规则集，直接复用；
  - 如果没有，就新建一个规则集：`name` 为 `<分类前缀>-<规则名>`（`geosite-` / `geoip-` / `geolite-`，原样保留 `!` 等字符），behavior 由分类决定，`format: mrs`，`interval: 86400`；*（设计者的决定：命名和渲染器 `_geosite_to_rule_sets` 的 `geosite-<category>` 保持一致，渲染器本身就生成带 `!` 的名字，说明 `!` 没问题）*
  - 如果名字已被 URL 不同的另一个规则集占用，就加 `-2`、`-3`……（和渲染器的做法一样）；
  - 然后用 `insertBeforeMatch` 插入一条 `RULE-SET` 规则。
- **GEOSITE/GEOIP 模式**
  - 插入一条 `GEOSITE <name>`（geosite）或 `GEOIP <name>`（geoip）规则；
  - geo-lite 分类不提供这个模式（客户端自带的 geodata 里不一定有这些精简规则），按钮直接禁用。
- geoip 分类的规则默认勾选 `no_resolve`。
- **重复规则** *（设计者的决定）*：如果方案里已经有一条非 MATCH 规则匹配同一个东西（RULE-SET 引用了同一个规则集，或者 GEOSITE/GEOIP 的值相同，不区分大小写），就不再插入，改为提示「已存在：第 N 条 → 分组 X」。目标分组不同也一样跳过，因为排在后面的那条永远不会命中。所以 `addLibraryRule` 除了返回新的 profile，还要返回状态（`added` / `exists`，以及已有规则的位置和目标分组），两个入口据此决定提示内容。
- 注：渲染器已经会把 GEOSITE 规则改写成引用 meta-rules-dat `.mrs` 的规则集，所以对 geosite 来说，两种加入方式最终输出是一样的，区别只在方案里怎么显示。GEOIP 仍然依赖客户端本地的 geoip 数据库。
- 前端单元测试覆盖：新建规则集、复用已有规则集、重名加数字后缀、重复规则跳过并返回已有位置、插入到 MATCH 之前、no_resolve 默认值、geo-lite 禁用 GEOSITE 模式。

## 其他

- 把 `.superpowers/` 加入 `.gitignore`。

## 留给实现者决定

- 具体的视觉细节、窄屏下的布局、文案措辞。
- 后端拉取 GitHub 时用同步还是异步（参考现有 `httpx.Client` 的用法）。
- 预览筛选框的具体交互方式。
- 50000 行上限、50 条 LRU 这两个数字，可以根据实测调整。
