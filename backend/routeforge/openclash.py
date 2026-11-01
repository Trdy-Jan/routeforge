"""推送到 OpenClash：方案内容变化后，登录路由器 LuCI 并调用 OpenClash 的「更新配置」接口。

OpenClash 收到请求后会按它自己的订阅设置重新下载该配置文件（即本服务的订阅链接）、套用覆写设置并重载。
"""

import asyncio
import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session

from routeforge.db.models import ProfileRow, Setting, utcnow
from routeforge.services.render import render_profile

logger = logging.getLogger(__name__)

CONFIG_KEY = "openclash_config"
PUSHED_HASH_KEY = "openclash_pushed_hash"
TARGET = "mihomo"
UPDATE_TIMEOUT = 180  # OpenClash 会同步下载订阅并重载，可能较慢


class OpenClashConfig(BaseModel):
    router_url: str = ""
    username: str = "root"
    password: str = ""
    config_name: str = ""  # OpenClash 中的配置文件名（不含 .yaml），如 192_168_31_88
    profile_id: int | None = None  # 该配置文件订阅的是哪个方案
    auto_push: bool = False

    @property
    def complete(self) -> bool:
        return bool(self.router_url and self.username and self.config_name)


class OpenClashError(Exception):
    pass


@dataclass
class PushStatus:
    at: datetime
    ok: bool
    message: str
    trigger: str  # "auto" | "manual"


def load_config(session: Session) -> OpenClashConfig:
    row = session.get(Setting, CONFIG_KEY)
    return OpenClashConfig.model_validate_json(row.value) if row else OpenClashConfig()


def save_config(session: Session, cfg: OpenClashConfig) -> None:
    row = session.get(Setting, CONFIG_KEY) or Setting(key=CONFIG_KEY, value="")
    row.value = cfg.model_dump_json()
    session.add(row)
    session.commit()


def normalize_router_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return re.sub(r"/cgi-bin/luci.*$", "", url)


def luci_login(client: httpx.Client, cfg: OpenClashConfig) -> tuple[str, dict[str, str]]:
    """登录 LuCI，返回 (带 stok 的 luci 基础地址, cookies)。"""
    base = f"{normalize_router_url(cfg.router_url)}/cgi-bin/luci"
    try:
        resp = client.post(base, data={"luci_username": cfg.username, "luci_password": cfg.password},
                           follow_redirects=False, timeout=15)
    except httpx.HTTPError as e:
        raise OpenClashError(f"无法连接路由器：{e}") from e
    cookies = {k: v for k, v in resp.cookies.items() if k.startswith("sysauth")}
    for k in cookies:  # 共享的 httpx 客户端会把 cookie 存进全局 jar，这里只用显式传递的
        client.cookies.delete(k)
    if not cookies:
        if resp.status_code in (200, 403):
            raise OpenClashError("登录路由器失败：用户名或密码错误")
        raise OpenClashError(f"登录路由器失败（HTTP {resp.status_code}）")
    # 旧版 LuCI 把会话令牌放在 URL 里：/cgi-bin/luci/;stok=xxx/
    m = re.search(r";stok=([0-9a-fA-F]+)", resp.headers.get("location", ""))
    if m:
        base = f"{base}/;stok={m.group(1)}"
    return base, cookies


