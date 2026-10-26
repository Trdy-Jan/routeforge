"""分享链接解析的通用工具。"""

import base64
from typing import NamedTuple
from urllib.parse import parse_qs, quote, unquote, urlencode

from routeforge.parsers.errors import ParseError


def b64decode_loose(data: str) -> str:
    """容忍缺失填充、urlsafe 字符和换行的 base64 解码。"""
    s = "".join(data.split()).replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as e:
        raise ParseError(f"base64 解码失败：{e}") from e


def b64encode_text(text: str, *, urlsafe: bool = False, padding: bool = True) -> str:
    raw = text.encode("utf-8")
    out = (base64.urlsafe_b64encode(raw) if urlsafe else base64.b64encode(raw)).decode("ascii")
    return out if padding else out.rstrip("=")


def split_hostport(hp: str) -> tuple[str, int]:
    if hp.startswith("["):
        host, _, rest = hp[1:].partition("]")
        port_s = rest.removeprefix(":")
    else:
        host, _, port_s = hp.rpartition(":")
    if not host or not port_s.isdigit():
        raise ParseError(f"无效的地址或端口：{hp}")
    port = int(port_s)
    if not 1 <= port <= 65535:
        raise ParseError(f"端口超出范围：{port}")
    return host, port


def host_for_uri(server: str) -> str:
    return f"[{server}]" if ":" in server else server


class StdParts(NamedTuple):
    userinfo: str
    server: str
    port: int
    query: dict[str, str]
    name: str


def split_standard(uri: str) -> StdParts:
    """拆分 scheme://userinfo@host:port/?query#name 形式的链接（userinfo / name 已解码）。"""
    _, sep, rest = uri.strip().partition("://")
    if not sep:
        raise ParseError("不是分享链接")
    rest, _, frag = rest.partition("#")
    rest, _, qs = rest.partition("?")
    userinfo, at, hostport = rest.rstrip("/").rpartition("@")
    if not at or not userinfo:
        raise ParseError("缺少认证信息（@ 之前的部分）")
    server, port = split_hostport(hostport)
    query = {k: v[-1] for k, v in parse_qs(qs, keep_blank_values=True).items()}
    return StdParts(unquote(userinfo), server, port, query, unquote(frag))


def build_uri(scheme: str, userinfo: str, server: str, port: int, params: dict[str, str], name: str) -> str:
    uri = f"{scheme}://{userinfo}@{host_for_uri(server)}:{port}"
    if params:
        uri += "?" + urlencode(params, quote_via=quote)
    return uri + "#" + quote(name, safe="")
