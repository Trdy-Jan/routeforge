import shutil
import subprocess

import pytest
import yaml

from routeforge.ir.node import Hysteria2Node, Reality, SSNode, TLSOptions, Transport, VlessNode
from routeforge.ir.profile import Rule, RuleProvider
from routeforge.ir.resolved import ResolvedGroup, ResolvedProfile
from routeforge.renderers import get_renderer
from routeforge.renderers.mihomo import BASE_CONFIG, MihomoRenderer

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"


def group(name, members, type="select") -> ResolvedGroup:
    return ResolvedGroup(name=name, type=type, members=members,
                         url="https://www.gstatic.com/generate_204", interval=300, tolerance=50)


def sample() -> ResolvedProfile:
    return ResolvedProfile(
        name="我的方案",
        proxies=[
            SSNode(name="香港 01", server="1.2.3.4", port=8388, cipher="aes-128-gcm", password="p"),
            VlessNode(name="落地", server="ex.com", port=443, uuid=UUID, flow="xtls-rprx-vision",
                      tls=TLSOptions(sni="www.apple.com", fingerprint="chrome",
                                     reality=Reality(public_key="PK", short_id="ab")),
                      via="前置"),
        ],
        groups=[
            group("节点选择", ["落地", "前置", "DIRECT"]),
            group("前置", ["香港 01"], type="url-test"),
            group("广告拦截", ["REJECT", "DIRECT"]),
        ],
        rules=[
            Rule(type="RULE-SET", value="ads", target="广告拦截"),
            Rule(type="IP-CIDR", value="10.0.0.0/8", target="DIRECT", no_resolve=True),
            Rule(type="MATCH", target="节点选择"),
        ],
        rule_providers=[RuleProvider(name="ads", behavior="domain", format="mrs",
                                     url="https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/category-ads-all.mrs")],
        source_ids=[1, 2],
    )


def test_render_structure():
    result = MihomoRenderer().render(sample())
    assert result.content_type == "text/yaml; charset=utf-8"
    assert result.file_ext == "yaml"
    assert result.warnings == []
    config = yaml.safe_load(result.content)
    assert list(config) == [*BASE_CONFIG, "proxies", "proxy-groups", "rule-providers", "rules"]
    assert [p["name"] for p in config["proxies"]] == ["香港 01", "落地"]
    assert config["proxies"][1]["dialer-proxy"] == "前置"
    assert config["proxy-groups"] == [
        {"name": "节点选择", "type": "select", "proxies": ["落地", "前置", "DIRECT"]},
        {"name": "前置", "type": "url-test", "proxies": ["香港 01"],
         "url": "https://www.gstatic.com/generate_204", "interval": 300, "tolerance": 50},
        {"name": "广告拦截", "type": "select", "proxies": ["REJECT", "DIRECT"]},
    ]
    assert config["rule-providers"] == {
        "ads": {"type": "http", "behavior": "domain", "format": "mrs",
                "url": "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite/category-ads-all.mrs",
                "interval": 86400, "path": "./ruleset/ads.mrs"},
    }
    assert config["rules"] == ["RULE-SET,ads,广告拦截", "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve", "MATCH,节点选择"]


def test_output_is_deterministic_and_keeps_unicode_literal():
    a = MihomoRenderer().render(sample()).content
    b = MihomoRenderer().render(sample()).content
    assert a == b
    assert "香港 01" in a


def test_no_rule_providers_key_when_none_defined():
    p = sample().model_copy(update={"rule_providers": [], "rules": [Rule(type="MATCH", target="节点选择")]})
    assert "rule-providers" not in yaml.safe_load(MihomoRenderer().render(p).content)


GEOSITE_BASE = "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite"


def geosite_profile(rules, providers=()) -> ResolvedProfile:
    return ResolvedProfile(name="x", proxies=[], groups=[group("G", ["DIRECT"])],
                           rules=[*rules, Rule(type="MATCH", target="G")],
                           rule_providers=list(providers), source_ids=[])


