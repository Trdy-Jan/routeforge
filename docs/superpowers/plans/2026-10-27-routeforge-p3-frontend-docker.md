# RouteForge P3 前端与 Docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 RouteForge 的 Vue 管理界面（登录、节点源、节点、配置方案编辑与预览），由 FastAPI 托管构建产物，并打包为单个 Docker 镜像。

**Architecture:** `frontend/` 为独立的 Vite + Vue 3 + TypeScript 项目，开发时代理 `/api`、`/sub` 到后端；生产构建产物拷贝进镜像，由后端 `ROUTEFORGE_STATIC_DIR` 托管（SPA 回退到 `index.html`）。前端只通过 `src/api/` 调用 P2 的 REST 接口；方案编辑的纯逻辑放在 `src/lib/profile.ts` 并用 Vitest 测试，界面组件做手动冒烟测试（spec 第 12 节）。

**Tech Stack:** Vue 3.5、vue-router 4、Naive UI 2、Vite 6、TypeScript 5.8、vue-tsc 2、Vitest 3；Docker（node:24-alpine 构建、python:3.12-slim 运行、uv 0.10.8）

**Spec:** `docs/superpowers/specs/2026-10-26-routeforge-design.md`

**前置：** P1、P2 已完成（`docs/superpowers/plans/2026-10-27-routeforge-p1-core.md`、`...-p2-server.md`）。

## Global Constraints

- 前端命令在 `frontend/` 下执行；后端命令在 `backend/` 下执行
- 依赖锁定大版本：`vue ^3.5.13`、`vue-router ^4.5.0`、`naive-ui ^2.41.0`、`vite ^6.3.0`、`@vitejs/plugin-vue ^5.2.0`、`typescript ~5.8.3`、`vue-tsc ^2.2.0`、`vitest ^3.1.0`、`@vue/tsconfig ^0.7.0`、`@types/node ^22.0.0`（npm 上已有更新的大版本，本期不升级）
- `@vue/tsconfig` 启用了 `verbatimModuleSyntax`：类型必须用 `import type` / `type` 修饰导入
- 界面语言为中文，使用 Naive UI 的 `zhCN` locale
- Naive UI 的 `NSelect`、`NRadioGroup` 等组件 `update:value` 参数为宽联合类型：模板中不对它们用 `v-model` 绑定窄类型状态，而是写 `:value` + `@update:value="(v: unknown) => (x = v as T)"`，避免 vue-tsc 报错（`NInput`、`NInputNumber` 可直接用 `v-model`）
- 所有写请求带 `Content-Type: application/json`（无请求体时发送 `{}`），与 P2 的 415 规则一致
- 后端返回的时间是不带时区的 UTC 字符串，前端按 UTC 解析后用本地时间显示
- 开发联调：后端以 `ROUTEFORGE_ADMIN_PASSWORD=pw ROUTEFORGE_COOKIE_SECURE=false uv run routeforge` 启动（8000 端口），前端 `npm run dev`（5173 端口）
- 每个界面任务的验收：`npm run build` 通过（含 vue-tsc 类型检查）+ 按任务列出的步骤在浏览器中手动检查

## Review Focus

1. **分组改名** → 所有引用该分组的成员、规则目标、链式代理前置同步改名，不产生悬空引用（Task 2 `renameGroup` 测试）
2. **新增规则时方案已有 MATCH** → 新规则插在 MATCH 之前，MATCH 始终在末尾（Task 2 `insertBeforeMatch` 测试）
3. **会话过期后任意操作返回 401** → 自动跳转登录页，登录后回到原页面（Task 2 客户端测试 + Task 3 手动检查）
4. **后端 422 校验错误（detail 为数组）** → 以可读中文提示显示，而不是 `[object Object]`（Task 2 客户端测试）
5. **直接访问 `/profiles/3` 等前端路由或刷新页面** → 后端返回 `index.html` 而不是 404；`/api/*` 未知路径仍返回 JSON 404（Task 1 测试）

## File Structure

```
backend/routeforge/web.py          mount_frontend(app, static_dir)：静态资源 + SPA 回退
backend/tests/test_web.py
frontend/
  package.json  vite.config.ts  tsconfig.json  index.html  env.d.ts
  src/
    main.ts  App.vue  router.ts
    api/client.ts      request()、ApiError、setUnauthorizedHandler()
    api/types.ts       与 P2 接口对应的 TS 类型
    api/index.ts       api.* 各接口函数、buildQuery()
    lib/format.ts      formatBytes、formatTime、formatEpoch
    lib/profile.ts     方案编辑纯函数
    lib/clipboard.ts   copyText()
    views/LoginView.vue  SourcesView.vue  NodesView.vue  ProfilesView.vue  ProfileEditView.vue
    components/GroupEditor.vue  FilterForm.vue  RuleEditor.vue  ProviderEditor.vue  ChainEditor.vue  PreviewPanel.vue
    api/client.test.ts  lib/format.test.ts  lib/profile.test.ts
Dockerfile  .dockerignore  docker-compose.yml  .env.example  README.md
```

---

### Task 1: 后端托管前端构建产物

**Files:**
- Create: `backend/routeforge/web.py`
- Modify: `backend/routeforge/app.py`（在所有 `include_router` 之后挂载前端）
- Test: `backend/tests/test_web.py`

**Interfaces:**
- Consumes: P2 `create_app`、`Settings.static_dir`；`tests.helpers.mock_client`
- Produces: `mount_frontend(app: FastAPI, static_dir: Path) -> None`：`/assets/*` 走 StaticFiles；其他 GET 路径若是 `static_dir` 内的文件则直接返回，否则返回 `index.html`；以 `api/`、`sub/` 开头的路径返回 404

- [ ] **Step 1: 写失败测试 `backend/tests/test_web.py`**

```python
import pytest
from fastapi.testclient import TestClient

from routeforge.app import create_app
from routeforge.config import Settings
from tests.helpers import ADMIN_PASSWORD, mock_client


@pytest.fixture
def web_client(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "favicon.ico").write_bytes(b"ICO")
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    settings = Settings(data_dir=tmp_path, database_url="sqlite://", admin_password=ADMIN_PASSWORD,
                        cookie_secure=False, static_dir=static)
    with TestClient(create_app(settings, http_client=mock_client({}), start_scheduler=False)) as c:
        yield c


def test_index_and_spa_fallback(web_client):
    assert web_client.get("/").text == "<html>INDEX</html>"
    assert web_client.get("/profiles/3").text == "<html>INDEX</html>"


def test_static_files(web_client):
    js = web_client.get("/assets/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert web_client.get("/favicon.ico").content == b"ICO"


def test_api_and_sub_paths_are_not_swallowed(web_client):
    resp = web_client.get("/api/unknown")
    assert resp.status_code == 404 and resp.headers["content-type"].startswith("application/json")
    assert web_client.get("/sub/nope").status_code == 404
    assert web_client.get("/api/auth/me").status_code == 401


def test_path_traversal_returns_index_not_file(web_client):
    resp = web_client.get("/..%2Fsecret.txt")
    assert "SECRET" not in resp.text


def test_no_static_dir_means_no_frontend(client):
    assert client.get("/").status_code == 404
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_web.py -v`
Expected: FAIL（`/` 返回 404）

- [ ] **Step 3: 实现 `backend/routeforge/web.py`**

```python
"""托管前端构建产物（单页应用）。"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_RESERVED_PREFIXES = ("api/", "sub/")


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()
    index = root / "index.html"
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(_RESERVED_PREFIXES) or path in ("api", "sub"):
            raise HTTPException(status_code=404)
        if path:
            candidate = (root / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        return FileResponse(index)
```

- [ ] **Step 4: 在 `app.py` 挂载**

导入追加 `from routeforge.web import mount_frontend`，在最后一个 `app.include_router(...)` 之后、`return app` 之前加入：

```python
    if settings.static_dir is not None:
        mount_frontend(app, settings.static_dir)
```

- [ ] **Step 5: 运行确认通过**

Run: `uv run pytest -v`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add backend/routeforge/web.py backend/routeforge/app.py backend/tests/test_web.py
git commit -m "feat(server): serve the built frontend with SPA fallback"
```

---

### Task 2: 前端骨架、API 客户端与方案编辑纯函数

**Files:**
- Create: `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`、`frontend/env.d.ts`
- Create: `frontend/src/api/client.ts`、`frontend/src/api/types.ts`、`frontend/src/api/index.ts`
- Create: `frontend/src/lib/format.ts`、`frontend/src/lib/profile.ts`
- Test: `frontend/src/api/client.test.ts`、`frontend/src/lib/format.test.ts`、`frontend/src/lib/profile.test.ts`

**Interfaces:**
- Consumes: P2 全部 REST 接口（字段名与 P2 Task 5/6/7 的 Produces 一致）
- Produces:
  - `client.ts`: `class ApiError extends Error { status: number }`、`request<T>(method, path, body?) => Promise<T>`、`setUnauthorizedHandler(fn: (() => void) | null)`
  - `types.ts`: `Source`、`SourceKind`、`SourceInput`、`SourcePatch`、`UserInfo`、`LineError`、`ImportResult`、`RefreshResult`、`NodeItem`、`Member`、`FilterMember`、`GroupType`、`ProxyGroup`、`RULE_TYPES`、`RuleType`、`Rule`、`RuleProvider`、`Chain`、`Profile`、`ProfileSummary`、`ProfileDetail`、`Preview`、`TemplateInfo`
  - `index.ts`: `api` 对象（见代码）、`buildQuery(params)`
  - `format.ts`: `formatBytes(n?)`、`formatTime(iso?)`、`formatEpoch(seconds?)`
  - `profile.ts`: `BUILTIN_TARGETS`、`DEFAULT_TEST_URL`、`newGroup(name)`、`newRule(target)`、`moveItem(list, index, delta)`、`insertBeforeMatch(rules, rule)`、`sameMember(a, b)`、`memberLabel(m, nodes, sources)`、`renameGroup(profile, from, to)`、`targetOptions(profile)`、`subscriptionUrl(origin, token)`

- [ ] **Step 1: 创建工程文件**

`frontend/package.json`：

```json
{
  "name": "routeforge-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "naive-ui": "^2.41.0",
    "vue": "^3.5.13",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@vitejs/plugin-vue": "^5.2.0",
    "@vue/tsconfig": "^0.7.0",
    "typescript": "~5.8.3",
    "vite": "^6.3.0",
    "vitest": "^3.1.0",
    "vue-tsc": "^2.2.0"
  }
}
```

`frontend/vite.config.ts`：

```ts
/// <reference types="vitest/config" />
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/sub': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'node',
  },
})
```

`frontend/tsconfig.json`：

```json
{
  "extends": "@vue/tsconfig/tsconfig.dom.json",
  "compilerOptions": {
    "types": ["vite/client"],
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["env.d.ts", "src/**/*.ts", "src/**/*.vue"]
}
```

`frontend/env.d.ts`：

```ts
/// <reference types="vite/client" />
```

`frontend/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>RouteForge</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

Run: `cd frontend && npm install`
Expected: 生成 `package-lock.json` 与 `node_modules/`（已在 `.gitignore` 中）

- [ ] **Step 2: 写失败测试**

`frontend/src/api/client.test.ts`：

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request, setUnauthorizedHandler } from './client'

