"""手动导入的输入识别：在订阅格式之外，额外接受单个 Clash 节点映射和裸节点列表。"""

import yaml

from routeforge.parsers.subscription import clash_items, parse_subscription
from routeforge.parsers.uri import LineError, ParseOutcome


def parse_manual_input(text: str) -> ParseOutcome:
    stripped = text.lstrip("﻿").strip()
    try:
        data = yaml.safe_load(stripped)
    except (yaml.YAMLError, RecursionError):
        data = None
    if _is_proxy(data):
        return clash_items([data])
    if isinstance(data, list) and any(_is_proxy(item) for item in data):
        # 只要有一项像节点就按节点列表处理，坏条目逐条进错误列表
        return clash_items(data)
    outcome = parse_subscription(stripped)
    if not outcome.nodes and not outcome.errors:
        outcome.errors.append(LineError(line=stripped[:80], message="没有识别到任何节点"))
    return outcome


def _is_proxy(item) -> bool:
    return isinstance(item, dict) and "type" in item
