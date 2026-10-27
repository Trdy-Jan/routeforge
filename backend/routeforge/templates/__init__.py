"""内置分流模板：数据在同目录 *.yaml，套用时复制进方案。"""

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from routeforge.ir.profile import GroupRef, Profile, ProxyGroup, Rule, RuleProvider

PLACEHOLDER_GROUP = "节点选择"
_DIR = Path(__file__).parent


class Template(BaseModel):
    id: str
    name: str
    description: str
    groups: list[ProxyGroup] = []
    rules: list[Rule] = []
    rule_providers: list[RuleProvider] = []


@cache
def load_templates() -> dict[str, Template]:
    templates: dict[str, Template] = {}
    for path in sorted(_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        templates[path.stem] = Template(id=path.stem, **data)
    return templates


def apply_template(profile: Profile, template: Template) -> tuple[Profile, list[str]]:
    notes: list[str] = []

    groups = list(profile.groups)
    group_names = {g.name for g in groups}
    needs_placeholder = any(
        isinstance(m, GroupRef) and m.name == PLACEHOLDER_GROUP for g in template.groups for m in g.members
    )
    if needs_placeholder and PLACEHOLDER_GROUP not in group_names:
        groups.insert(0, ProxyGroup(name=PLACEHOLDER_GROUP))
        group_names.add(PLACEHOLDER_GROUP)
        notes.append(f"已创建分组「{PLACEHOLDER_GROUP}」，请向其中添加节点")
    for g in template.groups:
        if g.name in group_names:
            notes.append(f"分组「{g.name}」已存在，已跳过")
            continue
        groups.append(g.model_copy(deep=True))
        group_names.add(g.name)

    providers = list(profile.rule_providers)
    provider_names = {p.name for p in providers}
    for p in template.rule_providers:
        if p.name in provider_names:
            notes.append(f"规则集「{p.name}」已存在，已跳过")
            continue
        providers.append(p.model_copy())
        provider_names.add(p.name)

    rules = list(profile.rules)
    existing = {(r.type, r.value, r.target) for r in rules}
    has_match = any(r.type == "MATCH" for r in rules)
    insert_at = next((i for i, r in enumerate(rules) if r.type == "MATCH"), len(rules))
    new_rules: list[Rule] = []
    template_match: Rule | None = None
    for r in template.rules:
        if r.type == "MATCH":
            if has_match:
                notes.append("方案已有 MATCH 规则，模板中的 MATCH 已跳过")
            else:
                template_match = r
            continue
        if (r.type, r.value, r.target) not in existing:
            new_rules.append(r.model_copy())
    rules[insert_at:insert_at] = new_rules
    if template_match is not None:
        rules.append(template_match.model_copy())

    return profile.model_copy(update={"groups": groups, "rules": rules, "rule_providers": providers}), notes
