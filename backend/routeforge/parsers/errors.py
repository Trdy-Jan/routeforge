class ParseError(ValueError):
    """输入（分享链接 / 订阅 / Clash proxy）无法解析为 IR。"""


class UnsupportedNode(Exception):
    """IR 节点包含目标格式无法表达的内容。"""
