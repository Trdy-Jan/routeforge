"""手动导入的输入识别：在订阅格式之外，额外接受单个 Clash 节点映射和裸节点列表。"""

import yaml

from routeforge.parsers.subscription import clash_items, parse_subscription
from routeforge.parsers.uri import ParseOutcome


def parse_manual_input(text: str) -> ParseOutcome:
    stripped = text.lstrip("﻿").strip()
    try:
        data = yaml.safe_load(stripped)
    except (yaml.YAMLError, RecursionError):
        data = None
    if _is_proxy(data):
        return clash_items([data])
    if isinstance(data, list) and data and all(_is_proxy(item) for item in data):
        return clash_items(data)
    return parse_subscription(stripped)


def _is_proxy(item) -> bool:
    return isinstance(item, dict) and "type" in item
