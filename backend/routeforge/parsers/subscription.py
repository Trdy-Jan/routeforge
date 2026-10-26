"""机场订阅内容解析：自动识别 Clash YAML / 明文分享链接 / Base64 分享链接列表。"""

import yaml

from routeforge.parsers.clash_proxy import from_clash, name_label
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import LineError, ParseOutcome, parse_many
from routeforge.parsers.uri._common import b64decode_loose


def parse_subscription(text: str) -> ParseOutcome:
    stripped = text.lstrip("\ufeff").strip()
    if not stripped:
        return ParseOutcome()
    clash = _try_clash_yaml(stripped)
    if clash is not None:
        return clash
    if "://" not in stripped:
        try:
            stripped = b64decode_loose(stripped)
        except ParseError:
            return ParseOutcome(errors=[LineError(line=stripped[:80], message="无法识别的订阅格式")])
        if "://" not in stripped:
            return ParseOutcome(errors=[LineError(line=stripped[:80], message="无法识别的订阅格式")])
    return parse_many(stripped)


def _try_clash_yaml(text: str) -> ParseOutcome | None:
    try:
        data = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
        return None
    outcome = ParseOutcome()
    for item in data["proxies"]:
        if not isinstance(item, dict):
            outcome.errors.append(LineError(line=_item_label(item), message="proxies 中的条目不是映射"))
            continue
        try:
            outcome.nodes.append(from_clash(item))
        except ParseError as e:
            outcome.errors.append(LineError(line=name_label(item), message=str(e)))
    return outcome


def _item_label(item) -> str:
    """非映射条目的错误行文本：标量直接显示，容器只显示类型名，避免对嵌套结构调用 str()。"""
    if isinstance(item, (str, int, float, bool)) or item is None:
        return str(item)[:80]
    return type(item).__name__
