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


@dataclass(frozen=True)
class Issue:
    """一条错误的结构化信息：section 对应前端编辑器的标签页，hint 是修复建议。"""

    section: str  # "groups" | "rules" | "providers" | "chains"
    message: str
    hint: str


@dataclass
class ResolveResult:
    profile: ResolvedProfile | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

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
        self.issues: list[Issue] = []
        self.warnings: list[str] = []

    def _error(self, section: str, message: str, hint: str) -> None:
        self.errors.append(message)
        self.issues.append(Issue(section, message, hint))

    def run(self) -> ResolveResult:
        group_names = self._check_group_names()
        expanded = {g.name: self._expand(g) for g in self.profile.groups}
        chains = self._resolve_chains(group_names)
        used, chains = self._effective(expanded, chains)
        names = self._assign_names(used, group_names)
        self._check_group_refs(expanded, group_names)
        self._check_cycles(expanded, chains)
        self._check_rules(group_names)
        if self.errors:
            return ResolveResult(None, self.errors, self.warnings, self.issues)
        return ResolveResult(self._build(expanded, chains, used, names), [], self.warnings)

    def _check_group_names(self) -> set[str]:
        names: set[str] = set()
        for g in self.profile.groups:
            if g.name in BUILTIN_TARGETS:
                self._error("groups", f"分组名不能使用保留名「{g.name}」", "DIRECT、REJECT 等是内置目标，请给这个分组换个名字")
            elif g.name in names:
                self._error("groups", f"分组名重复：「{g.name}」", "重命名或删除其中一个同名分组")
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
            self._error("groups", f"分组「{group_name}」的过滤器正则无效：{e}", "打开该分组，修正过滤器的正则表达式（常见原因：括号未闭合、多余的反斜杠）")
            return []

    def _resolve_chains(self, group_names: set[str]) -> dict[int, Entry]:
        chains: dict[int, Entry] = {}
        seen: set[int] = set()
        for c in self.profile.chains:
            ln = self.by_id.get(c.node.node_id)
            if ln is None or not ln.enabled:
                self.warnings.append(f"链式代理的落地节点 #{c.node.node_id} 不存在或已禁用，已忽略")
                continue
            if ln.id in seen:
                self._error("chains", f"落地节点「{ln.node.name}」配置了多条链式代理", "同一个落地节点只能保留一条链式代理")
                continue
            seen.add(ln.id)
            match c.via:
                case GroupRef(name=name):
                    if name not in group_names:
                        self._error("chains", f"链式代理「{ln.node.name}」的前置分组「{name}」不存在", "改选一个存在的前置分组，或在「分组」中新建该分组")
                        continue
                    chains[ln.id] = ("group", name)
                case NodeRef(node_id=vid):
                    v = self.by_id.get(vid)
                    if v is None or not v.enabled:
                        self._error("chains", f"链式代理「{ln.node.name}」的前置节点 #{vid} 不存在或已禁用", "改选前置节点，或到「节点」页面重新启用它")
                        continue
                    chains[ln.id] = ("node", vid)
        return chains

    def _effective(
        self, expanded: dict[str, list[Entry]], chains: dict[int, Entry]
    ) -> tuple[list[int], dict[int, Entry]]:
        """不动点：从分组可达的节点出发，落地节点已可达的链式代理生效，其前置节点随之可达。

        返回 (used, 生效的链式代理)；used 先按分组顺序，再按发现顺序追加仅作前置的节点。
        """
        used = list(dict.fromkeys(v for entries in expanded.values() for kind, v in entries if kind == "node"))
        reached = set(used)
        effective: dict[int, Entry] = {}
        changed = True
        while changed:
            changed = False
            for nid, target in chains.items():
                if nid in effective or nid not in reached:
                    continue
                effective[nid] = target
                changed = True
                kind, value = target
                if kind == "node" and value not in reached:
                    reached.add(value)
                    used.append(value)
        for nid in chains:
            if nid not in effective:
                self.warnings.append(f"落地节点「{self.by_id[nid].node.name}」未出现在任何分组中，链式代理不会生效")
        return used, {nid: t for nid, t in chains.items() if nid in effective}

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
                    self._error("groups", f"分组「{g}」引用了不存在的分组「{value}」", f"从「{g}」中移除「{value}」，或新建名为「{value}」的分组")

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
                    self._error(
                        "groups",
                        "检测到循环引用：" + " → ".join(self._label(x) for x in cycle),
                        "分组之间（含链式代理）不能互相包含，移除环上任意一个引用即可",
                    )
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
            self._error(
                "rules",
                "规则必须以且仅以一条 MATCH 规则结尾",
                f"当前有 {len(matches)} 条 MATCH 规则：保留一条并移到最后，或套用「漏网之鱼」模板",
            )
        provider_names = [p.name for p in self.profile.rule_providers]
        if len(provider_names) != len(set(provider_names)):
            self._error("providers", "规则集名称重复", "重命名或删除重名的规则集")
        for p in self.profile.rule_providers:
            if not p.name or any(bad in p.name for bad in ("/", "\\", ",", "..")):
                self._error("providers", f"规则集名称「{p.name}」无效：不能为空，也不能包含 / \\ , ..", "修改这个规则集的名称")
            if p.format == "mrs" and p.behavior == "classical":
                self._error("providers", f"规则集「{p.name}」：mrs 格式只支持 domain / ipcidr", "把格式改为 yaml / text，或把类型改为 domain / ipcidr")
        for r in rules:
            if r.type != "MATCH" and not r.value:
                self._error("rules", f"规则「{r.type}」缺少值", "为这条规则填写匹配值，或删除它")
            if "," in r.value or "," in r.target:
                self._error("rules", f"规则「{r.type},{r.value}」的值或目标「{r.target}」不能包含逗号「,」", "每条规则只能写一个值，多个值请拆成多条规则")
            if r.target not in group_names and r.target not in BUILTIN_TARGETS:
                self._error(
                    "rules",
                    f"规则「{r.type},{r.value}」的目标「{r.target}」不存在",
                    f"把目标改为已有分组，或在「分组」中新建名为「{r.target}」的分组",
                )
            if r.type == "RULE-SET" and r.value not in provider_names:
                self._error("rules", f"规则引用的规则集「{r.value}」不存在", f"在「规则集」中添加名为「{r.value}」的规则集，或删除这条 RULE-SET 规则")

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
