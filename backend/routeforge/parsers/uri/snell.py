"""Snell：snell://psk@host:port?version=4&udp=true&reuse=true&obfs=http&obfs-host=..#name。"""

from urllib.parse import quote

from routeforge.ir.node import SnellNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import build_uri, split_standard

_BOOL_MAP = {"1": True, "true": True, "0": False, "false": False}


def _parse_bool(raw: str | None, field: str) -> bool | None:
    if raw is None or raw == "":
        return None
    val = _BOOL_MAP.get(raw.strip().lower())
    if val is None:
        raise ParseError(f"snell：无效的 {field}：{raw}")
    return val


def parse(uri: str) -> SnellNode:
    p = split_standard(uri)
    q = p.query
    udp = _parse_bool(q.get("udp"), "udp")
    reuse = _parse_bool(q.get("reuse"), "reuse")
    obfs_opts: dict = {}
    if q.get("obfs"):
        obfs_opts["mode"] = q["obfs"]
        host = q.get("obfs-host") or q.get("obfs_host")
        if host:
            obfs_opts["host"] = host
    return SnellNode(
        name=p.name or f"{p.server}:{p.port}",
        server=p.server,
        port=p.port,
        psk=p.userinfo,
        version=q.get("version") or None,
        udp=True if udp is None else udp,
        reuse=reuse,
        obfs_opts=obfs_opts,
    )


def dump(node: SnellNode) -> str:
    params: dict[str, str] = {}
    if node.version is not None:
        params["version"] = str(node.version)
    params["udp"] = "true" if node.udp else "false"
    if node.reuse is not None:
        params["reuse"] = "true" if node.reuse else "false"
    if node.obfs_opts.get("mode"):
        params["obfs"] = str(node.obfs_opts["mode"])
        if node.obfs_opts.get("host"):
            params["obfs-host"] = str(node.obfs_opts["host"])
    return build_uri("snell", quote(node.psk, safe=""), node.server, node.port, params, node.name)
