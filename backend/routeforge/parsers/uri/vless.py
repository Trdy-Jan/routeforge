"""VLESS：vless://uuid@host:port?security=tls|reality|none&type=..&flow=..#name。"""

from urllib.parse import quote

from routeforge.ir.node import VlessNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import (
    build_uri,
    split_standard,
    tls_from_query,
    tls_to_query,
    transport_from_query,
    transport_to_query,
)


def parse(uri: str) -> VlessNode:
    p = split_standard(uri)
    encryption = p.query.get("encryption") or ""
    if encryption not in ("none", ""):
        raise ParseError(f"vless：不支持的 encryption：{encryption}")
    return VlessNode(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        uuid=p.userinfo,
        flow=p.query.get("flow") or None,
        tls=tls_from_query(p.query, default_on=False),
        transport=transport_from_query(p.query),
    )


def dump(node: VlessNode) -> str:
    params = {"encryption": "none", **tls_to_query(node.tls), **transport_to_query(node.transport)}
    if node.flow:
        params["flow"] = node.flow
    return build_uri("vless", quote(node.uuid, safe=""), node.server, node.port, params, node.name)