function mockFetch(status: number, body?: unknown) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) =>
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('request', () => {
  it('sends JSON with content type on POST', async () => {
    const fn = mockFetch(200, { ok: true })
    expect(await request('POST', '/api/x', { a: 1 })).toEqual({ ok: true })
    const init = fn.mock.calls[0][1]!
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"a":1}')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('sends {} when a write has no body', async () => {
    const fn = mockFetch(200, {})
    await request('POST', '/api/x')
    expect(fn.mock.calls[0][1]!.body).toBe('{}')
  })

  it('sends no body on GET and DELETE', async () => {
    const fn = mockFetch(200, [])
    await request('GET', '/api/x')
    expect(fn.mock.calls[0][1]!.body).toBeUndefined()
  })

  it('returns undefined for 204', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    expect(await request('DELETE', '/api/x/1')).toBeUndefined()
  })

  it('uses string detail as error message', async () => {
    mockFetch(400, { detail: '手动节点源无需刷新' })
    await expect(request('POST', '/api/x')).rejects.toMatchObject({ status: 400, message: '手动节点源无需刷新' })
  })

  it('joins 422 validation messages', async () => {
    mockFetch(422, { detail: [{ msg: 'Value error, 订阅源需要 http(s) 链接' }, { msg: 'Field required' }] })
    await expect(request('POST', '/api/x')).rejects.toThrow('Value error, 订阅源需要 http(s) 链接；Field required')
  })

  it('falls back to status text when body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('oops', { status: 502 })))
    await expect(request('GET', '/api/x')).rejects.toThrow('请求失败（HTTP 502）')
  })

  it('calls the unauthorized handler on 401', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    mockFetch(401, { detail: '未登录' })
    await expect(request('GET', '/api/x')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledOnce()
  })
})
```

`frontend/src/lib/format.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { formatBytes, formatEpoch, formatTime } from './format'

describe('format', () => {
  it('formats bytes', () => {
    expect(formatBytes(undefined)).toBe('—')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(10 * 1024 ** 3)).toBe('10.0 GB')
  })

  it('treats naive backend timestamps as UTC', () => {
    const expected = new Date('2026-01-01T00:00:00Z').toLocaleString('zh-CN', { hour12: false })
    expect(formatTime('2026-01-01T00:00:00')).toBe(expected)
    expect(formatTime('2026-01-01T00:00:00.123456')).toBe(expected)
    expect(formatTime(null)).toBe('—')
  })

  it('formats epoch seconds as a date', () => {
    expect(formatEpoch(0)).toBe(new Date(0).toLocaleDateString('zh-CN'))
    expect(formatEpoch(undefined)).toBe('—')
  })
})
```

`frontend/src/lib/profile.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import type { NodeItem, Profile, Source } from '../api/types'
import {
  insertBeforeMatch, memberLabel, moveItem, newGroup, newRule, renameGroup, sameMember,
  subscriptionUrl, targetOptions,
} from './profile'

const base: Profile = {
  name: 'p',
  groups: [
    { ...newGroup('节点选择'), members: [{ kind: 'group', name: '自动' }, { kind: 'builtin', name: 'DIRECT' }] },
    newGroup('自动'),
  ],
  rules: [
    { type: 'DOMAIN-SUFFIX', value: 'a.com', target: '自动', no_resolve: false },
    { type: 'MATCH', value: '', target: '节点选择', no_resolve: false },
  ],
  rule_providers: [],
  chains: [{ node: { kind: 'node', node_id: 1 }, via: { kind: 'group', name: '自动' } }],
}

describe('profile helpers', () => {
  it('renameGroup updates every reference', () => {
    const p = renameGroup(base, '自动', '自动测速')
    expect(p.groups.map((g) => g.name)).toEqual(['节点选择', '自动测速'])
    expect(p.groups[0].members[0]).toEqual({ kind: 'group', name: '自动测速' })
    expect(p.rules[0].target).toBe('自动测速')
    expect(p.chains[0].via).toEqual({ kind: 'group', name: '自动测速' })
    expect(base.groups[1].name).toBe('自动') // 不修改原对象
  })

  it('insertBeforeMatch keeps MATCH last', () => {
    const rules = insertBeforeMatch(base.rules, newRule('DIRECT'))
    expect(rules.map((r) => r.type)).toEqual(['DOMAIN-SUFFIX', 'DOMAIN-SUFFIX', 'MATCH'])
    expect(insertBeforeMatch([], newRule('DIRECT'))).toHaveLength(1)
  })

  it('moveItem swaps neighbours and ignores out-of-range moves', () => {
    expect(moveItem([1, 2, 3], 0, 1)).toEqual([2, 1, 3])
    expect(moveItem([1, 2, 3], 0, -1)).toEqual([1, 2, 3])
    expect(moveItem([1, 2, 3], 2, 1)).toEqual([1, 2, 3])
  })

  it('sameMember compares by kind and identity', () => {
    expect(sameMember({ kind: 'node', node_id: 1 }, { kind: 'node', node_id: 1 })).toBe(true)
    expect(sameMember({ kind: 'node', node_id: 1 }, { kind: 'group', name: '1' })).toBe(false)
    const f = { kind: 'filter', source_id: null, name_regex: 'HK', exclude_regex: null } as const
    expect(sameMember(f, { ...f })).toBe(true)
    expect(sameMember(f, { ...f, exclude_regex: 'x' })).toBe(false)
  })

  it('memberLabel describes each member kind', () => {
    const nodes = new Map<number, NodeItem>([[1, { id: 1, name: '香港 01' } as NodeItem]])
    const sources = new Map<number, Source>([[2, { id: 2, name: '机场' } as Source]])
    expect(memberLabel({ kind: 'node', node_id: 1 }, nodes, sources)).toBe('香港 01')
    expect(memberLabel({ kind: 'node', node_id: 9 }, nodes, sources)).toBe('#9（已删除）')
    expect(memberLabel({ kind: 'group', name: '自动' }, nodes, sources)).toBe('分组：自动')
    expect(memberLabel({ kind: 'builtin', name: 'REJECT' }, nodes, sources)).toBe('REJECT')
    expect(memberLabel({ kind: 'filter', source_id: 2, name_regex: 'HK', exclude_regex: 'x0' }, nodes, sources))
      .toBe('过滤：机场 /HK/ 排除 /x0/')
    expect(memberLabel({ kind: 'filter', source_id: null, name_regex: '', exclude_regex: null }, nodes, sources))
      .toBe('过滤：全部节点源 /(全部)/')
  })

  it('targetOptions lists groups then builtins', () => {
    expect(targetOptions(base)).toEqual(['节点选择', '自动', 'DIRECT', 'REJECT'])
  })

  it('subscriptionUrl joins origin and token', () => {
    expect(subscriptionUrl('https://rf.example.com', 'abc')).toBe('https://rf.example.com/sub/abc')
  })
})
```

- [ ] **Step 3: 运行确认失败**

Run: `npm test`
Expected: FAIL（找不到 `./client`、`./format`、`./profile`）

- [ ] **Step 4: 实现 `frontend/src/api/client.ts`**

```ts
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn
}

export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: 'same-origin' }
  if (method !== 'GET' && method !== 'DELETE') {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body ?? {})
  }
  const resp = await fetch(path, init)
  if (resp.status === 401) onUnauthorized?.()
  if (!resp.ok) throw new ApiError(resp.status, await errorMessage(resp))
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

async function errorMessage(resp: Response): Promise<string> {
  try {
    const data = await resp.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail)) return data.detail.map((d: { msg: string }) => d.msg).join('；')
  } catch {
    // 响应不是 JSON
  }
  return `请求失败（HTTP ${resp.status}）`
}
```

- [ ] **Step 5: 实现 `frontend/src/api/types.ts`**

```ts
export type SourceKind = 'manual' | 'subscription'

export interface UserInfo {
  upload?: number
  download?: number
  total?: number
  expire?: number
}

export interface Source {
  id: number
  kind: SourceKind
  name: string
  url: string | null
  refresh_interval: number
  user_agent: string
  last_fetched_at: string | null
  last_error: string | null
  userinfo: UserInfo | null
  node_count: number
}

export interface SourceInput {
  kind: SourceKind
  name: string
  url?: string
  refresh_interval?: number
  user_agent?: string
}

export type SourcePatch = Partial<Pick<Source, 'name' | 'refresh_interval' | 'user_agent'>> & { url?: string }

export interface LineError {
  line: string
  message: string
}

export interface ImportResult {
  added: number
  errors: LineError[]
}

export interface RefreshResult {
  ok: boolean
  error: string | null
  added: number
  updated: number
  removed: number
  parse_errors: LineError[]
}

export interface NodeItem {
  id: number
  source_id: number
  name: string
  type: string
  server: string
  port: number
  enabled: boolean
  position: number
  data: Record<string, unknown>
}

export interface FilterMember {
  kind: 'filter'
  source_id: number | null
  name_regex: string
  exclude_regex: string | null
}

export type Member =
  | { kind: 'node'; node_id: number }
  | { kind: 'group'; name: string }
  | { kind: 'builtin'; name: 'DIRECT' | 'REJECT' }
  | FilterMember

export type GroupType = 'select' | 'url-test' | 'fallback' | 'load-balance'

export interface ProxyGroup {
  name: string
  type: GroupType
  members: Member[]
  url: string
  interval: number
  tolerance: number
}

export const RULE_TYPES = [
  'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'IP-CIDR', 'IP-CIDR6',
  'GEOSITE', 'GEOIP', 'PROCESS-NAME', 'RULE-SET', 'MATCH',
] as const

export type RuleType = (typeof RULE_TYPES)[number]

export interface Rule {
  type: RuleType
  value: string
  target: string
  no_resolve: boolean
}

export interface RuleProvider {
  name: string
  behavior: 'domain' | 'ipcidr' | 'classical'
  format: 'yaml' | 'text' | 'mrs'
  url: string
  interval: number
}

export interface Chain {
  node: { kind: 'node'; node_id: number }
  via: { kind: 'group'; name: string } | { kind: 'node'; node_id: number }
}

export interface Profile {
  name: string
  groups: ProxyGroup[]
  rules: Rule[]
  rule_providers: RuleProvider[]
  chains: Chain[]
}

export interface ProfileSummary {
  id: number
  name: string
  token: string
}

export interface ProfileDetail {
  id: number
  token: string
  last_good_at: string | null
  profile: Profile
}

export interface Preview {
  ok: boolean
  content: string | null
  errors: string[]
  warnings: string[]
}

export interface TemplateInfo {
  id: string
  name: string
  description: string
}
```

- [ ] **Step 6: 实现 `frontend/src/api/index.ts`**

```ts
import { request } from './client'
import type {
  FilterMember, ImportResult, NodeItem, Preview, Profile, ProfileDetail, ProfileSummary, RefreshResult,
  Source, SourceInput, SourcePatch, TemplateInfo,
} from './types'

export function buildQuery(params: Record<string, string | number | null | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return entries.length ? '?' + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString() : ''
}

export const api = {
  login: (password: string) => request<{ ok: boolean }>('POST', '/api/auth/login', { password }),
  logout: () => request<{ ok: boolean }>('POST', '/api/auth/logout'),
  me: () => request<{ admin: boolean }>('GET', '/api/auth/me'),

  listSources: () => request<Source[]>('GET', '/api/sources'),
  createSource: (body: SourceInput) => request<Source>('POST', '/api/sources', body),
  updateSource: (id: number, body: SourcePatch) => request<Source>('PATCH', `/api/sources/${id}`, body),
  deleteSource: (id: number) => request<void>('DELETE', `/api/sources/${id}`),
  refreshSource: (id: number) => request<RefreshResult>('POST', `/api/sources/${id}/refresh`),
  importNodes: (id: number, text: string) =>
    request<ImportResult>('POST', `/api/sources/${id}/nodes/import`, { text }),

  listNodes: (params: { source_id?: number | null; q?: string } = {}) =>
    request<NodeItem[]>('GET', '/api/nodes' + buildQuery(params)),
  updateNode: (id: number, body: { name?: string; enabled?: boolean }) =>
    request<NodeItem>('PATCH', `/api/nodes/${id}`, body),
  deleteNode: (id: number) => request<void>('DELETE', `/api/nodes/${id}`),
  bulkNodes: (ids: number[], enabled: boolean) =>
    request<{ updated: number }>('POST', '/api/nodes/bulk', { ids, enabled }),
  matchNodes: (filter: Omit<FilterMember, 'kind'>) => request<NodeItem[]>('POST', '/api/nodes/match', filter),

  listProfiles: () => request<ProfileSummary[]>('GET', '/api/profiles'),
  createProfile: (name: string) => request<ProfileDetail>('POST', '/api/profiles', { name }),
  getProfile: (id: number) => request<ProfileDetail>('GET', `/api/profiles/${id}`),
  saveProfile: (id: number, profile: Profile) => request<ProfileDetail>('PUT', `/api/profiles/${id}`, profile),
  deleteProfile: (id: number) => request<void>('DELETE', `/api/profiles/${id}`),
  applyTemplate: (id: number, templateId: string) =>
    request<{ profile: ProfileDetail; notes: string[] }>('POST', `/api/profiles/${id}/apply-template`,
      { template_id: templateId }),
  rotateToken: (id: number) => request<ProfileDetail>('POST', `/api/profiles/${id}/rotate-token`),
  preview: (id: number) => request<Preview>('GET', `/api/profiles/${id}/preview`),

  listTemplates: () => request<TemplateInfo[]>('GET', '/api/templates'),
}
```

- [ ] **Step 7: 实现 `frontend/src/lib/format.ts`**

```ts
const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return '—'
  let value = n
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit++
  }
  return `${unit === 0 ? value : value.toFixed(1)} ${UNITS[unit]}`
}

