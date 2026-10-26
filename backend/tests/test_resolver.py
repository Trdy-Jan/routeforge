import re

import pytest

from routeforge.ir.node import SSNode
from routeforge.ir.profile import (
    Builtin, Chain, Filter, GroupRef, NodeRef, Profile, ProxyGroup, Rule, RuleProvider,
)
from routeforge.resolver import LibraryNode, match_filter, resolve


def ss(name: str) -> SSNode:
    return SSNode(name=name, server="1.1.1.1", port=8388, cipher="aes-128-gcm", password="p")


def lib(*rows: tuple) -> list[LibraryNode]:
    """rows: (id, source_id, name) 或 (id, source_id, name, enabled)"""
    return [LibraryNode(id=r[0], source_id=r[1], enabled=r[3] if len(r) > 3 else True, node=ss(r[2])) for r in rows]


MATCH_PROXY = [Rule(type="MATCH", target="Proxy")]


def make(groups, rules=None, **kw) -> Profile:
    return Profile(name="p", groups=groups, rules=MATCH_PROXY if rules is None else rules, **kw)


def group(name, *members, type="select") -> ProxyGroup:
    return ProxyGroup(name=name, type=type, members=list(members))


def members_of(result, name):
    return next(g.members for g in result.profile.groups if g.name == name)


def test_filter_expands_by_source_and_regex_in_library_order_skipping_disabled():
    library = lib((1, 10, "香港 01"), (2, 10, "日本 01"), (3, 20, "香港 02"), (4, 10, "香港 03", False), (5, 10, "香港 04 x0.1"))
    p = make([group("Proxy", Filter(source_id=10, name_regex="香港|HK", exclude_regex=r"x0\.\d"))])
    result = resolve(p, library)
    assert result.ok, result.errors
    assert members_of(result, "Proxy") == ["香港 01"]
    assert [n.name for n in result.profile.proxies] == ["香港 01"]
    assert result.profile.source_ids == [10]


def test_filter_without_source_matches_all_sources():
    library = lib((1, 10, "HK1"), (2, 20, "HK2"))
    result = resolve(make([group("Proxy", Filter(name_regex="HK"))]), library)
    assert members_of(result, "Proxy") == ["HK1", "HK2"]
    assert result.profile.source_ids == [10, 20]


def test_invalid_regex_is_an_error_not_an_exception():
    result = resolve(make([group("Proxy", Filter(name_regex="("))]), lib((1, 10, "a")))
    assert not result.ok
    assert any("正则" in e for e in result.errors)


def test_match_filter_public_helper():
    library = lib((1, 10, "HK1"), (2, 10, "JP1"))
    assert [ln.id for ln in match_filter(library, Filter(name_regex="HK"))] == [1]
    with pytest.raises(re.error):
        match_filter(library, Filter(name_regex="("))


def test_missing_or_disabled_node_ref_warns_and_empty_group_gets_direct():
    library = lib((1, 10, "a", False))
    result = resolve(make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=99))]), library)
    assert result.ok
    assert members_of(result, "Proxy") == ["DIRECT"]
    assert len([w for w in result.warnings if "不存在或已禁用" in w]) == 2
    assert any("DIRECT" in w for w in result.warnings)


def test_duplicate_member_listed_once():
    library = lib((1, 10, "a"))
    p = make([group("Proxy", NodeRef(node_id=1), Filter(name_regex="a"))])
    assert members_of(resolve(p, library), "Proxy") == ["a"]


def test_name_collisions_with_nodes_groups_and_builtins_get_suffix():
    library = lib((1, 10, "HK"), (2, 20, "HK"), (3, 10, "Proxy"), (4, 10, "DIRECT"))
    p = make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=2), NodeRef(node_id=3), NodeRef(node_id=4))])
    result = resolve(p, library)
    assert members_of(result, "Proxy") == ["HK", "HK 2", "Proxy 2", "DIRECT 2"]
    assert [n.name for n in result.profile.proxies] == ["HK", "HK 2", "Proxy 2", "DIRECT 2"]


def test_group_ref_builtin_and_nested_group():
    library = lib((1, 10, "a"))
    p = make([group("Proxy", GroupRef(name="Auto"), Builtin(name="DIRECT")),
              group("Auto", NodeRef(node_id=1), type="url-test")])
    result = resolve(p, library)
    assert members_of(result, "Proxy") == ["Auto", "DIRECT"]
    auto = next(g for g in result.profile.groups if g.name == "Auto")
    assert auto.type == "url-test" and auto.interval == 300


