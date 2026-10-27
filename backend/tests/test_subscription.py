from routeforge.ir.node import SSNode, TrojanNode
from routeforge.parsers.subscription import parse_subscription

# base64url（无填充）编码的 "trojan://pw@a.example.com:443#A\r\nss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B\r\n"
B64_SUB = (
    "dHJvamFuOi8vcHdAYS5leGFtcGxlLmNvbTo0NDMjQQ0Kc3M6Ly9ZV1Z6TFRJMU5pMW5ZMjA2ZEdWemRBQDEuMi4zLjQ6ODM4OCNCDQo"
)


def test_base64_without_padding_and_crlf_lines():
    outcome = parse_subscription(B64_SUB)
    assert [type(n) for n in outcome.nodes] == [TrojanNode, SSNode]
    assert [n.name for n in outcome.nodes] == ["A", "B"]
    assert outcome.errors == []


def test_base64_wrapped_over_multiple_lines():
    wrapped = "\n".join(B64_SUB[i:i + 40] for i in range(0, len(B64_SUB), 40))
    assert [n.name for n in parse_subscription(wrapped).nodes] == ["A", "B"]


def test_plain_share_links_with_bom():
    text = "\ufefftrojan://pw@a.example.com:443#A\nss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B\n"
    assert [n.name for n in parse_subscription(text).nodes] == ["A", "B"]


def test_clash_yaml_keeps_good_proxies_and_reports_bad_ones():
    text = """
mixed-port: 7890
proxies:
  - {name: 香港 01, type: ss, server: 1.2.3.4, port: 8388, cipher: aes-128-gcm, password: p}
  - {name: 坏节点, type: snell, server: 1.2.3.4, port: 1}
  - just-a-string
proxy-groups: []
"""
    outcome = parse_subscription(text)
    assert [n.name for n in outcome.nodes] == ["香港 01"]
    assert [e.line for e in outcome.errors] == ["坏节点", "just-a-string"]


def test_empty_and_garbage():
    assert parse_subscription("   \n").nodes == []
    garbage = parse_subscription("<html>502 Bad Gateway</html>")
    assert garbage.nodes == []
    assert len(garbage.errors) == 1
    assert "无法识别" in garbage.errors[0].message


def test_deeply_nested_yaml_does_not_leak_recursion_error():
    text = "proxies: " + "[" * 5000 + "]" * 5000
    outcome = parse_subscription(text)
    assert outcome.nodes == []
    assert outcome.errors


def test_error_line_does_not_stringify_nested_structures():
    text = "proxies:\n  - [1, 2, 3]\n  - {name: [a, b], type: ss}\n  - {name: 42, type: nope, server: s, port: 1}\n"
    outcome = parse_subscription(text)
    assert [e.line for e in outcome.errors] == ["list", "?", "42"]