/** 后端时间为不带时区的 UTC 字符串，可能带 6 位微秒。 */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const trimmed = iso.replace(/(\.\d{3})\d+/, '$1')
  const hasZone = /([zZ]|[+-]\d{2}:\d{2})$/.test(trimmed)
  return new Date(hasZone ? trimmed : `${trimmed}Z`).toLocaleString('zh-CN', { hour12: false })
}

export function formatEpoch(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  return new Date(seconds * 1000).toLocaleDateString('zh-CN')
}
```

- [ ] **Step 8: 实现 `frontend/src/lib/profile.ts`**

```ts
import type { Member, NodeItem, Profile, ProxyGroup, Rule, Source } from '../api/types'

export const BUILTIN_TARGETS = ['DIRECT', 'REJECT'] as const
export const DEFAULT_TEST_URL = 'https://www.gstatic.com/generate_204'

export function newGroup(name: string): ProxyGroup {
  return { name, type: 'select', members: [], url: DEFAULT_TEST_URL, interval: 300, tolerance: 50 }
}

export function newRule(target: string): Rule {
  return { type: 'DOMAIN-SUFFIX', value: '', target, no_resolve: false }
}

export function moveItem<T>(list: T[], index: number, delta: number): T[] {
  const to = index + delta
  if (to < 0 || to >= list.length) return list
  const copy = [...list]
  ;[copy[index], copy[to]] = [copy[to], copy[index]]
  return copy
}

export function insertBeforeMatch(rules: Rule[], rule: Rule): Rule[] {
  const at = rules.findIndex((r) => r.type === 'MATCH')
  if (at === -1) return [...rules, rule]
  return [...rules.slice(0, at), rule, ...rules.slice(at)]
}

export function sameMember(a: Member, b: Member): boolean {
  switch (a.kind) {
    case 'node':
      return b.kind === 'node' && a.node_id === b.node_id
    case 'group':
      return b.kind === 'group' && a.name === b.name
    case 'builtin':
      return b.kind === 'builtin' && a.name === b.name
    case 'filter':
      return (
        b.kind === 'filter' &&
        a.source_id === b.source_id &&
        a.name_regex === b.name_regex &&
        (a.exclude_regex || null) === (b.exclude_regex || null)
      )
  }
}

export function memberLabel(m: Member, nodes: Map<number, NodeItem>, sources: Map<number, Source>): string {
  switch (m.kind) {
    case 'node':
      return nodes.get(m.node_id)?.name ?? `#${m.node_id}（已删除）`
    case 'group':
      return `分组：${m.name}`
    case 'builtin':
      return m.name
    case 'filter': {
      const src = m.source_id == null ? '全部节点源' : (sources.get(m.source_id)?.name ?? `#${m.source_id}`)
      const exclude = m.exclude_regex ? ` 排除 /${m.exclude_regex}/` : ''
      return `过滤：${src} /${m.name_regex || '(全部)'}/${exclude}`
    }
  }
}

export function renameGroup(profile: Profile, from: string, to: string): Profile {
  const rename = (m: Member): Member => (m.kind === 'group' && m.name === from ? { ...m, name: to } : m)
  return {
    ...profile,
    groups: profile.groups.map((g) => ({ ...g, name: g.name === from ? to : g.name, members: g.members.map(rename) })),
    rules: profile.rules.map((r) => (r.target === from ? { ...r, target: to } : r)),
    chains: profile.chains.map((c) =>
      c.via.kind === 'group' && c.via.name === from ? { ...c, via: { kind: 'group', name: to } } : c,
    ),
  }
}

export function targetOptions(profile: Profile): string[] {
  return [...profile.groups.map((g) => g.name), ...BUILTIN_TARGETS]
}

export function subscriptionUrl(origin: string, token: string): string {
  return `${origin}/sub/${token}`
}
```

- [ ] **Step 9: 运行确认通过**

Run: `npm test`
Expected: 3 个测试文件全部 passed

Run: `npx vue-tsc --noEmit`
Expected: 无错误（此时还没有 `src/main.ts`，`vite build` 留到 Task 3）

- [ ] **Step 10: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json frontend/index.html frontend/env.d.ts frontend/src
git commit -m "feat(web): scaffold frontend with api client and profile helpers"
```

### Task 3: 应用外壳、登录页与节点源页

**Files:**
- Create: `frontend/src/main.ts`、`frontend/src/App.vue`、`frontend/src/router.ts`
- Create: `frontend/src/views/LoginView.vue`、`frontend/src/views/SourcesView.vue`

**Interfaces:**
- Consumes: Task 2 `api`、`setUnauthorizedHandler`、`formatBytes`、`formatTime`、`formatEpoch`、类型
- Produces:
  - `router.ts`: `router`、`markLoggedIn()`、`markLoggedOut()`；`RouteMeta` 扩展字段 `title`（侧边栏菜单名）、`order`（菜单顺序）、`activeMenu`（子页面高亮哪个菜单）。**后续任务只需往 `routes` 数组添加带 `meta.title` 的路由，侧边栏菜单会自动出现。**
  - 路由：`/login`（name `login`）、`/` → `sources`、`/sources`（name `sources`）

- [ ] **Step 1: 实现 `frontend/src/router.ts`**

```ts
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { api } from './api'
import LoginView from './views/LoginView.vue'
import SourcesView from './views/SourcesView.vue'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    order?: number
    activeMenu?: string
  }
}

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView },
  { path: '/', redirect: { name: 'sources' } },
  { path: '/sources', name: 'sources', component: SourcesView, meta: { title: '节点源', order: 1 } },
]

export const router = createRouter({ history: createWebHistory(), routes })

let authenticated = false

export function markLoggedIn(): void {
  authenticated = true
}

export function markLoggedOut(): void {
  authenticated = false
}

router.beforeEach(async (to) => {
  if (to.name === 'login' || authenticated) return true
  try {
    await api.me()
    authenticated = true
    return true
  } catch {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})
```

- [ ] **Step 2: 实现 `frontend/src/main.ts`**

```ts
import { createApp } from 'vue'
import App from './App.vue'
import { setUnauthorizedHandler } from './api/client'
import { markLoggedOut, router } from './router'

setUnauthorizedHandler(() => {
  markLoggedOut()
  const current = router.currentRoute.value
  if (current.name !== 'login') {
    router.push({ name: 'login', query: { redirect: current.fullPath } })
  }
})

createApp(App).use(router).mount('#app')
```

- [ ] **Step 3: 实现 `frontend/src/App.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import {
  NButton, NConfigProvider, NDialogProvider, NLayout, NLayoutContent, NLayoutSider, NMenu, NMessageProvider,
  dateZhCN, zhCN, type MenuOption,
} from 'naive-ui'
import { api } from './api'
import { markLoggedOut } from './router'

const route = useRoute()
const router = useRouter()

const menuOptions = computed<MenuOption[]>(() =>
  router
    .getRoutes()
    .filter((r) => r.meta.title)
    .sort((a, b) => (a.meta.order ?? 0) - (b.meta.order ?? 0))
    .map((r) => ({ label: r.meta.title, key: String(r.name) })),
)
const activeKey = computed(() => route.meta.activeMenu ?? String(route.name ?? ''))
const showShell = computed(() => route.name !== 'login')

function navigate(key: string) {
  router.push({ name: key })
}

async function logout() {
  await api.logout()
  markLoggedOut()
  router.push({ name: 'login' })
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <NLayout v-if="showShell" has-sider class="shell">
          <NLayoutSider bordered :width="180">
            <div class="brand">RouteForge</div>
            <NMenu :options="menuOptions" :value="activeKey" @update:value="navigate" />
            <div class="logout"><NButton text @click="logout">退出登录</NButton></div>
          </NLayoutSider>
          <NLayoutContent content-style="padding: 24px;">
            <RouterView />
          </NLayoutContent>
        </NLayout>
        <RouterView v-else />
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style>
body {
  margin: 0;
}
.shell {
  height: 100vh;
}
.brand {
  font-size: 18px;
  font-weight: 600;
  padding: 16px;
}
.logout {
  padding: 16px;
}
</style>
```

- [ ] **Step 4: 实现 `frontend/src/views/LoginView.vue`**

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NForm, NFormItem, NInput } from 'naive-ui'
import { api } from '../api'
import { markLoggedIn } from '../router'

const route = useRoute()
const router = useRouter()
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.login(password.value)
    markLoggedIn()
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <NCard title="RouteForge 登录" style="width: 360px">
      <NForm @submit.prevent="submit">
        <NFormItem label="管理员密码">
          <NInput v-model:value="password" type="password" show-password-on="click" autofocus />
        </NFormItem>
        <NAlert v-if="error" type="error" style="margin-bottom: 12px">{{ error }}</NAlert>
        <NButton type="primary" attr-type="submit" block :loading="loading">登录</NButton>
      </NForm>
    </NCard>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}
</style>
```

- [ ] **Step 5: 实现 `frontend/src/views/SourcesView.vue`**

```vue
<script setup lang="ts">
import { h, onMounted, reactive, ref } from 'vue'
import {
  NAlert, NButton, NDataTable, NForm, NFormItem, NInput, NInputNumber, NModal, NRadioButton, NRadioGroup, NSpace,
  NTag, NText, useDialog, useMessage, type DataTableColumns,
} from 'naive-ui'
import { api } from '../api'
import type { LineError, Source, SourceKind } from '../api/types'
import { formatBytes, formatEpoch, formatTime } from '../lib/format'

const message = useMessage()
const dialog = useDialog()

