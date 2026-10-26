"""分享链接解析的通用工具。"""

import base64
from typing import NamedTuple
from urllib.parse import parse_qs, quote, unquote, urlencode

from routeforge.parsers.errors import ParseError
from routeforge.ir.node import Reality, TLSOptions, Transport


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


_TRUTHY = {"1", "true", "True"}


def tls_from_query(q: dict[str, str], *, default_on: bool) -> TLSOptions | None:
    security = q.get("security") or ("tls" if default_on else "none")
    if security == "none":
        return None
    if security not in ("tls", "reality", "xtls"):
        raise ParseError(f"不支持的 security：{security}")
    reality = None
    if security == "reality":
        if not q.get("pbk"):
            raise ParseError("reality 缺少 pbk（公钥）")
        reality = Reality(public_key=q["pbk"], short_id=q.get("sid", ""))
    insecure = (q.get("allowInsecure") or q.get("insecure") or q.get("allow_insecure") or "") in _TRUTHY
    return TLSOptions(
        sni=q.get("sni") or q.get("peer") or None,
        alpn=[a for a in q.get("alpn", "").split(",") if a],
        insecure=insecure,
        fingerprint=q.get("fp") or None,
        reality=reality,
    )


def tls_to_query(tls: TLSOptions | None) -> dict[str, str]:
    if tls is None:
        return {"security": "none"}
    q = {"security": "reality" if tls.reality else "tls"}
    if tls.sni:
        q["sni"] = tls.sni
    if tls.alpn:
        q["alpn"] = ",".join(tls.alpn)
    if tls.insecure:
        q["allowInsecure"] = "1"
    if tls.fingerprint:
        q["fp"] = tls.fingerprint
    if tls.reality:
        q["pbk"] = tls.reality.public_key
        if tls.reality.short_id:
            q["sid"] = tls.reality.short_id
    return q


def transport_from_query(q: dict[str, str]) -> Transport | None:
    kind = q.get("type") or "tcp"
    if kind == "tcp":
        return None
    if kind == "http":  # xray 分享链接中 http 即 h2
        kind = "h2"
    if kind not in ("ws", "grpc", "h2", "httpupgrade"):
        raise ParseError(f"不支持的传输层：{kind}")
    return Transport(
        type=kind,
        path=q.get("path") or None,
        host=q.get("host") or None,
        service_name=q.get("serviceName") or None,
    )


def transport_to_query(tr: Transport | None) -> dict[str, str]:
    if tr is None:
        return {}
    q = {"type": tr.type}
    if tr.path:
        q["path"] = tr.path
    if tr.host:
        q["host"] = tr.host
    if tr.service_name:
        q["serviceName"] = tr.service_name
    return q
