"""拉取机场订阅。"""

from dataclasses import dataclass

import httpx

_USERINFO_KEYS = ("upload", "download", "total", "expire")


@dataclass
class FetchResult:
    text: str
    userinfo: dict[str, int] | None


def fetch_subscription(client: httpx.Client, url: str, user_agent: str) -> FetchResult:
    resp = client.get(url, headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return FetchResult(text=resp.text, userinfo=parse_userinfo(resp.headers.get("subscription-userinfo")))


def parse_userinfo(header: str | None) -> dict[str, int] | None:
    if not header:
        return None
    info: dict[str, int] = {}
    for part in header.split(";"):
        key, sep, value = part.strip().partition("=")
        value = value.strip()
        if sep and key in _USERINFO_KEYS and value.isdigit():
            info[key] = int(value)
    return info or None


def format_userinfo(info: dict) -> str:
    return "; ".join(f"{k}={info[k]}" for k in _USERINFO_KEYS if k in info)