const sources = ref<Source[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    sources.value = await api.listSources()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// —— 新建 / 编辑 ——
const showForm = ref(false)
const editing = ref<Source | null>(null)
const saving = ref(false)
const form = reactive({ kind: 'manual' as SourceKind, name: '', url: '', refresh_interval: 360, user_agent: 'clash.meta' })

function openCreate() {
  editing.value = null
  Object.assign(form, { kind: 'manual', name: '', url: '', refresh_interval: 360, user_agent: 'clash.meta' })
  showForm.value = true
}

function openEdit(s: Source) {
  editing.value = s
  Object.assign(form, {
    kind: s.kind, name: s.name, url: s.url ?? '', refresh_interval: s.refresh_interval, user_agent: s.user_agent,
  })
  showForm.value = true
}

async function save() {
  saving.value = true
  const subFields =
    form.kind === 'subscription'
      ? { url: form.url, refresh_interval: form.refresh_interval, user_agent: form.user_agent }
      : {}
  try {
    if (editing.value) {
      await api.updateSource(editing.value.id, { name: form.name, ...subFields })
    } else {
      const created = await api.createSource({ kind: form.kind, name: form.name, ...subFields })
      if (created.last_error) message.warning(`已创建，但首次拉取失败：${created.last_error}`)
    }
    showForm.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

// —— 刷新 ——
async function refresh(s: Source) {
  try {
    const r = await api.refreshSource(s.id)
    if (r.ok) message.success(`刷新完成：新增 ${r.added}，更新 ${r.updated}，移除 ${r.removed}`)
    else message.error(r.error ?? '刷新失败')
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

// —— 导入分享链接 ——
const importTarget = ref<Source | null>(null)
const importText = ref('')
const importErrors = ref<LineError[]>([])

function openImport(s: Source) {
  importTarget.value = s
  importText.value = ''
  importErrors.value = []
}

async function doImport() {
  if (!importTarget.value) return
  try {
    const r = await api.importNodes(importTarget.value.id, importText.value)
    importErrors.value = r.errors
    message.success(`已导入 ${r.added} 个节点`)
    if (r.errors.length === 0) importTarget.value = null
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

// —— 删除 ——
function remove(s: Source) {
  dialog.warning({
    title: '删除节点源',
    content: `确定删除「${s.name}」及其 ${s.node_count} 个节点？引用这些节点的方案会在预览中出现警告。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteSource(s.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

function trafficText(s: Source): string {
  const u = s.userinfo
  if (!u) return '—'
  const used = formatBytes((u.upload ?? 0) + (u.download ?? 0))
  const expire = u.expire ? `，${formatEpoch(u.expire)} 到期` : ''
  return `${used} / ${formatBytes(u.total)}${expire}`
}

const columns: DataTableColumns<Source> = [
  { title: '名称', key: 'name' },
  {
    title: '类型',
    key: 'kind',
    render: (s) =>
      h(NTag, { size: 'small', type: s.kind === 'subscription' ? 'info' : 'default' }, () =>
        s.kind === 'subscription' ? '机场订阅' : '手动'),
  },
  { title: '节点数', key: 'node_count' },
  { title: '上次拉取', key: 'last_fetched_at', render: (s) => (s.kind === 'subscription' ? formatTime(s.last_fetched_at) : '—') },
  {
    title: '状态',
    key: 'last_error',
    render: (s) =>
      s.last_error ? h(NText, { type: 'error' }, () => s.last_error) : h(NText, { type: 'success' }, () => '正常'),
  },
  { title: '流量', key: 'userinfo', render: trafficText },
  {
    title: '操作',
    key: 'actions',
    render: (s) =>
      h(NSpace, { size: 'small' }, () => [
        s.kind === 'subscription'
          ? h(NButton, { size: 'small', onClick: () => refresh(s) }, () => '立即刷新')
          : h(NButton, { size: 'small', onClick: () => openImport(s) }, () => '导入链接'),
        h(NButton, { size: 'small', onClick: () => openEdit(s) }, () => '编辑'),
        h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => remove(s) }, () => '删除'),
      ]),
  },
]
</script>

<template>
  <NSpace vertical size="large">
    <NSpace justify="space-between" align="center">
      <h2 style="margin: 0">节点源</h2>
      <NButton type="primary" @click="openCreate">新建节点源</NButton>
    </NSpace>
    <NDataTable :columns="columns" :data="sources" :loading="loading" :row-key="(s: Source) => s.id" />
  </NSpace>

  <NModal v-model:show="showForm" preset="card" :title="editing ? '编辑节点源' : '新建节点源'" style="width: 520px">
    <NForm label-placement="left" label-width="96">
      <NFormItem v-if="!editing" label="类型">
        <NRadioGroup :value="form.kind" @update:value="(v: unknown) => (form.kind = v as SourceKind)">
          <NRadioButton value="manual">手动</NRadioButton>
          <NRadioButton value="subscription">机场订阅</NRadioButton>
        </NRadioGroup>
      </NFormItem>
      <NFormItem label="名称"><NInput v-model:value="form.name" /></NFormItem>
      <template v-if="form.kind === 'subscription'">
        <NFormItem label="订阅链接"><NInput v-model:value="form.url" placeholder="https://..." /></NFormItem>
        <NFormItem label="刷新间隔">
          <NInputNumber
            :value="form.refresh_interval"
            :min="10"
            :max="10080"
            @update:value="(v: number | null) => (form.refresh_interval = v ?? 360)"
          >
            <template #suffix>分钟</template>
          </NInputNumber>
        </NFormItem>
        <NFormItem label="User-Agent"><NInput v-model:value="form.user_agent" /></NFormItem>
      </template>
    </NForm>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="showForm = false">取消</NButton>
        <NButton type="primary" :loading="saving" @click="save">保存</NButton>
      </NSpace>
    </template>
  </NModal>

  <NModal
    :show="importTarget !== null"
    preset="card"
    title="导入分享链接"
    style="width: 640px"
    @update:show="(v: boolean) => { if (!v) importTarget = null }"
  >
    <NInput
      v-model:value="importText"
      type="textarea"
      :rows="10"
      placeholder="每行一个 ss:// vmess:// vless:// trojan:// hysteria2:// tuic:// 链接"
    />
    <NAlert v-if="importErrors.length" type="warning" title="以下行未能导入" style="margin-top: 12px">
      <div v-for="(e, i) in importErrors" :key="i"><code>{{ e.line }}</code>：{{ e.message }}</div>
    </NAlert>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="importTarget = null">关闭</NButton>
        <NButton type="primary" @click="doImport">导入</NButton>
      </NSpace>
    </template>
  </NModal>
</template>
```

- [ ] **Step 6: 构建与类型检查**

Run: `npm run build && npm test`
Expected: 构建成功（生成 `dist/`），测试全部 passed

- [ ] **Step 7: 浏览器手动检查**

终端 A（`backend/`）：`ROUTEFORGE_ADMIN_PASSWORD=pw ROUTEFORGE_COOKIE_SECURE=false ROUTEFORGE_DATA_DIR=./data uv run routeforge`
终端 B（`frontend/`）：`npm run dev`

打开 `http://localhost:5173`，逐项确认：
1. 自动跳转到 `/login?redirect=/sources`；输错密码显示「密码错误」；输入 `pw` 后进入「节点源」页
2. 新建手动节点源「手动」→ 点「导入链接」，粘贴 `ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#HK` 和一行 `abc` → 提示导入 1 个，弹窗中列出 `abc：不是分享链接`；表格节点数为 1
3. 新建机场订阅，链接填 `https://example.invalid/sub` → 出现「首次拉取失败」警告，状态列红色显示错误
4. 订阅链接填 `ftp://x` 保存 → 显示中文校验错误（不是 `[object Object]`）
5. 编辑名称后表格更新；删除时出现确认框
6. 刷新浏览器仍停留在「节点源」页；点「退出登录」回到登录页；再访问 `/sources` 被重定向到登录页

完成后停止两个进程，删除 `backend/data/`。

- [ ] **Step 8: 提交**

```bash
git add frontend/src
git commit -m "feat(web): add app shell, login and sources pages"
```

### Task 4: 节点页

**Files:**
- Create: `frontend/src/views/NodesView.vue`
- Modify: `frontend/src/router.ts`（添加路由）

**Interfaces:**
- Consumes: `api.listSources`、`api.listNodes`、`api.updateNode`、`api.deleteNode`、`api.bulkNodes`；`NodeItem`、`Source`
- Produces: 路由 `/nodes`（name `nodes`，菜单「节点」，order 2）

- [ ] **Step 1: 实现 `frontend/src/views/NodesView.vue`**

```vue
<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NButton, NDataTable, NInput, NModal, NSelect, NSpace, NSwitch, NTag, useDialog, useMessage,
  type DataTableColumns, type DataTableRowKey,
} from 'naive-ui'
import { api } from '../api'
import type { NodeItem, Source } from '../api/types'

const message = useMessage()
const dialog = useDialog()

const nodes = ref<NodeItem[]>([])
const sources = ref<Source[]>([])
const sourceFilter = ref<number | null>(null)
const keyword = ref('')
const checked = ref<DataTableRowKey[]>([])
const loading = ref(false)

const sourceMap = computed(() => new Map(sources.value.map((s) => [s.id, s])))
const sourceOptions = computed(() => sources.value.map((s) => ({ label: s.name, value: s.id })))
const isManual = (n: NodeItem) => sourceMap.value.get(n.source_id)?.kind === 'manual'

async function load() {
  loading.value = true
  try {
    const [srcs, list] = await Promise.all([
      api.listSources(),
      api.listNodes({ source_id: sourceFilter.value, q: keyword.value.trim() || undefined }),
    ])
    sources.value = srcs
    nodes.value = list
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(sourceFilter, load)

async function toggle(n: NodeItem, enabled: boolean) {
  try {
    const updated = await api.updateNode(n.id, { enabled })
    n.enabled = updated.enabled
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function bulk(enabled: boolean) {
  try {
    const r = await api.bulkNodes(checked.value.map(Number), enabled)
    message.success(`已${enabled ? '启用' : '禁用'} ${r.updated} 个节点`)
    checked.value = []
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

const renaming = ref<NodeItem | null>(null)
const newName = ref('')

function openRename(n: NodeItem) {
  renaming.value = n
  newName.value = n.name
}

async function doRename() {
  if (!renaming.value) return
  try {
    await api.updateNode(renaming.value.id, { name: newName.value.trim() })
    renaming.value = null
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

function remove(n: NodeItem) {
  dialog.warning({
    title: '删除节点',
    content: `确定删除「${n.name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteNode(n.id)
        await load()
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

const columns: DataTableColumns<NodeItem> = [
  { type: 'selection' },
  { title: '名称', key: 'name' },
  { title: '协议', key: 'type', render: (n) => h(NTag, { size: 'small' }, () => n.type) },
  { title: '地址', key: 'server', render: (n) => `${n.server}:${n.port}` },
  { title: '节点源', key: 'source_id', render: (n) => sourceMap.value.get(n.source_id)?.name ?? '—' },
  {
    title: '启用',
    key: 'enabled',
    render: (n) => h(NSwitch, { value: n.enabled, onUpdateValue: (v: boolean) => toggle(n, v) }),
  },
  {
    title: '操作',
    key: 'actions',
    render: (n) =>
      isManual(n)
        ? h(NSpace, { size: 'small' }, () => [
            h(NButton, { size: 'small', onClick: () => openRename(n) }, () => '改名'),
            h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => remove(n) }, () => '删除'),
          ])
        : '订阅节点（随订阅更新）',
  },
]
</script>

<template>
  <NSpace vertical size="large">
    <h2 style="margin: 0">节点</h2>
    <NSpace>
      <NSelect
        :value="sourceFilter"
        :options="sourceOptions"
        @update:value="(v: unknown) => (sourceFilter = (v as number | null) ?? null)"
        clearable
        placeholder="全部节点源"
        style="width: 200px"
      />
      <NInput v-model:value="keyword" placeholder="按名称搜索" clearable style="width: 220px" @keyup.enter="load" />
      <NButton @click="load">搜索</NButton>
      <NButton :disabled="!checked.length" @click="bulk(true)">启用所选</NButton>
      <NButton :disabled="!checked.length" @click="bulk(false)">禁用所选</NButton>
    </NSpace>
    <NDataTable
      v-model:checked-row-keys="checked"
      :columns="columns"
      :data="nodes"
      :loading="loading"
      :row-key="(n: NodeItem) => n.id"
      :pagination="{ pageSize: 50 }"
    />
  </NSpace>

  <NModal
    :show="renaming !== null"
    preset="card"
    title="节点改名"
    style="width: 420px"
    @update:show="(v: boolean) => { if (!v) renaming = null }"
  >
    <NInput v-model:value="newName" @keyup.enter="doRename" />
    <template #footer>
      <NSpace justify="end">
        <NButton @click="renaming = null">取消</NButton>
        <NButton type="primary" :disabled="!newName.trim()" @click="doRename">保存</NButton>
      </NSpace>
    </template>
  </NModal>
</template>
```

- [ ] **Step 2: 在 `router.ts` 注册路由**

顶部导入追加 `import NodesView from './views/NodesView.vue'`，在 `routes` 数组 `sources` 之后追加：

```ts
  { path: '/nodes', name: 'nodes', component: NodesView, meta: { title: '节点', order: 2 } },
```

- [ ] **Step 3: 构建**

Run: `npm run build`
Expected: 成功

- [ ] **Step 4: 浏览器手动检查**（按 Task 3 Step 7 方式启动前后端）

1. 侧边栏出现「节点」菜单
2. 在「节点源」新建手动源并导入 2 个链接；进入「节点」页可见 2 行，协议、地址、节点源列正确
3. 切换「启用」开关后刷新页面，状态保留
4. 勾选 2 行 → 「禁用所选」→ 提示「已禁用 2 个节点」
5. 「改名」后名称更新；「删除」需确认
6. 按节点源筛选、按名称搜索（回车或点「搜索」）结果正确
7. 若有机场订阅节点（可选），其操作列显示「订阅节点（随订阅更新）」

- [ ] **Step 5: 提交**

```bash
git add frontend/src
git commit -m "feat(web): add nodes page"
```

### Task 5: 方案列表、方案编辑页外壳与预览面板

**Files:**
- Create: `frontend/src/lib/clipboard.ts`
- Create: `frontend/src/views/ProfilesView.vue`
- Create: `frontend/src/views/ProfileEditView.vue`
- Create: `frontend/src/components/PreviewPanel.vue`
- Modify: `frontend/src/router.ts`（添加路由）

**Interfaces:**
- Consumes: `api.listProfiles/createProfile/deleteProfile/getProfile/saveProfile/applyTemplate/rotateToken/preview/listTemplates`；`subscriptionUrl`；类型
- Produces:
  - `copyText(text: string): Promise<boolean>`
  - 路由：`/profiles`（name `profiles`，菜单「配置方案」，order 3）、`/profiles/:id`（name `profile-edit`，props `{ id: number }`，`meta.activeMenu = 'profiles'`）
  - `ProfileEditView` 状态：`profile: Ref<Profile | null>`（可编辑副本）、`detail: Ref<ProfileDetail | null>`、`dirty`（与已保存版本 JSON 比较）、`version`（每次加载 / 保存后 +1，用于通知预览刷新）、`setDetail(d)`；页面使用 `NTabs`，**后续任务在 `<NTabs>` 中插入新的 `NTabPane`**
  - `PreviewPanel` props：`profileId: number`、`token: string`、`dirty: boolean`、`version: number`；emit `rotated(detail: ProfileDetail)`

- [ ] **Step 1: 实现 `frontend/src/lib/clipboard.ts`**

```ts
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false // 非 HTTPS 页面或浏览器拒绝访问剪贴板
  }
}
```

- [ ] **Step 2: 实现 `frontend/src/views/ProfilesView.vue`**

```vue
<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NDataTable, NInput, NInputGroup, NModal, NSpace, useDialog, useMessage, type DataTableColumns,
} from 'naive-ui'
import { api } from '../api'
import type { ProfileSummary } from '../api/types'
import { copyText } from '../lib/clipboard'
import { subscriptionUrl } from '../lib/profile'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const profiles = ref<ProfileSummary[]>([])
const loading = ref(false)
const showCreate = ref(false)
const newName = ref('')

async function load() {
  loading.value = true
  try {
    profiles.value = await api.listProfiles()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function create() {
  try {
    const p = await api.createProfile(newName.value.trim())
    showCreate.value = false
    newName.value = ''
    router.push({ name: 'profile-edit', params: { id: p.id } })
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function copy(url: string) {
  if (await copyText(url)) message.success('已复制订阅链接')
  else message.warning('无法访问剪贴板，请手动复制')
}

function remove(p: ProfileSummary) {
  dialog.warning({
    title: '删除方案',
    content: `确定删除「${p.name}」？使用该订阅链接的客户端将无法再更新。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteProfile(p.id)
        await load()
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

const columns: DataTableColumns<ProfileSummary> = [
  { title: '名称', key: 'name' },
  {
    title: '订阅链接',
    key: 'token',
    render: (p) => {
      const url = subscriptionUrl(window.location.origin, p.token)
      return h(NInputGroup, null, () => [
        h(NInput, { value: url, readonly: true, size: 'small' }),
        h(NButton, { size: 'small', onClick: () => copy(url) }, () => '复制'),
      ])
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (p) =>
      h(NSpace, { size: 'small' }, () => [
        h(NButton, { size: 'small', type: 'primary', onClick: () => router.push({ name: 'profile-edit', params: { id: p.id } }) },
          () => '编辑'),
        h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => remove(p) }, () => '删除'),
      ]),
  },
]
</script>

<template>
  <NSpace vertical size="large">
    <NSpace justify="space-between" align="center">
      <h2 style="margin: 0">配置方案</h2>
      <NButton type="primary" @click="showCreate = true">新建方案</NButton>
    </NSpace>
    <NDataTable :columns="columns" :data="profiles" :loading="loading" :row-key="(p: ProfileSummary) => p.id" />
  </NSpace>

  <NModal v-model:show="showCreate" preset="card" title="新建方案" style="width: 420px">
    <NInput v-model:value="newName" placeholder="方案名称，例如 家里电脑" @keyup.enter="create" />
    <template #footer>
      <NSpace justify="end">
        <NButton @click="showCreate = false">取消</NButton>
        <NButton type="primary" :disabled="!newName.trim()" @click="create">创建</NButton>
      </NSpace>
    </template>
  </NModal>
</template>
```

- [ ] **Step 3: 实现 `frontend/src/components/PreviewPanel.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NInput, NInputGroup, NSpace, NText, useDialog, useMessage } from 'naive-ui'
import { api } from '../api'
import type { Preview, ProfileDetail } from '../api/types'
import { copyText } from '../lib/clipboard'
import { subscriptionUrl } from '../lib/profile'

const props = defineProps<{ profileId: number; token: string; dirty: boolean; version: number }>()
const emit = defineEmits<{ rotated: [detail: ProfileDetail] }>()
const message = useMessage()
const dialog = useDialog()

const preview = ref<Preview | null>(null)
const loading = ref(false)
const url = computed(() => subscriptionUrl(window.location.origin, props.token))

async function load() {
  loading.value = true
  try {
    preview.value = await api.preview(props.profileId)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(() => props.version, load)

async function copy() {
  if (await copyText(url.value)) message.success('已复制订阅链接')
  else message.warning('无法访问剪贴板，请手动复制')
}

function rotate() {
  dialog.warning({
    title: '重置订阅链接',
    content: '旧链接会立即失效，所有客户端都需要改用新链接。确定继续？',
    positiveText: '重置',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        emit('rotated', await api.rotateToken(props.profileId))
        message.success('订阅链接已重置')
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}
</script>

<template>
  <NSpace vertical size="large">
    <NCard title="订阅链接" size="small">
      <NSpace vertical>
        <NInputGroup>
          <NInput :value="url" readonly />
          <NButton @click="copy">复制</NButton>
          <NButton type="warning" ghost @click="rotate">重置</NButton>
        </NInputGroup>
        <NText depth="3">在 Clash Verge Rev 等使用 Mihomo 内核的客户端中添加此订阅链接。</NText>
      </NSpace>
    </NCard>

    <NAlert v-if="dirty" type="warning">有未保存的修改：预览和订阅链接使用的是已保存的版本。</NAlert>
    <NButton :loading="loading" @click="load">重新生成预览</NButton>

    <template v-if="preview">
      <NAlert v-if="preview.errors.length" type="error" title="方案有错误，无法生成配置（订阅链接会继续返回上次成功的版本）">
        <ul class="list"><li v-for="(e, i) in preview.errors" :key="i">{{ e }}</li></ul>
      </NAlert>
      <NAlert v-if="preview.warnings.length" type="warning" title="警告">
        <ul class="list"><li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li></ul>
      </NAlert>
      <pre v-if="preview.content" class="yaml">{{ preview.content }}</pre>
    </template>
  </NSpace>
</template>

<style scoped>
.list {
  margin: 0;
  padding-left: 20px;
}
.yaml {
  background: #f6f8fa;
  border-radius: 6px;
  font-size: 12px;
  max-height: 600px;
  overflow: auto;
  padding: 12px;
}
</style>
```

- [ ] **Step 4: 实现 `frontend/src/views/ProfileEditView.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { NButton, NDropdown, NInput, NSpace, NSpin, NTabPane, NTabs, useMessage } from 'naive-ui'
import { api } from '../api'
import type { Profile, ProfileDetail, TemplateInfo } from '../api/types'
import PreviewPanel from '../components/PreviewPanel.vue'

const props = defineProps<{ id: number }>()
const router = useRouter()
const message = useMessage()

const detail = ref<ProfileDetail | null>(null)
const profile = ref<Profile | null>(null)
const savedJson = ref('')
const version = ref(0)
const templates = ref<TemplateInfo[]>([])
const saving = ref(false)

const dirty = computed(() => profile.value !== null && JSON.stringify(profile.value) !== savedJson.value)
const templateOptions = computed(() =>
  templates.value.map((t) => ({ label: t.name, key: t.id, props: { title: t.description } })),
)

function setDetail(d: ProfileDetail) {
  detail.value = d
  profile.value = structuredClone(d.profile)
  savedJson.value = JSON.stringify(d.profile)
  version.value++
}

async function load() {
  try {
    const [d, t] = await Promise.all([api.getProfile(props.id), api.listTemplates()])
    templates.value = t
    setDetail(d)
  } catch (e) {
    message.error((e as Error).message)
  }
}
onMounted(load)

async function save(): Promise<boolean> {
  if (!profile.value) return false
  saving.value = true
  try {
    setDetail(await api.saveProfile(props.id, profile.value))
    message.success('已保存')
    return true
  } catch (e) {
    message.error((e as Error).message)
    return false
  } finally {
    saving.value = false
  }
}

async function applyTemplate(key: string | number) {
  if (dirty.value && !(await save())) return
  try {
    const r = await api.applyTemplate(props.id, String(key))
    setDetail(r.profile)
    r.notes.forEach((n) => message.info(n))
    message.success('模板已套用')
  } catch (e) {
    message.error((e as Error).message)
  }
}

function onRotated(d: ProfileDetail) {
  if (detail.value) detail.value = { ...detail.value, token: d.token }
}

onBeforeRouteLeave(() => !dirty.value || window.confirm('有未保存的修改，确定离开？'))

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) e.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onUnmounted(() => window.removeEventListener('beforeunload', onBeforeUnload))
</script>

<template>
  <NSpin :show="!profile">
    <NSpace v-if="profile && detail" vertical size="large">
      <NSpace align="center" justify="space-between">
        <NSpace align="center">
          <NButton text @click="router.push({ name: 'profiles' })">← 返回</NButton>
          <NInput v-model:value="profile.name" placeholder="方案名称" style="width: 240px" />
        </NSpace>
        <NSpace>
          <NDropdown :options="templateOptions" trigger="click" @select="applyTemplate">
            <NButton>套用模板</NButton>
          </NDropdown>
          <NButton type="primary" :disabled="!dirty || !profile.name.trim()" :loading="saving" @click="save">
            保存
          </NButton>
        </NSpace>
      </NSpace>

      <NTabs type="line" default-value="preview" animated>
        <NTabPane name="preview" tab="预览与订阅">
          <PreviewPanel
            :profile-id="detail.id"
            :token="detail.token"
            :dirty="dirty"
            :version="version"
            @rotated="onRotated"
          />
        </NTabPane>
      </NTabs>
    </NSpace>
  </NSpin>
</template>
```

- [ ] **Step 5: 在 `router.ts` 注册路由**

顶部导入追加：

```ts
import ProfileEditView from './views/ProfileEditView.vue'
import ProfilesView from './views/ProfilesView.vue'
```

`routes` 数组 `nodes` 之后追加：

```ts
  { path: '/profiles', name: 'profiles', component: ProfilesView, meta: { title: '配置方案', order: 3 } },
  {
    path: '/profiles/:id',
    name: 'profile-edit',
    component: ProfileEditView,
    props: (route) => ({ id: Number(route.params.id) }),
    meta: { activeMenu: 'profiles' },
  },
```

- [ ] **Step 6: 构建**

Run: `npm run build`
Expected: 成功

- [ ] **Step 7: 浏览器手动检查**（先在「节点源」中准备一个手动源和 1 个节点）

1. 「配置方案」→「新建方案」，输入名称后跳转到编辑页，侧边栏仍高亮「配置方案」
2. 预览显示错误「规则必须以且仅以一条 MATCH 规则结尾」
3. 「套用模板」→「AI 服务」：弹出「已创建分组『节点选择』…」等提示；再套用「漏网之鱼」→ 预览无错误，警告中有「节点选择」为空已补 DIRECT，下方出现 YAML
4. 「复制」订阅链接（localhost 下可用），在新标签页打开 → 下载 / 显示 YAML
5. 「重置」→ 链接变化；旧链接返回 404
6. 修改方案名 → 「保存」可点、预览上方出现未保存提示；不保存直接点「← 返回」→ 弹出确认框
7. 保存后返回列表，名称已更新；删除方案需确认

- [ ] **Step 8: 提交**

```bash
git add frontend/src
git commit -m "feat(web): add profile list, editor shell and preview panel"
```

### Task 6: 分组编辑器（含过滤器）

**Files:**
- Create: `frontend/src/components/FilterForm.vue`
- Create: `frontend/src/components/GroupEditor.vue`
- Modify: `frontend/src/views/ProfileEditView.vue`（加载节点 / 节点源，加入「分组」标签页）

**Interfaces:**
- Consumes: `api.matchNodes`；`memberLabel`、`moveItem`、`newGroup`、`renameGroup`、`sameMember`、`BUILTIN_TARGETS`；类型
- Produces:
  - `FilterForm` props `{ sources: Source[] }`，emit `submit(filter: FilterMember)`
  - `GroupEditor`：`v-model`（`Profile`，组件内原地修改分组；改名时整体替换为 `renameGroup` 的结果），props `{ nodes: NodeItem[]; sources: Source[] }`
  - `ProfileEditView` 新增 `nodes: Ref<NodeItem[]>`、`sources: Ref<Source[]>`（Task 7 的链式代理编辑器也使用）

- [ ] **Step 1: 实现 `frontend/src/components/FilterForm.vue`**

```vue
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NSelect, NSpace, NTag } from 'naive-ui'
import { api } from '../api'
import type { FilterMember, NodeItem, Source } from '../api/types'

const props = defineProps<{ sources: Source[] }>()
const emit = defineEmits<{ submit: [filter: FilterMember] }>()

const form = reactive({ source_id: null as number | null, name_regex: '', exclude_regex: '' })
const matched = ref<NodeItem[] | null>(null)
const error = ref('')
const sourceOptions = computed(() => props.sources.map((s) => ({ label: s.name, value: s.id })))

function toFilter(): FilterMember {
  return { kind: 'filter', source_id: form.source_id, name_regex: form.name_regex, exclude_regex: form.exclude_regex || null }
}

async function test() {
  error.value = ''
  try {
    matched.value = await api.matchNodes({
      source_id: form.source_id, name_regex: form.name_regex, exclude_regex: form.exclude_regex || null,
    })
  } catch (e) {
    matched.value = null
    error.value = (e as Error).message
  }
}
</script>

<template>
  <NForm label-placement="left" label-width="96">
    <NFormItem label="节点源">
      <NSelect
        :value="form.source_id"
        :options="sourceOptions"
        clearable
        placeholder="全部节点源"
        @update:value="(v: unknown) => (form.source_id = (v as number | null) ?? null)"
      />
    </NFormItem>
    <NFormItem label="名称匹配">
      <NInput v-model:value="form.name_regex" placeholder="正则，例如 香港|HK；留空匹配全部" />
    </NFormItem>
    <NFormItem label="排除">
      <NInput v-model:value="form.exclude_regex" placeholder="正则，可选，例如 过期|剩余" />
    </NFormItem>
  </NForm>
  <NAlert v-if="error" type="error">{{ error }}</NAlert>
  <div v-if="matched">
    匹配到 {{ matched.length }} 个节点：
    <NTag v-for="n in matched.slice(0, 30)" :key="n.id" size="small" style="margin: 2px">{{ n.name }}</NTag>
    <span v-if="matched.length > 30">…</span>
  </div>
  <NSpace justify="end" style="margin-top: 12px">
    <NButton @click="test">预览匹配</NButton>
    <NButton type="primary" @click="emit('submit', toFilter())">添加</NButton>
  </NSpace>
</template>
```

- [ ] **Step 2: 实现 `frontend/src/components/GroupEditor.vue`**

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  NButton, NCard, NEmpty, NInput, NInputNumber, NModal, NSelect, NSpace, NTag, NText, useDialog, useMessage,
} from 'naive-ui'
import type { FilterMember, GroupType, Member, NodeItem, Profile, Source } from '../api/types'
import { BUILTIN_TARGETS, memberLabel, moveItem, newGroup, renameGroup, sameMember } from '../lib/profile'
import FilterForm from './FilterForm.vue'

const profile = defineModel<Profile>({ required: true })
const props = defineProps<{ nodes: NodeItem[]; sources: Source[] }>()
const message = useMessage()
const dialog = useDialog()

const GROUP_TYPES = [
  { label: '手动选择', value: 'select' },
  { label: '自动测速', value: 'url-test' },
  { label: '故障转移', value: 'fallback' },
  { label: '负载均衡', value: 'load-balance' },
]

const nodeMap = computed(() => new Map(props.nodes.map((n) => [n.id, n])))
const sourceMap = computed(() => new Map(props.sources.map((s) => [s.id, s])))
const nodeOptions = computed(() =>
  props.nodes.map((n) => ({ label: `${n.name}（${sourceMap.value.get(n.source_id)?.name ?? '?'}）`, value: n.id })),
)

const drafts = ref<Record<number, string>>({})
const filterFor = ref<number | null>(null)

function groupOptions(self: string) {
  return profile.value.groups.filter((g) => g.name !== self).map((g) => ({ label: g.name, value: g.name }))
}

function tagType(m: Member) {
  return ({ node: 'default', group: 'info', builtin: 'warning', filter: 'success' } as const)[m.kind]
}

function commitRename(index: number) {
  const draft = drafts.value[index]
  delete drafts.value[index]
  if (draft === undefined) return
  const old = profile.value.groups[index].name
  const name = draft.trim()
  if (name === old) return
  if (!name) {
    message.error('分组名不能为空')
    return
  }
  if ((BUILTIN_TARGETS as readonly string[]).includes(name) || profile.value.groups.some((g) => g.name === name)) {
    message.error(`分组名「${name}」已存在或是保留名`)
    return
  }
  profile.value = renameGroup(profile.value, old, name)
}

function addGroup() {
  let i = profile.value.groups.length + 1
  while (profile.value.groups.some((g) => g.name === `分组 ${i}`)) i++
  profile.value.groups.push(newGroup(`分组 ${i}`))
}

function moveGroup(index: number, delta: number) {
  profile.value.groups = moveItem(profile.value.groups, index, delta)
}

function removeGroup(index: number) {
  const name = profile.value.groups[index].name
  const p = profile.value
  const refs =
    p.groups.filter((g) => g.members.some((m) => m.kind === 'group' && m.name === name)).length +
    p.rules.filter((r) => r.target === name).length +
    p.chains.filter((c) => c.via.kind === 'group' && c.via.name === name).length
  dialog.warning({
    title: '删除分组',
    content: refs
      ? `「${name}」仍被 ${refs} 处引用（分组成员 / 规则 / 链式代理），删除后需要修改这些引用，否则预览会报错。确定删除？`
      : `确定删除分组「${name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => {
      profile.value.groups.splice(index, 1)
    },
  })
}

function addMember(index: number, m: Member) {
  const g = profile.value.groups[index]
  if (g.members.some((x) => sameMember(x, m))) {
    message.warning('该成员已在分组中')
    return
  }
  g.members.push(m)
}

function moveMember(index: number, mi: number, delta: number) {
  const g = profile.value.groups[index]
  g.members = moveItem(g.members, mi, delta)
}

function removeMember(index: number, mi: number) {
  profile.value.groups[index].members.splice(mi, 1)
}

function submitFilter(f: FilterMember) {
  if (filterFor.value !== null) addMember(filterFor.value, f)
  filterFor.value = null
}
</script>

<template>
  <NSpace vertical>
    <NEmpty v-if="!profile.groups.length" description="还没有分组：可以「套用模板」，或在下方新建" />
    <NCard v-for="(g, i) in profile.groups" :key="i" size="small">
      <template #header>
        <NSpace align="center">
          <NInput
            :value="drafts[i] ?? g.name"
            style="width: 200px"
            @update:value="(v: string) => (drafts[i] = v)"
            @blur="commitRename(i)"
            @keyup.enter="commitRename(i)"
          />
          <NSelect
            :value="g.type"
            :options="GROUP_TYPES"
            style="width: 130px"
            @update:value="(v: unknown) => (g.type = v as GroupType)"
          />
        </NSpace>
      </template>
      <template #header-extra>
        <NSpace size="small">
          <NButton size="tiny" @click="moveGroup(i, -1)">上移</NButton>
          <NButton size="tiny" @click="moveGroup(i, 1)">下移</NButton>
          <NButton size="tiny" type="error" ghost @click="removeGroup(i)">删除</NButton>
        </NSpace>
      </template>

      <NSpace v-if="g.type !== 'select'" align="center" style="margin-bottom: 8px">
        <span>测速地址</span>
        <NInput v-model:value="g.url" style="width: 300px" />
        <span>间隔</span>
        <NInputNumber
          :value="g.interval"
          :min="10"
          style="width: 110px"
          @update:value="(v: number | null) => (g.interval = v ?? 300)"
        />
        <span>秒</span>
        <template v-if="g.type === 'url-test'">
          <span>容差</span>
          <NInputNumber
            :value="g.tolerance"
            :min="0"
            style="width: 110px"
            @update:value="(v: number | null) => (g.tolerance = v ?? 50)"
          />
          <span>毫秒</span>
        </template>
      </NSpace>

      <div v-for="(m, mi) in g.members" :key="mi" class="member">
        <NTag size="small" :type="tagType(m)">{{ memberLabel(m, nodeMap, sourceMap) }}</NTag>
        <NSpace size="small">
          <NButton size="tiny" quaternary @click="moveMember(i, mi, -1)">↑</NButton>
          <NButton size="tiny" quaternary @click="moveMember(i, mi, 1)">↓</NButton>
          <NButton size="tiny" quaternary type="error" @click="removeMember(i, mi)">✕</NButton>
        </NSpace>
      </div>
      <NText v-if="!g.members.length" depth="3">暂无成员（空分组在生成配置时会自动加入 DIRECT）</NText>

      <NSpace style="margin-top: 8px">
        <NSelect
          :value="null"
          :options="nodeOptions"
          filterable
          placeholder="添加节点"
          style="width: 260px"
          @update:value="(v: unknown) => addMember(i, { kind: 'node', node_id: v as number })"
        />
        <NSelect
          :value="null"
          :options="groupOptions(g.name)"
          placeholder="添加分组"
          style="width: 160px"
          @update:value="(v: unknown) => addMember(i, { kind: 'group', name: v as string })"
        />
        <NButton size="small" @click="addMember(i, { kind: 'builtin', name: 'DIRECT' })">+ DIRECT</NButton>
        <NButton size="small" @click="addMember(i, { kind: 'builtin', name: 'REJECT' })">+ REJECT</NButton>
        <NButton size="small" @click="filterFor = i">+ 过滤器</NButton>
      </NSpace>
    </NCard>
    <NButton dashed block @click="addGroup">新建分组</NButton>
  </NSpace>

  <NModal
    :show="filterFor !== null"
    preset="card"
    title="添加过滤器（按名称动态匹配节点，机场更新后自动跟随）"
    style="width: 600px"
    @update:show="(v: boolean) => { if (!v) filterFor = null }"
  >
    <FilterForm :sources="sources" @submit="submitFilter" />
  </NModal>
</template>

<style scoped>
.member {
  align-items: center;
  display: flex;
  justify-content: space-between;
  max-width: 560px;
  padding: 2px 0;
}
</style>
```

- [ ] **Step 3: 修改 `ProfileEditView.vue`**

导入改为：

```ts
import type { NodeItem, Profile, ProfileDetail, Source, TemplateInfo } from '../api/types'
import GroupEditor from '../components/GroupEditor.vue'
import PreviewPanel from '../components/PreviewPanel.vue'
```

在 `const templates = ref<TemplateInfo[]>([])` 之后追加：

```ts
const nodes = ref<NodeItem[]>([])
const sources = ref<Source[]>([])
```

`load()` 的 try 块改为：

```ts
    const [d, t, n, s] = await Promise.all([
      api.getProfile(props.id), api.listTemplates(), api.listNodes(), api.listSources(),
    ])
    templates.value = t
    nodes.value = n
    sources.value = s
    setDetail(d)
```

模板中 `<NTabs type="line" default-value="preview" animated>` 改为 `default-value="groups"`，并在其中第一个位置插入：

```vue
        <NTabPane name="groups" tab="分组">
          <GroupEditor v-model="profile" :nodes="nodes" :sources="sources" />
        </NTabPane>
```

- [ ] **Step 4: 构建**

Run: `npm run build`
Expected: 成功

- [ ] **Step 5: 浏览器手动检查**（准备：手动源中导入名称为「香港 01」「香港 02」「日本 01」的 3 个节点，可复制同一个 ss 链接改 `#` 后的名称）

1. 打开方案编辑页，默认显示「分组」标签
2. 「新建分组」→ 出现「分组 1」；改名为「香港」后回车；类型切换为「自动测速」→ 出现测速地址、间隔、容差
3. 「+ 过滤器」：名称匹配填 `香港` →「预览匹配」显示 2 个节点 →「添加」后成员显示「过滤：全部节点源 /香港/」
4. 名称匹配填 `(` →「预览匹配」显示正则错误提示
5. 在另一个分组中「添加分组」选择「香港」，再把「香港」改名为「香港自动」→ 引用处同步显示「分组：香港自动」
6. 重复添加同一成员 → 提示「该成员已在分组中」；成员 ↑ ↓ ✕ 生效
7. 删除被引用的分组 → 确认框提示引用数量
8. 保存 → 切到「预览与订阅」，YAML 中 `proxy-groups` 与编辑结果一致

- [ ] **Step 6: 提交**

```bash
git add frontend/src
git commit -m "feat(web): add proxy group editor with filter members"
```

### Task 7: 规则、规则集与链式代理编辑器

**Files:**
- Create: `frontend/src/components/RuleEditor.vue`
- Create: `frontend/src/components/ProviderEditor.vue`
- Create: `frontend/src/components/ChainEditor.vue`
- Modify: `frontend/src/views/ProfileEditView.vue`（加入 3 个标签页）

**Interfaces:**
- Consumes: `insertBeforeMatch`、`moveItem`、`newRule`、`targetOptions`；`RULE_TYPES`、类型；Task 6 中 `ProfileEditView` 的 `nodes`
- Produces:
  - `RuleEditor`：`v-model`（`Profile`）
  - `ProviderEditor`：`v-model`（`Profile`；规则集改名时同步更新 `RULE-SET` 规则的 value）
  - `ChainEditor`：`v-model`（`Profile`），props `{ nodes: NodeItem[] }`

- [ ] **Step 1: 实现 `frontend/src/components/RuleEditor.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { NAlert, NButton, NCheckbox, NInput, NSelect, NSpace } from 'naive-ui'
import { RULE_TYPES, type Profile, type Rule, type RuleType } from '../api/types'
import { insertBeforeMatch, moveItem, newRule, targetOptions } from '../lib/profile'

const profile = defineModel<Profile>({ required: true })

const NO_RESOLVE_TYPES: RuleType[] = ['IP-CIDR', 'IP-CIDR6', 'GEOIP', 'RULE-SET']
const PLACEHOLDERS: Partial<Record<RuleType, string>> = {
  DOMAIN: 'www.example.com',
  'DOMAIN-SUFFIX': 'example.com',
  'DOMAIN-KEYWORD': 'google',
  'IP-CIDR': '10.0.0.0/8',
  'IP-CIDR6': '2001:db8::/32',
  GEOSITE: 'cn',
  GEOIP: 'CN',
  'PROCESS-NAME': 'Telegram.exe',
}

const typeOptions = RULE_TYPES.map((t) => ({ label: t, value: t }))
const targets = computed(() => targetOptions(profile.value).map((t) => ({ label: t, value: t })))
const providerOptions = computed(() => profile.value.rule_providers.map((p) => ({ label: p.name, value: p.name })))
const hasMatch = computed(() => profile.value.rules.some((r) => r.type === 'MATCH'))
const defaultTarget = computed(() => profile.value.groups[0]?.name ?? 'DIRECT')

function add() {
  profile.value.rules = insertBeforeMatch(profile.value.rules, newRule(defaultTarget.value))
}

function addMatch() {
  profile.value.rules.push({ type: 'MATCH', value: '', target: defaultTarget.value, no_resolve: false })
}

function setType(r: Rule, t: RuleType) {
  r.type = t
  if (t === 'MATCH' || t === 'RULE-SET') r.value = ''
  if (!NO_RESOLVE_TYPES.includes(t)) r.no_resolve = false
}

function move(i: number, delta: number) {
  profile.value.rules = moveItem(profile.value.rules, i, delta)
}

function remove(i: number) {
  profile.value.rules.splice(i, 1)
}
</script>

<template>
  <NSpace vertical>
    <NAlert v-if="!hasMatch" type="warning">
      规则需要以一条 MATCH 结尾（决定未匹配任何规则的流量走向）。
      <NButton text type="primary" @click="addMatch">添加 MATCH</NButton>
    </NAlert>
    <NAlert type="info">规则从上到下依次匹配，命中第一条即停止。</NAlert>
    <div v-for="(r, i) in profile.rules" :key="i" class="row">
      <span class="idx">{{ i + 1 }}</span>
      <NSelect
        :value="r.type"
        :options="typeOptions"
        style="width: 170px"
        @update:value="(v: unknown) => setType(r, v as RuleType)"
      />
      <NSelect
        v-if="r.type === 'RULE-SET'"
        :value="r.value || null"
        :options="providerOptions"
        placeholder="选择规则集"
        style="width: 240px"
        @update:value="(v: unknown) => (r.value = String(v ?? ''))"
      />
      <NInput v-else-if="r.type !== 'MATCH'" v-model:value="r.value" :placeholder="PLACEHOLDERS[r.type]" style="width: 240px" />
      <span v-else class="match-text">其余所有流量</span>
      <span>→</span>
      <NSelect
        :value="r.target"
        :options="targets"
        style="width: 170px"
        @update:value="(v: unknown) => (r.target = v as string)"
      />
      <NCheckbox v-if="NO_RESOLVE_TYPES.includes(r.type)" v-model:checked="r.no_resolve">no-resolve</NCheckbox>
      <NButton size="tiny" quaternary @click="move(i, -1)">↑</NButton>
      <NButton size="tiny" quaternary @click="move(i, 1)">↓</NButton>
      <NButton size="tiny" quaternary type="error" @click="remove(i)">✕</NButton>
    </div>
    <NButton dashed block @click="add">添加规则（插在 MATCH 之前）</NButton>
  </NSpace>
</template>

<style scoped>
.row {
  align-items: center;
  display: flex;
  gap: 8px;
}
.idx {
  color: #999;
  text-align: right;
  width: 28px;
}
.match-text {
  color: #999;
  width: 240px;
}
</style>
```

- [ ] **Step 2: 实现 `frontend/src/components/ProviderEditor.vue`**

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NEmpty, NInput, NInputNumber, NSelect, NSpace, useDialog, useMessage } from 'naive-ui'
import type { Profile, RuleProvider } from '../api/types'

const profile = defineModel<Profile>({ required: true })
const message = useMessage()
const dialog = useDialog()

const BEHAVIORS = [
  { label: '域名 domain', value: 'domain' },
  { label: 'IP 段 ipcidr', value: 'ipcidr' },
  { label: '混合 classical', value: 'classical' },
]
const FORMATS = [
  { label: 'mrs', value: 'mrs' },
  { label: 'yaml', value: 'yaml' },
  { label: 'text', value: 'text' },
]

const drafts = ref<Record<number, string>>({})

function usage(name: string): number {
  return profile.value.rules.filter((r) => r.type === 'RULE-SET' && r.value === name).length
}

function add() {
  let i = profile.value.rule_providers.length + 1
  while (profile.value.rule_providers.some((p) => p.name === `ruleset-${i}`)) i++
  profile.value.rule_providers.push({ name: `ruleset-${i}`, behavior: 'domain', format: 'mrs', url: '', interval: 86400 })
}

function commitRename(index: number) {
  const draft = drafts.value[index]
  delete drafts.value[index]
  if (draft === undefined) return
  const old = profile.value.rule_providers[index].name
  const name = draft.trim()
  if (name === old) return
  if (!name || profile.value.rule_providers.some((p) => p.name === name)) {
    message.error(`规则集名称「${name}」为空或已存在`)
    return
  }
  profile.value.rule_providers[index].name = name
  for (const r of profile.value.rules) {
    if (r.type === 'RULE-SET' && r.value === old) r.value = name
  }
}

function remove(index: number) {
  const p = profile.value.rule_providers[index]
  const used = usage(p.name)
  dialog.warning({
    title: '删除规则集',
    content: used ? `「${p.name}」被 ${used} 条规则引用，删除后预览会报错。确定删除？` : `确定删除「${p.name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => {
      profile.value.rule_providers.splice(index, 1)
    },
  })
}
</script>

<template>
  <NSpace vertical>
    <NAlert type="info">规则集是远程维护的规则列表，在「规则」中用 RULE-SET 类型引用。mrs 格式只支持 domain 和 ipcidr。</NAlert>
    <NEmpty v-if="!profile.rule_providers.length" description="还没有规则集" />
    <div v-for="(p, i) in profile.rule_providers" :key="i" class="row">
      <NInput
        :value="drafts[i] ?? p.name"
        style="width: 180px"
        @update:value="(v: string) => (drafts[i] = v)"
        @blur="commitRename(i)"
        @keyup.enter="commitRename(i)"
      />
      <NSelect
        :value="p.behavior"
        :options="BEHAVIORS"
        style="width: 150px"
        @update:value="(v: unknown) => (p.behavior = v as RuleProvider['behavior'])"
      />
      <NSelect
        :value="p.format"
        :options="FORMATS"
        style="width: 90px"
        @update:value="(v: unknown) => (p.format = v as RuleProvider['format'])"
      />
      <NInput v-model:value="p.url" placeholder="https://..." style="flex: 1" />
      <NInputNumber
        :value="p.interval"
        :min="60"
        style="width: 130px"
        @update:value="(v: number | null) => (p.interval = v ?? 86400)"
      >
        <template #suffix>秒</template>
      </NInputNumber>
      <span class="usage">{{ usage(p.name) }} 条规则</span>
      <NButton size="tiny" quaternary type="error" @click="remove(i)">✕</NButton>
    </div>
    <NButton dashed block @click="add">添加规则集</NButton>
  </NSpace>
</template>

<style scoped>
.row {
  align-items: center;
  display: flex;
  gap: 8px;
}
.usage {
  color: #999;
  width: 70px;
}
</style>
```

- [ ] **Step 3: 实现 `frontend/src/components/ChainEditor.vue`**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { NAlert, NButton, NEmpty, NRadioButton, NRadioGroup, NSelect, NSpace } from 'naive-ui'
import type { Chain, NodeItem, Profile } from '../api/types'

const profile = defineModel<Profile>({ required: true })
const props = defineProps<{ nodes: NodeItem[] }>()

const nodeOptions = computed(() => props.nodes.map((n) => ({ label: n.name, value: n.id })))
const groupOptions = computed(() => profile.value.groups.map((g) => ({ label: g.name, value: g.name })))
const canAdd = computed(() => props.nodes.length > 0 && profile.value.groups.length > 0)

function add() {
  profile.value.chains.push({
    node: { kind: 'node', node_id: props.nodes[0].id },
    via: { kind: 'group', name: profile.value.groups[0].name },
  })
}

function setViaKind(c: Chain, kind: 'group' | 'node') {
  if (kind === c.via.kind) return
  c.via = kind === 'group'
    ? { kind: 'group', name: profile.value.groups[0]?.name ?? '' }
    : { kind: 'node', node_id: props.nodes[0]?.id ?? 0 }
}

function setVia(c: Chain, value: unknown) {
  c.via = c.via.kind === 'group' ? { kind: 'group', name: value as string } : { kind: 'node', node_id: value as number }
}

function remove(i: number) {
  profile.value.chains.splice(i, 1)
}
</script>

<template>
  <NSpace vertical>
    <NAlert type="info">
      链式代理：落地节点经由「前置」（分组或节点）出站，生成的配置中为 Mihomo 的 dialer-proxy。
      落地节点本身需要出现在某个分组里才会生效，且前置不能包含该落地节点。
    </NAlert>
    <NEmpty v-if="!profile.chains.length" description="还没有链式代理" />
    <div v-for="(c, i) in profile.chains" :key="i" class="row">
      <span>落地节点</span>
      <NSelect
        :value="c.node.node_id"
        :options="nodeOptions"
        filterable
        style="width: 240px"
        @update:value="(v: unknown) => (c.node = { kind: 'node', node_id: v as number })"
      />
      <span>经由</span>
      <NRadioGroup :value="c.via.kind" @update:value="(v: unknown) => setViaKind(c, v as 'group' | 'node')">
        <NRadioButton value="group">分组</NRadioButton>
        <NRadioButton value="node">节点</NRadioButton>
      </NRadioGroup>
      <NSelect
        :value="c.via.kind === 'group' ? c.via.name : c.via.node_id"
        :options="c.via.kind === 'group' ? groupOptions : nodeOptions"
        filterable
        style="width: 240px"
        @update:value="(v: unknown) => setVia(c, v)"
      />
      <NButton size="tiny" quaternary type="error" @click="remove(i)">✕</NButton>
    </div>
    <NButton dashed block :disabled="!canAdd" @click="add">添加链式代理</NButton>
  </NSpace>
</template>

<style scoped>
.row {
  align-items: center;
  display: flex;
  gap: 8px;
}
</style>
```

- [ ] **Step 4: 修改 `ProfileEditView.vue`**

导入追加：

```ts
import ChainEditor from '../components/ChainEditor.vue'
import ProviderEditor from '../components/ProviderEditor.vue'
import RuleEditor from '../components/RuleEditor.vue'
```

在「分组」`NTabPane` 之后、「预览与订阅」之前插入：

```vue
        <NTabPane name="rules" tab="规则">
          <RuleEditor v-model="profile" />
        </NTabPane>
        <NTabPane name="providers" tab="规则集">
          <ProviderEditor v-model="profile" />
        </NTabPane>
        <NTabPane name="chains" tab="链式代理">
          <ChainEditor v-model="profile" :nodes="nodes" />
        </NTabPane>
```

- [ ] **Step 5: 构建与测试**

Run: `npm run build && npm test`
Expected: 均成功

- [ ] **Step 6: 浏览器手动检查**（接 Task 6 的数据；另在手动源中导入一个名为「落地」的节点）

1. 「规则」：套用过「漏网之鱼」时 MATCH 在末尾；「添加规则」新行出现在 MATCH 之前；删除 MATCH 后出现黄色提示，点「添加 MATCH」恢复
2. 规则类型切到 `IP-CIDR` 出现 no-resolve 勾选框；切到 `RULE-SET` 值变为规则集下拉
3. 「规则集」：新建 `ruleset-1`，改名为 `my-ads` 后，引用它的 RULE-SET 规则同步变化；「n 条规则」计数正确
4. 「链式代理」：添加一条：落地节点选「落地」，经由分组「香港自动」；把「落地」加入任一分组并保存
5. 「预览与订阅」：YAML 中「落地」节点带 `dialer-proxy: 香港自动`
6. 把链式代理的前置改为包含「落地」的分组并保存 → 预览报「检测到循环引用」，订阅链接仍返回上一次成功的配置

- [ ] **Step 7: 提交**

```bash
git add frontend/src
git commit -m "feat(web): add rule, rule-provider and chain editors"
```

### Task 8: Docker 镜像、部署文件与 README

**Files:**
- Create: `Dockerfile`、`.dockerignore`、`docker-compose.yml`、`.env.example`、`README.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: P2 `routeforge` 命令与环境变量；Task 1 `ROUTEFORGE_STATIC_DIR`；前端 `npm run build` 产物 `frontend/dist`
- Produces: 镜像内 `/app/static`（前端）、`/data`（数据卷）、端口 8000；`docker compose up -d` 一键部署

- [ ] **Step 1: 创建 `Dockerfile`**

```dockerfile
# ---- 前端构建 ----
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 运行时 ----
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/routeforge ./routeforge
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist /app/static

ENV PATH="/app/.venv/bin:$PATH" \
    ROUTEFORGE_DATA_DIR=/data \
    ROUTEFORGE_STATIC_DIR=/app/static
VOLUME /data
EXPOSE 8000
CMD ["routeforge"]
```

- [ ] **Step 2: 创建 `.dockerignore`**

```
.git
.idea
**/__pycache__
**/.venv
**/node_modules
frontend/dist
backend/data
data
docs
.env
```

- [ ] **Step 3: 创建 `docker-compose.yml` 与 `.env.example`**

`docker-compose.yml`：

```yaml
services:
  routeforge:
    build: .
    image: routeforge:latest
    restart: unless-stopped
    # 只监听本机，由宿主机上的反向代理（Caddy / Nginx）提供 HTTPS
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      ROUTEFORGE_ADMIN_PASSWORD: ${ROUTEFORGE_ADMIN_PASSWORD:?请在 .env 中设置 ROUTEFORGE_ADMIN_PASSWORD}
      # 容器只能经由本机反代访问，信任其转发的客户端 IP（登录限速按真实 IP 计数）
      ROUTEFORGE_FORWARDED_ALLOW_IPS: "*"
    volumes:
      - ./data:/data
```

`.env.example`：

```
# 首次启动时设置的管理员密码（之后修改此值不会生效，见 README「修改管理员密码」）
ROUTEFORGE_ADMIN_PASSWORD=change-me-to-a-long-random-password
```

- [ ] **Step 4: 修改 `.gitignore`**

把 `/data/` 一行改为 `data/`，并追加：

```
.env
jar
```

- [ ] **Step 5: 创建 `README.md`**

````markdown
# RouteForge

自托管的订阅转换与规则管理服务：维护自己的节点库（手动分享链接 + 机场订阅），组合成「配置方案」，为每个方案生成订阅链接，供 Clash Verge Rev 等 Mihomo 内核客户端直接订阅。

## 功能

- 节点源：手动粘贴 ss / vmess / vless（含 Reality）/ trojan / hysteria2 / tuic 分享链接；导入机场订阅并定时刷新（支持 Base64、明文链接、Clash YAML，失败时保留上次节点）
- 配置方案：代理分组（手动选择 / 自动测速 / 故障转移 / 负载均衡），成员可以是节点、分组、DIRECT/REJECT，或按名称正则动态匹配的过滤器
- 分流规则：内置模板（广告拦截、AI 服务、流媒体、Telegram、国内直连、漏网之鱼），也可自定义规则与远程规则集
- 链式代理：指定落地节点经由某个分组 / 节点出站（Mihomo `dialer-proxy`）
- 订阅链接：带随机 token，可一键重置；方案改坏时继续返回上次成功的配置；单一机场源时透传流量与到期信息

第一期仅输出 Mihomo（Clash Meta）配置。

## 部署（Docker）

```bash
git clone <仓库地址> routeforge && cd routeforge
cp .env.example .env        # 编辑 .env，设置管理员密码
docker compose up -d --build
```

服务监听 `127.0.0.1:8000`，请在宿主机用反向代理提供 HTTPS（管理会话 cookie 默认只在 HTTPS 下发送）。Caddy 示例：

```
rf.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

数据保存在 `./data/routeforge.db`，备份该文件即可。

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ROUTEFORGE_ADMIN_PASSWORD` | — | 首次启动必填，之后不再读取 |
| `ROUTEFORGE_DATA_DIR` | `/data`（镜像内） | SQLite 数据目录 |
| `ROUTEFORGE_COOKIE_SECURE` | `true` | 仅在 HTTPS 下发送会话 cookie；纯 HTTP 内网使用时设为 `false` |
| `ROUTEFORGE_FORWARDED_ALLOW_IPS` | `127.0.0.1` | 信任哪些反向代理的 `X-Forwarded-For` |
| `ROUTEFORGE_HOST` / `ROUTEFORGE_PORT` | `0.0.0.0` / `8000` | 监听地址 |

### 修改管理员密码

```bash
docker compose down
sqlite3 data/routeforge.db "DELETE FROM setting WHERE key='admin_password_hash';"
# 修改 .env 中的 ROUTEFORGE_ADMIN_PASSWORD 后
docker compose up -d
```

## 使用

1. 「节点源」：新建手动源并导入分享链接，或添加机场订阅链接
2. 「配置方案」→ 新建 →「套用模板」（建议依次套用 国内直连、广告拦截、AI 服务、漏网之鱼），在「分组」里给「节点选择」添加节点或过滤器
3. 「预览与订阅」确认无错误后，复制订阅链接到客户端

## 开发

```bash
# 后端
cd backend
uv sync
uv run pytest
ROUTEFORGE_ADMIN_PASSWORD=pw ROUTEFORGE_COOKIE_SECURE=false uv run routeforge

# 前端（另一个终端，开发服务器把 /api、/sub 代理到 8000 端口）
cd frontend
npm install
npm test
npm run dev
```
````

- [ ] **Step 6: 生产形态验证（不依赖 Docker）**

```bash
cd frontend && npm run build && cd ../backend
ROUTEFORGE_ADMIN_PASSWORD=pw ROUTEFORGE_COOKIE_SECURE=false ROUTEFORGE_DATA_DIR=./data ROUTEFORGE_STATIC_DIR=../frontend/dist uv run routeforge
```

浏览器打开 `http://localhost:8000`：能登录；在 `/profiles` 页面按 F5 刷新仍显示该页面；`http://localhost:8000/api/nope` 返回 JSON 404。完成后停止服务并删除 `backend/data/`。

- [ ] **Step 7: Docker 构建验证（需要装有 Docker 的机器，例如目标 VPS）**

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs --tail 20 routeforge     # 应看到 Uvicorn running on http://0.0.0.0:8000
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/          # 200
curl -s http://127.0.0.1:8000/api/auth/me                                # {"detail":"未登录"}
docker compose down
```

当前开发机未安装 Docker；若在本机无法执行此步，请在交付说明中如实注明「Docker 构建未在本机验证」，并在 VPS 首次部署时执行。

- [ ] **Step 8: 全量回归**

Run: `cd backend && uv run pytest` 与 `cd frontend && npm test && npm run build`
Expected: 全部通过

- [ ] **Step 9: 提交**

```bash
git add Dockerfile .dockerignore docker-compose.yml .env.example README.md .gitignore
git commit -m "build: add docker image, compose file and readme"
```

---

## P3 完成标准

- 后端 `uv run pytest`、前端 `npm test` 与 `npm run build` 全部通过
- Task 3–7 的浏览器手动检查逐项通过
- 端到端：用 Clash Verge Rev（或其他 Mihomo 客户端）订阅一个方案链接，确认分组、规则与链式代理生效（spec 成功标准）
