"""配置方案（Profile）中间模型。"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

BUILTIN_TARGETS: frozenset[str] = frozenset({"DIRECT", "REJECT"})

GroupType = Literal["select", "url-test", "fallback", "load-balance"]
RuleType = Literal[
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6",
    "GEOSITE", "GEOIP", "PROCESS-NAME", "RULE-SET", "MATCH",
]


class NodeRef(BaseModel):
    kind: Literal["node"] = "node"
    node_id: int


class GroupRef(BaseModel):
    kind: Literal["group"] = "group"
    name: str


class Builtin(BaseModel):
    kind: Literal["builtin"] = "builtin"
    name: Literal["DIRECT", "REJECT"]


class Filter(BaseModel):
    """按节点源与名称正则动态匹配节点；source_id 为 None 表示所有源。"""

    kind: Literal["filter"] = "filter"
    source_id: int | None = None
    name_regex: str = ""
    exclude_regex: str | None = None


Member = Annotated[Union[NodeRef, GroupRef, Builtin, Filter], Field(discriminator="kind")]


class ProxyGroup(BaseModel):
    name: str
    type: GroupType = "select"
    members: list[Member] = []
    url: str = "https://www.gstatic.com/generate_204"
    interval: int = 300
    tolerance: int = 50


class Rule(BaseModel):
    type: RuleType
    value: str = ""
    target: str
    no_resolve: bool = False


class RuleProvider(BaseModel):
    name: str
    behavior: Literal["domain", "ipcidr", "classical"]
    format: Literal["yaml", "text", "mrs"] = "yaml"
    url: str
    interval: int = 86400


class Chain(BaseModel):
    """落地节点 node 在本方案中经由 via（分组或节点）出站。"""

    node: NodeRef
    via: Annotated[Union[GroupRef, NodeRef], Field(discriminator="kind")]


class Profile(BaseModel):
    name: str
    groups: list[ProxyGroup] = []
    rules: list[Rule] = []
    rule_providers: list[RuleProvider] = []
    chains: list[Chain] = []
