"""Trojan：trojan://password@host:port?sni=..&type=ws..#name（默认启用 TLS）。"""

from urllib.parse import quote

from routeforge.ir.node import TrojanNode
from routeforge.parsers.uri._common import (
    build_uri,
    split_standard,
    tls_from_query,
    tls_to_query,
    transport_from_query,
    transport_to_query,
)


def parse(uri: str) -> TrojanNode:
    p = split_standard(uri)
    return TrojanNode(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        password=p.userinfo,
        tls=tls_from_query(p.query, default_on=True),
        transport=transport_from_query(p.query),
    )


def dump(node: TrojanNode) -> str:
    params = {**tls_to_query(node.tls), **transport_to_query(node.transport)}
    if params.get("security") == "tls":
        del params["security"]
    return build_uri("trojan", quote(node.password, safe=""), node.server, node.port, params, node.name)
