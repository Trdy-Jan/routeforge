from routeforge.ir.node import SSNode
from routeforge.ir.profile import NodeRef, Profile, ProxyGroup, Rule
from routeforge.resolver import LibraryNode, resolve
from routeforge.templates import PLACEHOLDER_GROUP, apply_template, load_templates

ALL_IDS = ["ads", "ai", "cn-direct", "final", "streaming", "telegram"]


def test_all_builtin_templates_load_and_use_metacubex_rule_sets():
    templates = load_templates()
    assert sorted(templates) == ALL_IDS
    for t in templates.values():
        assert t.name and t.description
        for p in t.rule_providers:
            assert p.url.startswith("https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/")
            assert p.format == "mrs"


def test_applying_every_template_to_empty_profile_resolves_cleanly():
    templates = load_templates()
    profile = Profile(name="p")
    for tid in ALL_IDS:
        profile, _ = apply_template(profile, templates[tid])
    # 给「节点选择」加一个节点，模拟用户后续操作
    groups = [g.model_copy(update={"members": [NodeRef(node_id=1)]}) if g.name == PLACEHOLDER_GROUP else g
              for g in profile.groups]
    profile = profile.model_copy(update={"groups": groups})
    library = [LibraryNode(id=1, source_id=1, enabled=True,
                           node=SSNode(name="HK", server="1.1.1.1", port=1, cipher="aes-128-gcm", password="p"))]
    result = resolve(profile, library)
    assert result.ok, result.errors
    assert profile.groups[0].name == PLACEHOLDER_GROUP
    assert profile.rules[-1].type == "MATCH"


def test_placeholder_created_once_with_note():
    templates = load_templates()
    profile, notes = apply_template(Profile(name="p"), templates["ai"])
    assert [g.name for g in profile.groups].count(PLACEHOLDER_GROUP) == 1
    assert any(PLACEHOLDER_GROUP in n for n in notes)
    profile, notes = apply_template(profile, templates["streaming"])
    assert [g.name for g in profile.groups].count(PLACEHOLDER_GROUP) == 1
    assert not any("已创建" in n for n in notes)


def test_reapplying_is_idempotent():
    templates = load_templates()
    once, _ = apply_template(Profile(name="p"), templates["telegram"])
    twice, notes = apply_template(once, templates["telegram"])
    assert twice.groups == once.groups
    assert twice.rules == once.rules
    assert twice.rule_providers == once.rule_providers
    assert any("已存在" in n for n in notes)


def test_rules_inserted_before_existing_match_and_template_match_skipped():
    templates = load_templates()
    base = Profile(
        name="p",
        groups=[ProxyGroup(name="Proxy")],
        rules=[Rule(type="DOMAIN", value="a.com", target="DIRECT"), Rule(type="MATCH", target="Proxy")],
    )
    after_ads, _ = apply_template(base, templates["ads"])
    assert [r.type for r in after_ads.rules] == ["DOMAIN", "RULE-SET", "MATCH"]
    after_final, notes = apply_template(after_ads, templates["final"])
    assert [r.type for r in after_final.rules].count("MATCH") == 1
    assert after_final.rules[-1].target == "Proxy"
    assert any("MATCH" in n for n in notes)


def test_input_profile_not_mutated():
    templates = load_templates()
    base = Profile(name="p")
    apply_template(base, templates["ads"])
    assert base.groups == [] and base.rules == [] and base.rule_providers == []
