import pytest

from routeforge.ir.node import MieruNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_many, parse_uri, parse_uri_nodes, to_uri


def test_mierus_single_port():
    uri = ("mierus://user1:pass1@203.0.113.10?handshake-mode=HANDSHAKE_NO_WAIT&mtu=1400"
           "&multiplexing=MULTIPLEXING_OFF&port=11811&profile=default&protocol=TCP")
    assert parse_uri_nodes(uri) == [MieruNode(
        name="mieru-203.0.113.10-11811-TCP", server="203.0.113.10", port=11811, protocol="TCP",
        username="user1", password="pass1", multiplexing="MULTIPLEXING_OFF", handshake_mode="HANDSHAKE_NO_WAIT")]


def test_mierus_multi_pairs_and_range():  # 官方文档示例
    uri = ("mierus://user1:pass1@203.0.113.10?port=6666&port=9998-9999&port=6489&profile=default"
           "&protocol=TCP&protocol=TCP&protocol=UDP&traffic-pattern=CCoQAQ")
    nodes = parse_uri_nodes(uri)
    assert [(n.name, n.port, n.port_range, n.protocol) for n in nodes] == [
        ("mieru-203.0.113.10-6666-TCP", 6666, None, "TCP"),
        ("mieru-203.0.113.10-9998-9999-TCP", 9998, "9998-9999", "TCP"),
        ("mieru-203.0.113.10-6489-UDP", 6489, None, "UDP"),
    ]
    assert all(n.traffic_pattern == "CCoQAQ" for n in nodes)


def test_mierus_fragment_names():
    base = "mierus://u:p@h.example.com?profile=default&port=1000&protocol=TCP"
    assert parse_uri_nodes(base + "#My%20Node")[0].name == "My Node"
    two = base + "&port=2000&protocol=UDP#My"
    assert [n.name for n in parse_uri_nodes(two)] == ["My-1000-TCP", "My-2000-UDP"]


def test_mierus_percent_encoded_credentials_roundtrip():
    node = parse_uri_nodes("mierus://us%3Aer:p%40ss%25@h.example.com?profile=d&port=1&protocol=TCP#N")[0]
    assert (node.username, node.password) == ("us:er", "p@ss%")
    assert parse_uri_nodes(to_uri(node)) == [node]


def test_mierus_ipv6_host():
    node = parse_uri_nodes("mierus://u:p@[2001:db8::1]?profile=d&port=443&protocol=UDP#V6")[0]
    assert node.server == "2001:db8::1"
    assert "@[2001:db8::1]?" in to_uri(node)


def test_mierus_dump_shape_and_roundtrip():
    node = MieruNode(name="香港 M", server="203.0.113.10", port=2090, port_range="2090-2099", protocol="UDP",
                     username="user1", password="pass1", handshake_mode="HANDSHAKE_STANDARD")
    uri = to_uri(node)
    assert uri.startswith("mierus://user1:pass1@203.0.113.10?") and "profile=default" in uri and "port=2090-2099" in uri
    assert parse_uri_nodes(uri) == [node]


@pytest.mark.parametrize("bad", [
    "mierus://u:p@h?profile=d&port=1&port=2&protocol=TCP",   # 数量不一致
    "mierus://u:p@h?profile=d&protocol=TCP",                 # 缺 port
    "mierus://u:p@h?profile=d&port=70000&protocol=TCP",      # 端口越界
    "mierus://u:p@h?profile=d&port=1&protocol=QUIC",         # 协议非法
    "mierus://h?profile=d&port=1&protocol=TCP",              # 缺认证
    "mierus://u@h?profile=d&port=1&protocol=TCP",            # 缺密码
])
def test_mierus_errors(bad):
    with pytest.raises(ParseError):
        parse_uri_nodes(bad)


def test_mieru_standard_link_rejected():
    with pytest.raises(ParseError, match="暂不支持 mieru:// 标准链接"):
        parse_uri_nodes("mieru://QUJD")


def test_parse_uri_rejects_multi_node_link():
    with pytest.raises(ParseError):
        parse_uri("mierus://u:p@h?profile=d&port=1&port=2&protocol=TCP&protocol=UDP")


def test_parse_many_expands_mieru_links():
    text = "mierus://u:p@h?profile=d&port=1&port=2&protocol=TCP&protocol=UDP\nbroken"
    outcome = parse_many(text)
    assert len(outcome.nodes) == 2 and len(outcome.errors) == 1
