"""Clash / Mihomo proxy 字典与 IR 互转。字段名参见 https://wiki.metacubex.one/config/proxies/"""

from pydantic import ValidationError

from routeforge.ir.node import (
    Hysteria2Node, Node, Reality, SSNode, TLSOptions, Transport, TrojanNode, TuicNode, VlessNode, VmessNode,
)
from routeforge.parsers.errors import ParseError, UnsupportedNode

_SNI_KEY = {"vmess": "servername", "vless": "servername", "trojan": "sni", "hysteria2": "sni", "tuic": "sni"}
_ALWAYS_TLS = {"trojan", "hysteria2", "tuic"}
_HAS_TRANSPORT = {"vmess", "vless", "trojan"}


def from_clash(d: dict) -> Node:
    try:
        return _from_clash(d)
    except ParseError:
        raise
    except (KeyError, TypeError, ValueError, ValidationError) as e:
        raise ParseError(f"节点「{name_label(d)}」无效：{e}") from e


def name_label(d: dict) -> str:
    """错误信息中使用的节点名：仅接受 str / int，避免对任意嵌套结构（如 YAML 别名炸弹）调用 str()。"""
    name = d.get("name")
    return str(name) if isinstance(name, (str, int)) else "?"


def _from_clash(d: dict) -> Node:
    t = d["type"]
    common = dict(name=str(d["name"]), server=str(d["server"]), port=int(d["port"]), udp=bool(d.get("udp", True)))
    match t:
        case "ss":
            plugin = d.get("plugin") or None
            if plugin not in (None, "obfs", "v2ray-plugin"):
                raise ParseError(f"ss：不支持的插件 {plugin}")
            return SSNode(**common, cipher=d["cipher"], password=str(d["password"]),
                          plugin=plugin, plugin_opts=dict(d.get("plugin-opts") or {}))
        case "vmess":
            return VmessNode(**common, uuid=d["uuid"], alter_id=int(d.get("alterId", 0)),
                             cipher=d.get("cipher", "auto"), tls=_tls_from(d, t), transport=_transport_from(d))
        case "vless":
            return VlessNode(**common, uuid=d["uuid"], flow=d.get("flow") or None,
                             tls=_tls_from(d, t), transport=_transport_from(d))
        case "trojan":
            return TrojanNode(**common, password=str(d["password"]), tls=_tls_from(d, t), transport=_transport_from(d))
        case "hysteria2":
            return Hysteria2Node(**common, password=str(d["password"]), obfs=d.get("obfs") or None,
                                 obfs_password=d.get("obfs-password") or None,
                                 up=_str_or_none(d.get("up")), down=_str_or_none(d.get("down")), tls=_tls_from(d, t))
        case "tuic":
            return TuicNode(**common, uuid=d["uuid"], password=str(d.get("password", "")),
                            congestion_control=d.get("congestion-controller") or None, tls=_tls_from(d, t))
        case _:
            raise ParseError(f"不支持的节点类型：{t}")


def _str_or_none(v) -> str | None:
    return None if v is None else str(v)


def _tls_from(d: dict, t: str) -> TLSOptions | None:
    if t not in _ALWAYS_TLS and not d.get("tls"):
        return None
    ro = d.get("reality-opts")
    reality = Reality(public_key=ro["public-key"], short_id=str(ro.get("short-id", ""))) if ro else None
    return TLSOptions(
        sni=d.get(_SNI_KEY[t]) or None,
        alpn=list(d.get("alpn") or []),
        insecure=bool(d.get("skip-cert-verify", False)),
        fingerprint=d.get("client-fingerprint") or None,
        reality=reality,
    )


def _transport_from(d: dict) -> Transport | None:
    net = d.get("network") or "tcp"
    match net:
        case "tcp":
            return None
        case "ws":
            o = d.get("ws-opts") or {}
            return Transport(
                type="httpupgrade" if o.get("v2ray-http-upgrade") else "ws",
                path=o.get("path") or None,
                host=_header(o.get("headers") or {}, "Host"),
            )
        case "grpc":
            o = d.get("grpc-opts") or {}
            return Transport(type="grpc", service_name=o.get("grpc-service-name") or None)
        case "h2":
            o = d.get("h2-opts") or {}
            hosts = o.get("host") or []
            if isinstance(hosts, str):
                hosts = [hosts]
            return Transport(type="h2", path=o.get("path") or None, host=hosts[0] if hosts else None)
        case _:
            raise ParseError(f"不支持的传输层：{net}")


def _header(headers: dict, key: str) -> str | None:
    """按 HTTP 惯例不区分大小写读取请求头。"""
    for k, v in headers.items():
        if isinstance(k, str) and k.lower() == key.lower() and v:
            return v
    return None


def to_clash(node: Node) -> dict:
    d: dict = {"name": node.name, "type": node.type, "server": node.server, "port": node.port, "udp": node.udp}
    match node:
        case SSNode():
            d["cipher"] = node.cipher
            d["password"] = node.password
            if node.plugin:
                d["plugin"] = node.plugin
                d["plugin-opts"] = dict(node.plugin_opts)
        case VmessNode():
            d.update({"uuid": node.uuid, "alterId": node.alter_id, "cipher": node.cipher})
        case VlessNode():
            d["uuid"] = node.uuid
            if node.flow:
                d["flow"] = node.flow
        case TrojanNode():
            d["password"] = node.password
        case Hysteria2Node():
            d["password"] = node.password
            for key, value in (("obfs", node.obfs), ("obfs-password", node.obfs_password),
                               ("up", node.up), ("down", node.down)):
                if value:
                    d[key] = value
        case TuicNode():
            d["uuid"] = node.uuid
            d["password"] = node.password
            if node.congestion_control:
                d["congestion-controller"] = node.congestion_control
    _tls_to(d, node)
    _transport_to(d, node)
    if node.via:
        d["dialer-proxy"] = node.via
    return d


def _tls_to(d: dict, node: Node) -> None:
    tls = node.tls
    if node.type in ("vmess", "vless"):
        d["tls"] = tls is not None
    if tls is None:
        return
    if node.type == "ss":
        raise UnsupportedNode("ss 节点不支持 TLS 字段")
    if tls.sni:
        d[_SNI_KEY[node.type]] = tls.sni
    if tls.alpn:
        d["alpn"] = list(tls.alpn)
    if tls.insecure:
        d["skip-cert-verify"] = True
    if tls.fingerprint:
        d["client-fingerprint"] = tls.fingerprint
    if tls.reality:
        if node.type != "vless":
            raise UnsupportedNode(f"{node.type} 不支持 Reality")
        d["reality-opts"] = {"public-key": tls.reality.public_key, "short-id": tls.reality.short_id}


def _transport_to(d: dict, node: Node) -> None:
    tr = node.transport
    if tr is None:
        return
    if node.type not in _HAS_TRANSPORT:
        raise UnsupportedNode(f"{node.type} 不支持传输层 {tr.type}")
    match tr.type:
        case "ws" | "httpupgrade":
            d["network"] = "ws"
            opts: dict = {}
            if tr.path:
                opts["path"] = tr.path
            if tr.host:
                opts["headers"] = {"Host": tr.host}
            if tr.type == "httpupgrade":
                opts["v2ray-http-upgrade"] = True
            d["ws-opts"] = opts
        case "grpc":
            d["network"] = "grpc"
            d["grpc-opts"] = {"grpc-service-name": tr.service_name or ""}
        case "h2":
            d["network"] = "h2"
            opts = {"host": [tr.host]} if tr.host else {}
            if tr.path:
                opts["path"] = tr.path
            d["h2-opts"] = opts