def test_geosite_rule_becomes_mrs_rule_provider():
    p = geosite_profile([Rule(type="GEOSITE", value="Tencent", target="G")])
    config = yaml.safe_load(MihomoRenderer().render(p).content)
    assert config["rule-providers"] == {
        "geosite-tencent": {"type": "http", "behavior": "domain", "format": "mrs",
                            "url": f"{GEOSITE_BASE}/tencent.mrs",
                            "interval": 86400, "path": "./ruleset/geosite-tencent.mrs"},
    }
    assert config["rules"] == ["RULE-SET,geosite-tencent,G", "MATCH,G"]


def test_geosite_reuses_provider_with_same_url_and_dedupes():
    docker = RuleProvider(name="docker", behavior="domain", format="mrs", url=f"{GEOSITE_BASE}/docker.mrs")
    p = geosite_profile([
        Rule(type="GEOSITE", value="docker", target="G"),
        Rule(type="GEOSITE", value="cn", target="DIRECT"),
        Rule(type="GEOSITE", value="cn", target="G"),
    ], [docker])
    config = yaml.safe_load(MihomoRenderer().render(p).content)
    assert list(config["rule-providers"]) == ["docker", "geosite-cn"]
    assert config["rules"] == ["RULE-SET,docker,G", "RULE-SET,geosite-cn,DIRECT", "RULE-SET,geosite-cn,G", "MATCH,G"]


def test_geosite_provider_name_avoids_collision():
    taken = RuleProvider(name="geosite-cn", behavior="domain", format="yaml", url="https://example.com/cn.yaml")
    p = geosite_profile([Rule(type="GEOSITE", value="cn", target="G")], [taken])
    config = yaml.safe_load(MihomoRenderer().render(p).content)
    assert config["rule-providers"]["geosite-cn-2"]["url"] == f"{GEOSITE_BASE}/cn.mrs"
    assert config["rules"][0] == "RULE-SET,geosite-cn-2,G"


def test_unsupported_node_is_skipped_with_warning_and_removed_from_groups():
    bad = Hysteria2Node(name="坏", server="a.com", port=443, password="pw", transport=Transport(type="ws"))
    p = sample()
    p = p.model_copy(update={
        "proxies": [*p.proxies, bad],
        "groups": [group("节点选择", ["坏"]), *p.groups[1:]],
    })
    result = MihomoRenderer().render(p)
    config = yaml.safe_load(result.content)
    assert "坏" not in [x["name"] for x in config["proxies"]]
    assert config["proxy-groups"][0]["proxies"] == ["DIRECT"]
    assert any("坏" in w for w in result.warnings)
    assert "分组「节点选择」的成员均被跳过，已自动加入 DIRECT" in result.warnings
    assert not any("「前置」" in w and "均被跳过" in w for w in result.warnings)


def test_dialer_proxy_pointing_to_skipped_node_is_dropped():
    bad = Hysteria2Node(name="坏", server="a.com", port=443, password="pw", transport=Transport(type="ws"))
    landing = SSNode(name="L", server="1.1.1.1", port=1, cipher="aes-128-gcm", password="p", via="坏")
    p = ResolvedProfile(name="x", proxies=[landing, bad], groups=[group("G", ["L", "坏"])],
                        rules=[Rule(type="MATCH", target="G")], rule_providers=[], source_ids=[])
    result = MihomoRenderer().render(p)
    config = yaml.safe_load(result.content)
    assert "dialer-proxy" not in config["proxies"][0]
    assert any("L" in w and "前置" in w for w in result.warnings)


def test_registry():
    assert isinstance(get_renderer("mihomo"), MihomoRenderer)
    with pytest.raises(KeyError):
        get_renderer("surge")


@pytest.mark.skipif(shutil.which("mihomo") is None, reason="mihomo 不在 PATH 中")
def test_mihomo_binary_accepts_config(tmp_path):
    p = sample().model_copy(update={"rule_providers": [], "rules": [Rule(type="MATCH", target="节点选择")]})
    path = tmp_path / "config.yaml"
    path.write_text(MihomoRenderer().render(p).content, encoding="utf-8")
    proc = subprocess.run(["mihomo", "-t", "-d", str(tmp_path), "-f", str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
