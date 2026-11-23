import pytest

from routeforge.ir.node import SnellNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_uri, to_uri


def test_snell_v4_udp_parse_and_roundtrip():
    uri = "snell://testpsk1234567890abcdef@snell.example.com:20066?version=4&udp=true#primary"
    node = parse_uri(uri)
    assert node == SnellNode(
        name="primary",
        server="snell.example.com",
        port=20066,
        psk="testpsk1234567890abcdef",
        version=4,
        udp=True,
    )
    assert to_uri(node) == uri


def test_snell_with_obfs_and_reuse():
    uri = "snell://p%40ss@203.0.113.10:1443?version=v5&udp=false&reuse=1&obfs=http&obfs-host=bing.com#HK"
    node = parse_uri(uri)
    assert node == SnellNode(
        name="HK",
        server="203.0.113.10",
        port=1443,
        psk="p@ss",
        version=5,
        udp=False,
        reuse=True,
        obfs_opts={"mode": "http", "host": "bing.com"},
    )
    assert parse_uri(to_uri(node)) == node


def test_snell_default_name_and_optional_params():
    node = parse_uri("snell://secret@snell.example.com:8388")
    assert node.name == "snell.example.com:8388"
    assert node.version is None and node.udp is True and node.reuse is None and node.obfs_opts == {}
    assert parse_uri(to_uri(node)) == node


@pytest.mark.parametrize("bad", [
    "snell://snell.example.com:20066?version=4",          # 缺 psk
    "snell://psk@snell.example.com:20066?version=7",      # version 越界
    "snell://psk@snell.example.com:20066?version=abc",    # version 非数字
    "snell://psk@snell.example.com:20066?udp=maybe",      # udp 非布尔
    "snell://psk@snell.example.com:20066?reuse=maybe",    # reuse 非布尔
])
def test_snell_errors(bad):
    with pytest.raises(ParseError):
        parse_uri(bad)
