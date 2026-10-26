"""分享链接解析入口：按 scheme 分发到各协议模块。"""

from dataclasses import dataclass, field
from typing import Callable

from routeforge.ir.node import Node
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import ss

_PARSERS: dict[str, Callable[[str], Node]] = {
    "ss": ss.parse,
}

_DUMPERS: dict[str, Callable] = {
    "ss": ss.dump,
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
    uri = uri.strip()
    scheme, sep, _ = uri.partition("://")
    if not sep:
        raise ParseError("不是分享链接")
    parser = _PARSERS.get(scheme.lower())
    if parser is None:
        raise ParseError(f"不支持的协议：{scheme}")
    try:
        return parser(uri)
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
            outcome.nodes.append(parse_uri(line))
        except ParseError as e:
            outcome.errors.append(LineError(line=line, message=str(e)))
    return outcome
