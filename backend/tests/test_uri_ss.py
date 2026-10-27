import pytest

from routeforge.ir.node import SSNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_many, parse_uri, to_uri
from routeforge.parsers.uri import ss


def test_sip002_base64_userinfo_and_chinese_name():
    node = ss.parse("ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#%E9%A6%99%E6%B8%AF%2001")
    assert node == SSNode(name="香港 01", server="1.2.3.4", port=8388, cipher="aes-256-gcm", password="test")


def test_legacy_fully_base64_encoded():
    node = ss.parse("ss://YWVzLTEyOC1nY206cHdAZXhhbXBsZS5jb206NDQz#Legacy")
    assert (node.cipher, node.password, node.server, node.port, node.name) == (
        "aes-128-gcm", "pw", "example.com", 443, "Legacy",
    )


def test_plain_userinfo_2022_cipher_with_ipv6():
    node = ss.parse(
        "ss://2022-blake3-aes-128-gcm:YctPZ6U7xPPcU%2Bgp3u%2B0tx%2FtRizJN9K8y%2BuKlW2qjlI%3D@[2001:db8::1]:443#v6"
    )
    assert node.server == "2001:db8::1"
    assert node.password == "YctPZ6U7xPPcU+gp3u+0tx/tRizJN9K8y+uKlW2qjlI="


def test_obfs_plugin():
    node = ss.parse(
        "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388/?plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dbing.com#O"
    )
    assert node.plugin == "obfs"
    assert node.plugin_opts == {"mode": "http", "host": "bing.com"}


def test_missing_name_falls_back_to_host_port():
    assert ss.parse("ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388").name == "1.2.3.4:8388"


@pytest.mark.parametrize(
    "node",
    [
        SSNode(name="香港 01", server="1.2.3.4", port=8388, cipher="aes-256-gcm", password="p@ss:word"),
        SSNode(name="v6", server="2001:db8::1", port=443, cipher="aes-128-gcm", password="x"),
        SSNode(name="O", server="h.com", port=1, cipher="aes-128-gcm", password="x",
               plugin="obfs", plugin_opts={"mode": "tls", "host": "bing.com"}),
        SSNode(name="V", server="h.com", port=1, cipher="aes-128-gcm", password="x",
               plugin="v2ray-plugin", plugin_opts={"mode": "websocket", "tls": True, "host": "a.com", "path": "/ws"}),
    ],
)
def test_dump_parse_roundtrip(node):
    uri = ss.dump(node)
    assert ss.parse(uri) == node
    if node.server == "2001:db8::1":
        assert "@[2001:db8::1]:443" in uri


@pytest.mark.parametrize(
    "bad",
    ["ss://", "ss://!!!notbase64", "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:notaport#x",
     "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388/?plugin=kcptun#x"],
)
def test_malformed_raises_parse_error(bad):
    with pytest.raises(ParseError):
        ss.parse(bad)


def test_dispatcher_routes_by_scheme_and_rejects_unknown():
    assert isinstance(parse_uri("  ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B  "), SSNode)
    with pytest.raises(ParseError, match="不支持的协议"):
        parse_uri("socks5://1.2.3.4:1080")
    with pytest.raises(ParseError):
        parse_uri("not a link")


def test_to_uri_dispatches_by_node_type():
    node = SSNode(name="a", server="h.com", port=1, cipher="aes-128-gcm", password="x")
    assert to_uri(node).startswith("ss://")


def test_parse_many_skips_blank_and_comment_lines_and_collects_errors():
    text = "\n# comment\nss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#A\r\nss://broken\n\n"
    outcome = parse_many(text)
    assert [n.name for n in outcome.nodes] == ["A"]
    assert len(outcome.errors) == 1
    assert outcome.errors[0].line == "ss://broken"


def test_uppercase_scheme_is_normalized_before_dispatch():
    upper = parse_uri("SS://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B")
    lower = parse_uri("ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#B")
    assert upper == lower == SSNode(
        name="B", server="1.2.3.4", port=8388, cipher="aes-256-gcm", password="test"
    )
