import pytest

from routeforge.ir.node import Reality, TLSOptions, Transport, TrojanNode, VlessNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_uri, to_uri
from routeforge.parsers.uri import trojan, vless

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"


def test_trojan_ipv6_ws_emoji_name_and_encoded_password():
    node = trojan.parse(
        "trojan://pa%40ss@[2001:db8::1]:443?sni=a.com&type=ws&path=%2Fws&host=a.com"
        "#%F0%9F%87%AD%F0%9F%87%B0%20HK"
    )
    assert node == TrojanNode(
        name="🇭🇰 HK",
        server="2001:db8::1",
        port=443,
        password="pa@ss",
        tls=TLSOptions(sni="a.com"),
        transport=Transport(type="ws", path="/ws", host="a.com"),
    )


def test_trojan_peer_alias_and_allow_insecure():
    node = trojan.parse("trojan://pw@a.com:443?peer=b.com&allowInsecure=1#P")
    assert node.tls == TLSOptions(sni="b.com", insecure=True)
    assert node.transport is None


def test_vless_reality_vision():
    node = vless.parse(
        f"vless://{UUID}@ex.com:443?encryption=none&flow=xtls-rprx-vision&security=reality"
        "&sni=www.apple.com&fp=chrome&pbk=PUBKEY&sid=6ba8&type=tcp#R"
    )
    assert node == VlessNode(
        name="R",
        server="ex.com",
        port=443,
        uuid=UUID,
        flow="xtls-rprx-vision",
        tls=TLSOptions(sni="www.apple.com", fingerprint="chrome", reality=Reality(public_key="PUBKEY", short_id="6ba8")),
    )


def test_vless_without_security_has_no_tls_and_http_type_maps_to_h2():
    node = vless.parse(f"vless://{UUID}@ex.com:80?type=http&path=%2Fh2&host=ex.com#H")
    assert node.tls is None
    assert node.transport == Transport(type="h2", path="/h2", host="ex.com")


@pytest.mark.parametrize(
    "node",
    [
        TrojanNode(name="🇭🇰 HK", server="2001:db8::1", port=443, password="pa@ss",
                   tls=TLSOptions(sni="a.com", alpn=["h2", "http/1.1"]),
                   transport=Transport(type="ws", path="/ws", host="a.com")),
        TrojanNode(name="plain", server="a.com", port=443, password="pw"),
        VlessNode(name="R", server="ex.com", port=443, uuid=UUID, flow="xtls-rprx-vision",
                  tls=TLSOptions(sni="www.apple.com", fingerprint="chrome",
                                 reality=Reality(public_key="PUBKEY", short_id="6ba8"))),
        VlessNode(name="G", server="ex.com", port=443, uuid=UUID,
                  tls=TLSOptions(sni="ex.com", insecure=True), transport=Transport(type="grpc", service_name="gun")),
        VlessNode(name="W", server="ex.com", port=80, uuid=UUID, transport=Transport(type="httpupgrade", path="/up")),
    ],
)
def test_dump_parse_roundtrip(node):
    assert parse_uri(to_uri(node)) == node


@pytest.mark.parametrize(
    "bad",
    [
        f"vless://{UUID}@ex.com:443?type=kcp#x",
        f"vless://{UUID}@ex.com:443?security=reality&sni=a.com#x",
        "vless://@ex.com:443#x",
        "trojan://pw@a.com#noport",
        "trojan://pw@a.com:443?security=xyz#x",
    ],
)
def test_malformed_raises_parse_error(bad):
    with pytest.raises(ParseError):
        parse_uri(bad)
