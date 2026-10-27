# RouteForge

自托管的订阅转换与规则管理服务：维护自己的节点库（手动分享链接 + 机场订阅），组合成「配置方案」，为每个方案生成订阅链接，供 Clash Verge Rev 等 Mihomo 内核客户端直接订阅。

## 功能

- 节点源：手动粘贴 ss / vmess / vless（含 Reality）/ trojan / hysteria2 / tuic 分享链接；导入机场订阅并定时刷新（支持 Base64、明文链接、Clash YAML，失败时保留上次节点）
- 配置方案：代理分组（手动选择 / 自动测速 / 故障转移 / 负载均衡），成员可以是节点、分组、DIRECT/REJECT，或按名称正则动态匹配的过滤器
- 分流规则：内置模板（广告拦截、AI 服务、流媒体、Telegram、GitHub、Docker、国内直连、漏网之鱼），也可自定义规则与远程规则集
- 链式代理：指定落地节点经由某个分组 / 节点出站（Mihomo `dialer-proxy`）
- 订阅链接：带随机 token，可一键重置；方案改坏时继续返回上次成功的配置；单一机场源时透传流量与到期信息

第一期仅输出 Mihomo（Clash Meta）配置。

## 部署（Docker）

```bash
git clone <仓库地址> routeforge && cd routeforge
cp .env.example .env        # 编辑 .env，设置管理员密码
docker compose up -d --build
```

服务默认监听 `127.0.0.1:8000`。HTTP 和 HTTPS 都可以访问：会话 cookie 默认是 `auto` 模式，HTTPS 访问时带 `Secure` 标记，HTTP 访问时不带。

- **局域网直接用 HTTP**：把 `docker-compose.yml` 的端口改为 `"8000:8000"`（或其他端口），用 `http://<局域网 IP>:8000` 访问即可。注意此时密码和订阅 token 以明文传输，不要这样暴露到公网。
- **公网**：保持只监听本机，在宿主机用反向代理提供 HTTPS。Caddy 示例（默认的 `reverse_proxy` 即会正确设置 `X-Forwarded-For` 和 `X-Forwarded-Proto`）：

```
rf.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

反向代理必须把 `X-Forwarded-For` 设置（覆盖）为真实客户端地址，登录限速才会按真实 IP 计数。Nginx 请使用：

```
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
```

`X-Forwarded-Proto` 让服务知道外部是 HTTPS，从而给 cookie 加上 `Secure` 标记。

不要使用 `$proxy_add_x_forwarded_for`，它会保留客户端自带的值，可被用来伪造 IP 绕过限速。

数据保存在 `./data/routeforge.db`，备份该文件即可。

出于安全考虑，API 文档（`/docs`、`/openapi.json`）已禁用。

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ROUTEFORGE_ADMIN_PASSWORD` | — | 首次启动必填，之后不再读取 |
| `ROUTEFORGE_DATA_DIR` | `/data`（镜像内） | SQLite 数据目录 |
| `ROUTEFORGE_COOKIE_SECURE` | `auto` | `auto`：按访问方式决定，HTTPS 下 cookie 带 `Secure`，HTTP 下不带；`true`：始终带 `Secure`（此时 HTTP 访问无法登录，登录页会提示）；`false`：始终不带 |
| `ROUTEFORGE_FORWARDED_ALLOW_IPS` | `127.0.0.1` | 信任哪些反向代理的 `X-Forwarded-For`；`docker-compose.yml` 中默认为 `172.16.0.0/12`（Docker 桥接网段，宿主机反代经 Docker 网关访问容器）。Docker 使用自定义网段时需调整该 CIDR |
| `ROUTEFORGE_HOST` / `ROUTEFORGE_PORT` | `0.0.0.0` / `8000` | 监听地址 |

### 修改管理员密码

```bash
docker compose down
sqlite3 data/routeforge.db "DELETE FROM setting WHERE key='admin_password_hash';"
# 修改 .env 中的 ROUTEFORGE_ADMIN_PASSWORD 后
docker compose up -d
```

服务重新创建密码哈希时会同时轮换会话密钥，因此所有已登录的会话都会失效，需要重新登录。

## 使用

1. 「节点源」：新建手动源并导入分享链接，或添加机场订阅链接
2. 「配置方案」→ 新建 →「套用模板」（建议依次套用 国内直连、广告拦截、AI 服务、漏网之鱼），在「分组」里给「节点选择」添加节点或过滤器
3. 「预览与订阅」确认无错误后，复制订阅链接到客户端

方案有错误时，订阅链接会继续返回上次成功生成的配置；从未成功生成过的方案则会返回错误，直到修复为止，所以发放链接前请先在「预览」中确认无错误。

## 开发

```bash
# 后端
cd backend
uv sync
uv run pytest
ROUTEFORGE_ADMIN_PASSWORD=pw uv run routeforge

# 前端（另一个终端，开发服务器把 /api、/sub 代理到 8000 端口）
cd frontend
npm install
npm test
npm run dev
```
