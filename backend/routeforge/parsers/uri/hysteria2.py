"""Hysteria2：hysteria2://auth@host:port?sni=..&insecure=1&obfs=salamander&obfs-password=..#name（hy2:// 同义）。"""

from urllib.parse import quote

from routeforge.ir.node import Hysteria2Node
from routeforge.parsers.uri._common import build_uri, split_standard, tls_from_query, tls_to_query


def parse(uri: str) -> Hysteria2Node:
    p = split_standard(uri)
    q = p.query
    return Hysteria2Node(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        password=p.userinfo,
        obfs=q.get("obfs") or None,
        obfs_password=q.get("obfs-password") or None,
        tls=tls_from_query({**q, "security": "tls"}, default_on=True),
    )


def dump(node: Hysteria2Node) -> str:
    params = tls_to_query(node.tls)
    params.pop("security")
    if node.obfs:
        params["obfs"] = node.obfs
    if node.obfs_password:
        params["obfs-password"] = node.obfs_password
    return build_uri("hysteria2", quote(node.password, safe=""), node.server, node.port, params, node.name)
