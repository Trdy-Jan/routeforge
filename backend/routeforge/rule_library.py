"""在线规则库：索引 MetaCubeX/meta-rules-dat 的 geosite / geoip / geo-lite 规则，并按需拉取规则内容预览。"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

REPO = "MetaCubeX/meta-rules-dat"
BRANCH = "meta"
TREE_API = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}:{{}}"
MRS_BASE = f"https://github.com/{REPO}/raw/{BRANCH}"  # 与 renderers/mihomo.py 的 GEOSITE_MRS_BASE 保持一致
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

# 分类 → (仓库目录, rule-provider behavior)
CATEGORIES: dict[str, tuple[str, str]] = {
    "geosite": ("geo/geosite", "domain"),
    "geoip": ("geo/geoip", "ipcidr"),
    "geo-lite": ("geo-lite/geosite", "domain"),
}

INDEX_TTL = 86400
CONTENT_TTL = 86400
CONTENT_CACHE_SIZE = 50
# 单条规则最多缓存的行数：只是防止异常大文件占满内存，正常规则（最大约十余万行）不会触发
MAX_LINES = 500000
PAGE_SIZE = 200
MAX_PAGE_SIZE = 1000
MAX_QUERY_LENGTH = 200


def _path(category: str, name: str, ext: str) -> str:
    return f"{CATEGORIES[category][0]}/{quote(name, safe='@!-_.')}.{ext}"


def item_url(category: str, name: str) -> str:
    """写入配置的 .mrs 规则集 URL。"""
    return f"{MRS_BASE}/{_path(category, name, 'mrs')}"


def list_url(category: str, name: str) -> str:
    """用于预览的纯文本 .list URL。"""
    return f"{RAW_BASE}/{_path(category, name, 'list')}"


@dataclass(frozen=True)
class LibraryItem:
    category: str
    name: str
    behavior: str
    url: str


@dataclass
class LibraryIndex:
    items: list[LibraryItem]
    updated_at: datetime | None
    error: str | None


@dataclass
class RuleContent:
    """规则内容的一页。total 为规则总行数，matched 为按 q 筛选后的行数，lines 为从 offset 开始的一页。"""

    total: int
    matched: int
    offset: int
    lines: list[str]


@dataclass(frozen=True)
class _CachedLines:
    lines: list[str]
    lowered: list[str]  # 预先转小写，检索时不必每次处理全部行


class LibraryUnavailable(Exception):
    """无法从上游获取数据；消息可直接展示给用户。"""


def _describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return str(exc) or type(exc).__name__


class RuleLibrary:
    def __init__(self, client: httpx.Client, clock: Callable[[], float] = time.time) -> None:
        self._client = client
        self._clock = clock
        self._lock = threading.Lock()
        self._items: list[LibraryItem] | None = None
        self._names: set[tuple[str, str]] = set()
        self._fetched_at = 0.0
        self._updated_at: datetime | None = None
        self._error: str | None = None
        self._contents: OrderedDict[tuple[str, str], tuple[float, _CachedLines]] = OrderedDict()

    def index(self, force: bool = False) -> LibraryIndex:
        with self._lock:
            fresh = self._items is not None and self._clock() - self._fetched_at < INDEX_TTL
            if force or not fresh:
                try:
                    items = self._fetch_index()
                except Exception as exc:  # noqa: BLE001 — 任何上游错误都降级为旧数据或友好报错
                    self._error = f"无法从 GitHub 获取规则列表：{_describe(exc)}"
                    self._fetched_at = self._clock()  # 失败也计时，避免每次请求都去撞限流
                    if self._items is None:
                        self._fetched_at = 0.0
                        raise LibraryUnavailable(self._error) from exc
                else:
                    self._items = items
                    self._names = {(i.category, i.name) for i in items}
                    self._fetched_at = self._clock()
                    self._updated_at = datetime.now(timezone.utc)
                    self._error = None
            return LibraryIndex(items=list(self._items), updated_at=self._updated_at, error=self._error)

    def _fetch_index(self) -> list[LibraryItem]:
        items: list[LibraryItem] = []
        for category, (directory, behavior) in CATEGORIES.items():
            resp = self._client.get(TREE_API.format(directory), headers={"Accept": "application/vnd.github+json"},
                                    timeout=30)
            resp.raise_for_status()
            for entry in resp.json().get("tree", []):
                path = entry.get("path", "")
                if entry.get("type") == "blob" and path.endswith(".mrs"):
                    name = path[: -len(".mrs")]
                    items.append(LibraryItem(category, name, behavior, item_url(category, name)))
        return items

    def content(self, category: str, name: str, q: str = "", offset: int = 0, limit: int = PAGE_SIZE) -> RuleContent:
        """返回规则内容的一页；q 非空时只保留包含 q 的行（不区分大小写）。"""
        cached = self._lines(category, name)
        needle = q.strip().lower()
        if needle:
            matched = [line for line, low in zip(cached.lines, cached.lowered) if needle in low]
        else:
            matched = cached.lines
        offset = max(offset, 0)
        return RuleContent(total=len(cached.lines), matched=len(matched), offset=offset,
                           lines=matched[offset:offset + max(limit, 0)])

    def _lines(self, category: str, name: str) -> _CachedLines:
        self.index()
        key = (category, name)
        with self._lock:
            if key not in self._names:
                raise KeyError(key)
            cached = self._contents.get(key)
            if cached and self._clock() - cached[0] < CONTENT_TTL:
                self._contents.move_to_end(key)
                return cached[1]
        try:
            resp = self._client.get(list_url(category, name), timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise LibraryUnavailable(f"无法获取规则内容：{_describe(exc)}") from exc
        lines = [s for s in (raw.strip() for raw in resp.text.splitlines()) if s and not s.startswith("#")][:MAX_LINES]
        result = _CachedLines(lines=lines, lowered=[line.lower() for line in lines])
        with self._lock:
            self._contents[key] = (self._clock(), result)
            self._contents.move_to_end(key)
            while len(self._contents) > CONTENT_CACHE_SIZE:
                self._contents.popitem(last=False)
        return result