def trigger_update(client: httpx.Client, cfg: OpenClashConfig) -> str:
    if not cfg.complete:
        raise OpenClashError("请先填写路由器地址、用户名和配置文件名")
    base, cookies = luci_login(client, cfg)
    url = f"{base}/admin/services/openclash/update_config"
    params = {"filename": cfg.config_name, "_": str(int(time.time() * 1000))}
    header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    try:
        resp = client.get(url, params=params, headers={"Cookie": header}, follow_redirects=False,
                          timeout=UPDATE_TIMEOUT)
    except httpx.TimeoutException as e:
        raise OpenClashError("OpenClash 更新超时，请到路由器上查看运行日志") from e
    except httpx.HTTPError as e:
        raise OpenClashError(f"调用 OpenClash 失败：{e}") from e
    if resp.status_code in (301, 302, 303, 401, 403):
        raise OpenClashError("路由器登录状态无效，调用被拒绝")
    if resp.status_code == 404:
        raise OpenClashError("路由器上没有找到 OpenClash 的更新接口，请确认已安装 OpenClash")
    if resp.status_code >= 400:
        raise OpenClashError(f"调用 OpenClash 失败（HTTP {resp.status_code}）")
    # 新版 OpenClash 返回 {"status": "success", "message": "Config update started successfully", ...}
    try:
        data = resp.json()
    except ValueError:
        data = None
    if isinstance(data, dict) and data.get("status") not in (None, "success"):
        raise OpenClashError(f"OpenClash 返回失败：{data.get('message') or data.get('status')}")
    return f"已通知 OpenClash 更新配置「{cfg.config_name}」"


def check_login(client: httpx.Client, cfg: OpenClashConfig) -> str:
    if not cfg.router_url:
        raise OpenClashError("请先填写路由器地址")
    luci_login(client, cfg)
    return "登录路由器成功"


class OpenClashPusher:
    """监听数据变化，防抖后渲染所选方案；内容与上次推送不同时通知 OpenClash 更新。"""

    def __init__(self, engine: Engine, client: httpx.Client, debounce: float = 3) -> None:
        self._engine = engine
        self._client = client
        self._debounce = debounce
        self._dirty = threading.Event()
        self._last_change = 0.0
        self._lock = threading.Lock()
        self.status: PushStatus | None = None

    def notify_changed(self) -> None:
        self._last_change = time.monotonic()
        self._dirty.set()

    async def run(self, poll: float = 1) -> None:
        while True:
            await asyncio.sleep(poll)
            if not self._dirty.is_set() or time.monotonic() - self._last_change < self._debounce:
                continue
            self._dirty.clear()
            try:
                await asyncio.to_thread(self.push_if_changed)
            except Exception:
                logger.exception("自动推送到 OpenClash 出错")

    def push_if_changed(self) -> bool:
        """自动推送；返回是否实际调用了 OpenClash。"""
        with Session(self._engine) as session:
            cfg = load_config(session)
            if not cfg.auto_push or not cfg.complete or cfg.profile_id is None:
                return False
            digest = _profile_digest(session, cfg.profile_id)
            if digest is None:
                return False
            pushed = session.get(Setting, PUSHED_HASH_KEY)
            if pushed is not None and pushed.value == digest:
                return False
        self._push(cfg, digest, "auto")
        return True

    def push_now(self) -> PushStatus:
        with Session(self._engine) as session:
            cfg = load_config(session)
            digest = _profile_digest(session, cfg.profile_id) if cfg.profile_id is not None else None
        self._push(cfg, digest, "manual")
        assert self.status is not None
        return self.status

    def _push(self, cfg: OpenClashConfig, digest: str | None, trigger: str) -> None:
        with self._lock:
            try:
                msg = trigger_update(self._client, cfg)
            except OpenClashError as e:
                logger.warning("推送到 OpenClash 失败：%s", e)
                self.status = PushStatus(utcnow(), False, str(e), trigger)
                return
            self.status = PushStatus(utcnow(), True, msg, trigger)
            if digest is not None:
                with Session(self._engine) as session:
                    row = session.get(Setting, PUSHED_HASH_KEY) or Setting(key=PUSHED_HASH_KEY, value="")
                    row.value = digest
                    session.add(row)
                    session.commit()


def _profile_digest(session: Session, profile_id: int) -> str | None:
    row = session.get(ProfileRow, profile_id)
    if row is None:
        return None
    try:
        outcome = render_profile(session, row.to_profile(), TARGET)
    except Exception:
        logger.exception("渲染方案 #%s 出错，跳过推送", profile_id)
        return None
    if outcome.result is None:
        return None
    return hashlib.sha256(outcome.result.content.encode()).hexdigest()
