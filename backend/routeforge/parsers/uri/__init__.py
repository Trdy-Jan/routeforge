"""分享链接解析入口：按 scheme 分发到各协议模块。"""

from dataclasses import dataclass, field
from typing import Callable

from routeforge.ir.node import Node
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import hysteria2, mieru, ss, trojan, tuic, vless, vmess

_PARSERS: dict[str, Callable[[str], Node | list[Node]]] = {
    "ss": ss.parse,
    "trojan": trojan.parse,
    "vless": vless.parse,
    "vmess": vmess.parse,
    "hysteria2": hysteria2.parse,
    "hy2": hysteria2.parse,
    "tuic": tuic.parse,
    "mierus": mieru.parse,
    "mieru": mieru.parse_standard,
}

_DUMPERS: dict[str, Callable] = {
    "ss": ss.dump,
    "trojan": trojan.dump,
    "vless": vless.dump,
    "vmess": vmess.dump,
    "hysteria2": hysteria2.dump,
    "tuic": tuic.dump,
    "mieru": mieru.dump,
}


@dataclass
class LineError:
    line: str
    message: str


@dataclass
class ParseOutcome:
    nodes: list[Node] = field(default_factory=list)
    errors: list[LineError] = field(default_factory=list)


def parse_uri(uri: str) -> Node:
    nodes = parse_uri_nodes(uri)
    if len(nodes) != 1:
        raise ParseError("该链接包含多个节点")
    return nodes[0]


def parse_uri_nodes(uri: str) -> list[Node]:
    """解析一条分享链接；mierus:// 等链接可能产出多个节点。"""
    uri = uri.strip()
    scheme, sep, _ = uri.partition("://")
    if not sep:
        raise ParseError("不是分享链接")
    parser = _PARSERS.get(scheme.lower())
    if parser is None:
        raise ParseError(f"不支持的协议：{scheme}")
    uri = scheme.lower() + uri[len(scheme):]
    try:
        result = parser(uri)
        return result if isinstance(result, list) else [result]
    except ParseError:
        raise
    except (ValueError, KeyError, TypeError) as e:  # 包括 pydantic ValidationError
        raise ParseError(f"{scheme}：{e}") from e


def to_uri(node: Node) -> str:
    return _DUMPERS[node.type](node)


def parse_many(text: str) -> ParseOutcome:
    outcome = ParseOutcome()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            outcome.nodes.extend(parse_uri_nodes(line))
        except ParseError as e:
            outcome.errors.append(LineError(line=line, message=str(e)))
    return outcome
