"""resolver 输出、渲染器输入：所有引用已展开为最终名称。"""

from pydantic import BaseModel

from routeforge.ir.node import Node
from routeforge.ir.profile import GroupType, Rule, RuleProvider


class ResolvedGroup(BaseModel):
    name: str
    type: GroupType
    members: list[str]  # 节点最终名称 / 分组名 / DIRECT / REJECT
    url: str
    interval: int
    tolerance: int


class ResolvedProfile(BaseModel):
    name: str
    proxies: list[Node]
    groups: list[ResolvedGroup]
    rules: list[Rule]
    rule_providers: list[RuleProvider]
    source_ids: list[int]  # 本方案实际用到的节点源，升序
