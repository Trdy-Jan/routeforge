"""Mieru 简易分享链接：mierus://user:pass@host?profile=..&port=..&protocol=..[&port=..&protocol=..]#name。

port / protocol 可重复出现，按顺序一一配对，每对生成一个节点；port 可以是区间（如 9998-9999）。
profile、mtu 在 mihomo 中没有对应字段，解析时丢弃。
"""

from urllib.parse import parse_qs, quote, unquote, urlencode

from routeforge.ir.node import MieruNode, Node
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import host_for_uri


def parse(uri: str) -> list[MieruNode]:
    _, _, rest = uri.strip().partition("://")
    rest, _, frag = rest.partition("#")
    rest, _, qs = rest.partition("?")
    userinfo, at, host = rest.rstrip("/").rpartition("@")
    if not at or not userinfo:
        raise ParseError("缺少认证信息（@ 之前的部分）")
    user, sep, password = userinfo.partition(":")
    if not sep or not user or not password:
        raise ParseError("mierus：缺少 用户名:密码")
    if host.startswith("["):
        host, _, after = host[1:].partition("]")
    else:
        after = ":" if ":" in host else ""
    if after:
        raise ParseError("mierus：服务器地址后不能带端口，端口请写在 port= 参数里")
    if not host:
        raise ParseError("mierus：缺少服务器地址")

    query = parse_qs(qs, keep_blank_values=True)
    ports, protocols = query.get("port", []), query.get("protocol", [])
    if not ports:
        raise ParseError("mierus：缺少 port")
    if len(ports) != len(protocols):
        raise ParseError("mierus：port 与 protocol 的数量不一致")

    def one(key: str) -> str | None:
        return (query.get(key) or [None])[-1] or None

    name = unquote(frag)
    nodes = []
    for port_s, protocol in zip(ports, protocols):
        if "-" in port_s:
            port, port_range = 1, port_s
        elif port_s.isdigit():
            port, port_range = int(port_s), None
        else:
            raise ParseError(f"mierus：无效的端口：{port_s}")
        suffix = f"{port_s}-{protocol.upper()}"
        if not name:
            node_name = f"mieru-{host}-{suffix}"
        else:
            node_name = name if len(ports) == 1 else f"{name}-{suffix}"
        nodes.append(MieruNode(
            name=node_name, server=host, port=port, port_range=port_range, protocol=protocol,
            username=unquote(user), password=unquote(password),
            multiplexing=one("multiplexing"), handshake_mode=one("handshake-mode"),
            traffic_pattern=one("traffic-pattern"),
        ))
    return nodes


def parse_standard(uri: str) -> list[Node]:
    raise ParseError("暂不支持 mieru:// 标准链接，请使用 mierus:// 简易链接或 Clash YAML")


def dump(node: MieruNode) -> str:
    params = {"profile": "default", "port": node.port_range or str(node.port), "protocol": node.protocol}
    for key, value in (("multiplexing", node.multiplexing), ("handshake-mode", node.handshake_mode),
                       ("traffic-pattern", node.traffic_pattern)):
        if value:
            params[key] = value
    userinfo = f"{quote(node.username, safe='')}:{quote(node.password, safe='')}"
    uri = f"mierus://{userinfo}@{host_for_uri(node.server)}?{urlencode(params, quote_via=quote)}"
    return uri + "#" + quote(node.name, safe="")
