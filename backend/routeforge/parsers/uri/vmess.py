"""VMess：vmess://base64(json)，字段遵循 v2rayN 约定（grpc 的 serviceName 放在 path 字段）。"""

import json

from routeforge.ir.node import VmessNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import b64decode_loose, b64encode_text, tls_from_query, transport_from_query


def parse(uri: str) -> VmessNode:
    raw = b64decode_loose(uri.strip().removeprefix("vmess://"))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ParseError(f"vmess：JSON 无效：{e}") from e
    if not isinstance(data, dict):
        raise ParseError("vmess：内容不是 JSON 对象")
    for key in ("add", "id"):
        if data.get(key) in (None, ""):
            raise ParseError(f"vmess：缺少或无效字段 '{key}'")
    try:
        server = str(data["add"])
        port = int(data["port"])
        uuid = str(data["id"])
    except (KeyError, ValueError) as e:
        raise ParseError(f"vmess：缺少或无效字段 {e}") from e
    net = str(data.get("net") or "tcp")
    tq = {"type": net, "path": str(data.get("path") or ""), "host": str(data.get("host") or "")}
    if net == "grpc":
        tq["serviceName"] = tq.pop("path")
    tls_q = {
        "security": "tls" if data.get("tls") == "tls" else "none",
        "sni": str(data.get("sni") or ""),
        "alpn": str(data.get("alpn") or ""),
        "fp": str(data.get("fp") or ""),
    }
    return VmessNode(
        name=str(data.get("ps") or f"{server}:{port}"),
        server=server,
        port=port,
        uuid=uuid,
        alter_id=int(data.get("aid") or 0),
        cipher=str(data.get("scy") or "auto"),
        tls=tls_from_query(tls_q, default_on=False),
        transport=transport_from_query(tq),
    )


def dump(node: VmessNode) -> str:
    d = {
        "v": "2", "ps": node.name, "add": node.server, "port": str(node.port), "id": node.uuid,
        "aid": str(node.alter_id), "scy": node.cipher, "net": "tcp", "type": "none",
        "host": "", "path": "", "tls": "",
    }
    tr = node.transport
    if tr:
        d["net"] = tr.type
        d["host"] = tr.host or ""
        d["path"] = (tr.service_name if tr.type == "grpc" else tr.path) or ""
    if node.tls:
        d["tls"] = "tls"
        if node.tls.sni:
            d["sni"] = node.tls.sni
        if node.tls.alpn:
            d["alpn"] = ",".join(node.tls.alpn)
        if node.tls.fingerprint:
            d["fp"] = node.tls.fingerprint
    return "vmess://" + b64encode_text(json.dumps(d, ensure_ascii=False))
