"""Profile + 节点库 → ResolvedProfile：展开过滤器、校验引用、检测环、处理重名。"""

import re
from dataclasses import dataclass, field

from routeforge.ir.node import Node
from routeforge.ir.profile import BUILTIN_TARGETS, Builtin, Filter, GroupRef, NodeRef, Profile, ProxyGroup
from routeforge.ir.resolved import ResolvedGroup, ResolvedProfile

# 展开后的成员：("node", 节点 id) | ("group", 分组名) | ("builtin", "DIRECT"/"REJECT")
Entry = tuple[str, int | str]


@dataclass(frozen=True)
class LibraryNode:
    id: int
    source_id: int
    enabled: bool
    node: Node


@dataclass
class ResolveResult:
    profile: ResolvedProfile | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.profile is not None


def resolve(profile: Profile, library: list[LibraryNode]) -> ResolveResult:
    return _Resolver(profile, library).run()


def match_filter(library: list[LibraryNode], f: Filter) -> list[LibraryNode]:
    """返回过滤器匹配的已启用节点（保持节点库顺序）；正则无效时抛 re.error。"""
    try:
        include = re.compile(f.name_regex)
        exclude = re.compile(f.exclude_regex) if f.exclude_regex else None
    except (OverflowError, RecursionError) as e:
        raise re.error(f"正则过于复杂：{e}") from e
    return [
        ln for ln in library
        if ln.enabled
        and (f.source_id is None or ln.source_id == f.source_id)
        and include.search(ln.node.name)
        and not (exclude and exclude.search(ln.node.name))
    ]


