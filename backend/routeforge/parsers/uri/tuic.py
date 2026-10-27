"""TUIC v5：tuic://uuid:password@host:port?congestion_control=bbr&alpn=h3&sni=..#name。"""

from urllib.parse import quote

from routeforge.ir.node import TuicNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import build_uri, split_standard, tls_from_query, tls_to_query


def parse(uri: str) -> TuicNode:
    p = split_standard(uri)
    uuid, sep, password = p.userinfo.partition(":")
    if not sep or not password:
        raise ParseError("tuic：缺少 uuid:password")
    return TuicNode(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        uuid=uuid,
        password=password,
        congestion_control=p.query.get("congestion_control") or None,
        tls=tls_from_query({**p.query, "security": "tls"}, default_on=True),
    )


def dump(node: TuicNode) -> str:
    params = tls_to_query(node.tls)
    params.pop("security")
    if node.congestion_control:
        params["congestion_control"] = node.congestion_control
    userinfo = f"{quote(node.uuid, safe='')}:{quote(node.password, safe='')}"
    return build_uri("tuic", userinfo, node.server, node.port, params, node.name)