def test_unknown_group_ref_and_rule_target_are_errors():
    p = make([group("Proxy", GroupRef(name="Nope"))],
             rules=[Rule(type="DOMAIN-SUFFIX", value="a.com", target="Ghost"), *MATCH_PROXY])
    result = resolve(p, lib())
    assert not result.ok
    assert any("Nope" in e for e in result.errors)
    assert any("Ghost" in e for e in result.errors)


def test_duplicate_or_reserved_group_names_are_errors():
    result = resolve(make([group("Proxy"), group("Proxy"), group("DIRECT")]), lib())
    assert any("重复" in e for e in result.errors)
    assert any("保留" in e for e in result.errors)


def test_group_cycle_is_an_error():
    p = make([group("Proxy", GroupRef(name="B")), group("B", GroupRef(name="Proxy"))])
    result = resolve(p, lib())
    assert not result.ok
    assert any("循环" in e for e in result.errors)


def test_chain_via_group_sets_via_on_landing_node():
    library = lib((1, 10, "落地"), (2, 20, "机场 HK"))
    p = make(
        [group("Proxy", NodeRef(node_id=1)), group("前置", NodeRef(node_id=2))],
        chains=[Chain(node=NodeRef(node_id=1), via=GroupRef(name="前置"))],
    )
    result = resolve(p, library)
    assert result.ok, result.errors
    proxies = {n.name: n for n in result.profile.proxies}
    assert proxies["落地"].via == "前置"
    assert proxies["机场 HK"].via is None


def test_chain_via_node_includes_and_renames_the_dialer():
    library = lib((1, 10, "落地"), (2, 20, "Proxy"))
    p = make([group("Proxy", NodeRef(node_id=1))], chains=[Chain(node=NodeRef(node_id=1), via=NodeRef(node_id=2))])
    result = resolve(p, library)
    proxies = {n.name: n for n in result.profile.proxies}
    assert set(proxies) == {"落地", "Proxy 2"}
    assert proxies["落地"].via == "Proxy 2"


def test_chain_via_group_containing_landing_node_is_a_cycle():
    library = lib((1, 10, "落地"), (2, 20, "HK"))
    p = make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=2))],
             chains=[Chain(node=NodeRef(node_id=1), via=GroupRef(name="Proxy"))])
    result = resolve(p, library)
    assert not result.ok
    assert any("循环" in e and "落地" in e for e in result.errors)


def test_mutual_node_chains_are_a_cycle():
    library = lib((1, 10, "A"), (2, 10, "B"))
    p = make([group("Proxy", NodeRef(node_id=1), NodeRef(node_id=2))],
             chains=[Chain(node=NodeRef(node_id=1), via=NodeRef(node_id=2)),
                     Chain(node=NodeRef(node_id=2), via=NodeRef(node_id=1))])
    assert any("循环" in e for e in resolve(p, library).errors)


def test_chain_problems():
    library = lib((1, 10, "落地"), (2, 10, "孤立"))
    p = make(
        [group("Proxy", NodeRef(node_id=1))],
        chains=[
            Chain(node=NodeRef(node_id=1), via=GroupRef(name="不存在")),
            Chain(node=NodeRef(node_id=2), via=NodeRef(node_id=1)),
        ],
    )
    result = resolve(p, library)
    assert any("不存在" in e for e in result.errors)
    assert any("孤立" in w and "不会生效" in w for w in result.warnings)


def test_rule_validation():
    no_match = resolve(make([group("Proxy")], rules=[]), lib())
    assert any("MATCH" in e for e in no_match.errors)

    match_not_last = resolve(make([group("Proxy")], rules=[*MATCH_PROXY, Rule(type="DOMAIN", value="a", target="DIRECT")]), lib())
    assert any("MATCH" in e for e in match_not_last.errors)

    unknown_set = resolve(make([group("Proxy")], rules=[Rule(type="RULE-SET", value="ads", target="REJECT"), *MATCH_PROXY]), lib())
    assert any("ads" in e for e in unknown_set.errors)

    ok = resolve(
        make([group("Proxy")],
             rules=[Rule(type="RULE-SET", value="ads", target="REJECT"), *MATCH_PROXY],
             rule_providers=[RuleProvider(name="ads", behavior="domain", format="mrs", url="https://x/ads.mrs")]),
        lib(),
    )
    assert ok.ok, ok.errors


def test_pathological_regex_overflow_raises_re_error():
    with pytest.raises(re.error):
        match_filter(lib((1, 10, "a")), Filter(name_regex="a{99999999999999999999}"))


def test_pathological_regex_is_an_error_in_resolve():
    result = resolve(make([group("Proxy", Filter(name_regex="a{99999999999999999999}"))]), lib((1, 10, "a")))
    assert not result.ok
    assert any("正则" in e for e in result.errors)
