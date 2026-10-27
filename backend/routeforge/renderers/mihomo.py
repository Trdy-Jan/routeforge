"""Mihomo（Clash Meta）YAML 渲染器。"""

import copy
from urllib.parse import quote

import yaml

from routeforge.ir.profile import Rule, RuleProvider
from routeforge.ir.resolved import ResolvedProfile
from routeforge.parsers.clash_proxy import to_clash
from routeforge.parsers.errors import UnsupportedNode
from routeforge.renderers.base import RenderResult

BASE_CONFIG: dict = {
    "mixed-port": 7890,
    "allow-lan": False,
    "mode": "rule",
    "log-level": "info",
    "ipv6": False,
    "dns": {
        "enable": True,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "nameserver": ["https://doh.pub/dns-query", "https://dns.alidns.com/dns-query"],
    },
}

_PROVIDER_EXT = {"yaml": "yaml", "text": "list", "mrs": "mrs"}

GEOSITE_MRS_BASE = "https://github.com/MetaCubeX/meta-rules-dat/raw/meta/geo/geosite"


class MihomoRenderer:
    target = "mihomo"

    def render(self, profile: ResolvedProfile) -> RenderResult:
        warnings: list[str] = []
        proxies: list[dict] = []
        skipped: set[str] = set()
        for node in profile.proxies:
            try:
                proxies.append(to_clash(node))
            except UnsupportedNode as e:
                warnings.append(f"节点「{node.name}」无法用于 Mihomo，已跳过：{e}")
                skipped.add(node.name)
        for p in proxies:
            if p.get("dialer-proxy") in skipped:
                warnings.append(f"节点「{p['name']}」的前置「{p['dialer-proxy']}」已被跳过，链式代理已移除")
                del p["dialer-proxy"]

        groups = []
        for g in profile.groups:
            members = [m for m in g.members if m not in skipped]
            if not members:
                warnings.append(f"分组「{g.name}」的成员均被跳过，已自动加入 DIRECT")
                members = ["DIRECT"]
            entry: dict = {"name": g.name, "type": g.type, "proxies": members}
            if g.type != "select":
                entry["url"] = g.url
                entry["interval"] = g.interval
            if g.type == "url-test":
                entry["tolerance"] = g.tolerance
            groups.append(entry)

        rules, providers = _geosite_to_rule_sets(profile.rules, profile.rule_providers)

        config = copy.deepcopy(BASE_CONFIG)
        config["proxies"] = proxies
        config["proxy-groups"] = groups
        if providers:
            config["rule-providers"] = {p.name: _provider(p) for p in providers}
        config["rules"] = [_rule_line(r) for r in rules]

        content = yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return RenderResult(content=content, content_type="text/yaml; charset=utf-8", file_ext="yaml", warnings=warnings)


def _geosite_to_rule_sets(rules: list[Rule], providers: list[RuleProvider]) -> tuple[list[Rule], list[RuleProvider]]:
    """GEOSITE 依赖客户端本地 GeoSite.dat，各客户端自带的版本分类不全（如 ShellCrash 精简版缺 tencent），
    因此改写为引用 meta-rules-dat 按分类编译的 .mrs 规则集；已有同 URL 的规则集直接复用。"""
    providers = list(providers)
    by_url = {p.url: p.name for p in providers}
    names = {p.name for p in providers}
    out: list[Rule] = []
    for r in rules:
        if r.type != "GEOSITE":
            out.append(r)
            continue
        category = r.value.strip().lower()
        url = f"{GEOSITE_MRS_BASE}/{quote(category, safe='@!-_.')}.mrs"
        name = by_url.get(url)
        if name is None:
            name = base = f"geosite-{category}"
            n = 2
            while name in names:
                name, n = f"{base}-{n}", n + 1
            providers.append(RuleProvider(name=name, behavior="domain", format="mrs", url=url))
            by_url[url] = name
            names.add(name)
        out.append(r.model_copy(update={"type": "RULE-SET", "value": name}))
    return out, providers


def _provider(p: RuleProvider) -> dict:
    return {
        "type": "http",
        "behavior": p.behavior,
        "format": p.format,
        "url": p.url,
        "interval": p.interval,
        "path": f"./ruleset/{p.name}.{_PROVIDER_EXT[p.format]}",
    }


def _rule_line(r: Rule) -> str:
    if r.type == "MATCH":
        return f"MATCH,{r.target}"
    parts = [r.type, r.value, r.target]
    if r.no_resolve:
        parts.append("no-resolve")
    return ",".join(parts)