class _Resolver:
    def __init__(self, profile: Profile, library: list[LibraryNode]):
        self.profile = profile
        self.library = library
        self.by_id = {n.id: n for n in library}
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def run(self) -> ResolveResult:
        group_names = self._check_group_names()
        expanded = {g.name: self._expand(g) for g in self.profile.groups}
        chains = self._resolve_chains(group_names)
        used = self._used_nodes(expanded, chains)
        names = self._assign_names(used, group_names)
        self._check_group_refs(expanded, group_names)
        self._check_cycles(expanded, chains)
        self._check_rules(group_names)
        if self.errors:
            return ResolveResult(None, self.errors, self.warnings)
        return ResolveResult(self._build(expanded, chains, used, names), [], self.warnings)

    def _check_group_names(self) -> set[str]:
        names: set[str] = set()
        for g in self.profile.groups:
            if g.name in BUILTIN_TARGETS:
                self.errors.append(f"分组名不能使用保留名「{g.name}」")
            elif g.name in names:
                self.errors.append(f"分组名重复：「{g.name}」")
            names.add(g.name)
        return names

    def _expand(self, g: ProxyGroup) -> list[Entry]:
        out: list[Entry] = []
        for m in g.members:
            match m:
                case NodeRef(node_id=nid):
                    ln = self.by_id.get(nid)
                    if ln is None or not ln.enabled:
                        self.warnings.append(f"分组「{g.name}」引用的节点 #{nid} 不存在或已禁用，已忽略")
                        continue
                    out.append(("node", nid))
                case GroupRef(name=name):
                    out.append(("group", name))
                case Builtin(name=name):
                    out.append(("builtin", name))
                case Filter():
                    out.extend(("node", ln.id) for ln in self._match_filter(g.name, m))
        return list(dict.fromkeys(out))

    def _match_filter(self, group_name: str, f: Filter) -> list[LibraryNode]:
        try:
            return match_filter(self.library, f)
        except re.error as e:
            self.errors.append(f"分组「{group_name}」的过滤器正则无效：{e}")
            return []

    def _resolve_chains(self, group_names: set[str]) -> dict[int, Entry]:
        chains: dict[int, Entry] = {}
        for c in self.profile.chains:
            ln = self.by_id.get(c.node.node_id)
            if ln is None or not ln.enabled:
                self.warnings.append(f"链式代理的落地节点 #{c.node.node_id} 不存在或已禁用，已忽略")
                continue
            match c.via:
                case GroupRef(name=name):
                    if name not in group_names:
                        self.errors.append(f"链式代理「{ln.node.name}」的前置分组「{name}」不存在")
                        continue
                    chains[ln.id] = ("group", name)
                case NodeRef(node_id=vid):
                    v = self.by_id.get(vid)
                    if v is None or not v.enabled:
                        self.errors.append(f"链式代理「{ln.node.name}」的前置节点 #{vid} 不存在或已禁用")
                        continue
                    chains[ln.id] = ("node", vid)
        return chains

    def _used_nodes(self, expanded: dict[str, list[Entry]], chains: dict[int, Entry]) -> list[int]:
        used = [v for entries in expanded.values() for kind, v in entries if kind == "node"]
        in_groups = set(used)
        for nid, (kind, value) in chains.items():
            if nid not in in_groups:
                self.warnings.append(f"落地节点「{self.by_id[nid].node.name}」未出现在任何分组中，链式代理不会生效")
                continue
            if kind == "node":
                used.append(value)
        return list(dict.fromkeys(used))

    def _assign_names(self, used: list[int], group_names: set[str]) -> dict[int, str]:
        taken = set(group_names) | BUILTIN_TARGETS
        names: dict[int, str] = {}
        for nid in used:
            base = self.by_id[nid].node.name
            name, i = base, 2
            while name in taken:
                name = f"{base} {i}"
                i += 1
            taken.add(name)
            names[nid] = name
        return names

    def _check_group_refs(self, expanded: dict[str, list[Entry]], group_names: set[str]) -> None:
        for g, entries in expanded.items():
            for kind, value in entries:
                if kind == "group" and value not in group_names:
                    self.errors.append(f"分组「{g}」引用了不存在的分组「{value}」")

    def _check_cycles(self, expanded: dict[str, list[Entry]], chains: dict[int, Entry]) -> None:
        graph: dict[Entry, list[Entry]] = {}
        for g, entries in expanded.items():
            graph[("group", g)] = [e for e in entries if e[0] == "node" or (e[0] == "group" and e[1] in expanded)]
        for nid, target in chains.items():
            graph[("node", nid)] = [target]

        state: dict[Entry, int] = {}  # 1 = 访问中, 2 = 已完成

        def visit(v: Entry, stack: list[Entry]) -> None:
            state[v] = 1
            stack.append(v)
            for w in graph.get(v, []):
                if state.get(w) == 1:
                    cycle = stack[stack.index(w):] + [w]
                    self.errors.append("检测到循环引用：" + " → ".join(self._label(x) for x in cycle))
                elif w not in state:
                    visit(w, stack)
            stack.pop()
            state[v] = 2

        for v in graph:
            if v not in state:
                visit(v, [])

    def _label(self, e: Entry) -> str:
        kind, value = e
        return f"分组「{value}」" if kind == "group" else f"节点「{self.by_id[value].node.name}」"

    def _check_rules(self, group_names: set[str]) -> None:
        rules = self.profile.rules
        matches = [i for i, r in enumerate(rules) if r.type == "MATCH"]
        if len(matches) != 1 or matches[0] != len(rules) - 1:
            self.errors.append("规则必须以且仅以一条 MATCH 规则结尾")
        provider_names = [p.name for p in self.profile.rule_providers]
        if len(provider_names) != len(set(provider_names)):
            self.errors.append("规则集名称重复")
        for r in rules:
            if r.target not in group_names and r.target not in BUILTIN_TARGETS:
                self.errors.append(f"规则「{r.type},{r.value}」的目标「{r.target}」不存在")
            if r.type == "RULE-SET" and r.value not in provider_names:
                self.errors.append(f"规则引用的规则集「{r.value}」不存在")

    def _build(self, expanded, chains, used, names) -> ResolvedProfile:
        proxies: list[Node] = []
        for nid in used:
            via = None
            if nid in chains:
                kind, value = chains[nid]
                via = value if kind == "group" else names[value]
            proxies.append(self.by_id[nid].node.model_copy(update={"name": names[nid], "via": via}))
        groups: list[ResolvedGroup] = []
        for g in self.profile.groups:
            members = [names[v] if kind == "node" else v for kind, v in expanded[g.name]]
            if not members:
                self.warnings.append(f"分组「{g.name}」没有可用成员，已自动加入 DIRECT")
                members = ["DIRECT"]
            groups.append(ResolvedGroup(name=g.name, type=g.type, members=members,
                                        url=g.url, interval=g.interval, tolerance=g.tolerance))
        return ResolvedProfile(
            name=self.profile.name,
            proxies=proxies,
            groups=groups,
            rules=list(self.profile.rules),
            rule_providers=list(self.profile.rule_providers),
            source_ids=sorted({self.by_id[n].source_id for n in used}),
        )
