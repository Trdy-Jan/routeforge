import pytest

from routeforge.ir.node import (
    Hysteria2Node, MieruNode, Reality, SSNode, TLSOptions, Transport, TrojanNode, TuicNode, VlessNode, VmessNode,
)
from routeforge.parsers.clash_proxy import from_clash, to_clash
from routeforge.parsers.errors import ParseError, UnsupportedNode

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"


def test_vless_reality_to_clash_exact_dict():
    node = VlessNode(
        name="R", server="ex.com", port=443, uuid=UUID, flow="xtls-rprx-vision",
        tls=TLSOptions(sni="www.apple.com", fingerprint="chrome", reality=Reality(public_key="PK", short_id="ab")),
        via="前置",
    )
    assert to_clash(node) == {
        "name": "R", "type": "vless", "server": "ex.com", "port": 443, "udp": True,
        "uuid": UUID, "flow": "xtls-rprx-vision",
        "tls": True, "servername": "www.apple.com", "client-fingerprint": "chrome",
        "reality-opts": {"public-key": "PK", "short-id": "ab"},
        "dialer-proxy": "前置",
    }


def test_trojan_uses_sni_key_and_ws_opts():
    node = TrojanNode(name="T", server="a.com", port=443, password="pw",
                      tls=TLSOptions(sni="b.com", insecure=True),
                      transport=Transport(type="ws", path="/ws", host="b.com"))
    d = to_clash(node)
    assert d["sni"] == "b.com" and "servername" not in d and "tls" not in d
    assert d["skip-cert-verify"] is True
    assert d["network"] == "ws"
    assert d["ws-opts"] == {"path": "/ws", "headers": {"Host": "b.com"}}


def test_httpupgrade_maps_to_ws_with_flag():
    node = VlessNode(name="U", server="a.com", port=80, uuid=UUID, transport=Transport(type="httpupgrade", path="/up"))
    d = to_clash(node)
    assert d["tls"] is False
    assert d["network"] == "ws"
    assert d["ws-opts"] == {"path": "/up", "v2ray-http-upgrade": True}


@pytest.mark.parametrize(
    "node",
    [
        SSNode(name="s", server="1.2.3.4", port=8388, cipher="aes-128-gcm", password="p",
               plugin="obfs", plugin_opts={"mode": "http", "host": "bing.com"}),
        VmessNode(name="v", server="a.com", port=443, uuid=UUID, alter_id=0, cipher="auto",
                  tls=TLSOptions(sni="a.com", alpn=["h2"]), transport=Transport(type="grpc", service_name="gun")),
        VmessNode(name="v2", server="a.com", port=80, uuid=UUID, udp=False),
        VlessNode(name="h2", server="a.com", port=443, uuid=UUID, tls=TLSOptions(),
                  transport=Transport(type="h2", path="/p", host="a.com")),
        TrojanNode(name="t", server="a.com", port=443, password="pw"),
        Hysteria2Node(name="h", server="a.com", port=443, password="pw", obfs="salamander",
                      obfs_password="x", up="50 Mbps", down="200 Mbps", tls=TLSOptions(sni="a.com")),
        TuicNode(name="u", server="a.com", port=443, uuid=UUID, password="pw", congestion_control="bbr",
                 tls=TLSOptions(alpn=["h3"])),
    ],
)
def test_roundtrip(node):
    assert from_clash(to_clash(node)) == node


def test_from_clash_real_world_entry():
    d = {
        "name": "🇺🇸 美国 01", "type": "vmess", "server": "us.example.com", "port": "443",
        "uuid": UUID, "alterId": "0", "cipher": "auto", "tls": True, "servername": "us.example.com",
        "network": "ws", "ws-opts": {"path": "/v", "headers": {"Host": "us.example.com"}},
        "skip-cert-verify": False,
    }
    node = from_clash(d)
    assert node.port == 443
    assert node.transport == Transport(type="ws", path="/v", host="us.example.com")


@pytest.mark.parametrize(
    "d",
    [
        {"name": "x", "type": "snell", "server": "a", "port": 1},
        {"name": "x", "type": "ss", "server": "a", "port": 1},
        {"name": "x", "type": "ss", "server": "a", "port": 1, "cipher": "c", "password": "p", "plugin": "shadow-tls"},
        {"name": "x", "type": "vmess", "server": "a", "port": 1, "uuid": UUID, "network": "quic"},
        {"name": "x", "type": "trojan", "server": "a", "port": "abc", "password": "p"},
    ],
)
def test_from_clash_invalid_raises_parse_error(d):
    with pytest.raises(ParseError):
        from_clash(d)


def test_to_clash_rejects_transport_on_protocol_without_transport():
    node = Hysteria2Node(name="h", server="a.com", port=443, password="pw", transport=Transport(type="ws"))
    with pytest.raises(UnsupportedNode):
        to_clash(node)


def test_from_clash_error_message_does_not_stringify_non_scalar_name():
    with pytest.raises(ParseError) as exc:
        from_clash({"name": {"nested": [1, 2]}, "type": "ss"})
    assert "节点「?」" in str(exc.value)


def test_from_clash_h2_host_as_plain_string():
    node = from_clash({"name": "H", "type": "vless", "server": "a.com", "port": 443, "uuid": UUID, "tls": True,
                       "network": "h2", "h2-opts": {"host": "b.com", "path": "/h2"}})
    assert node.transport == Transport(type="h2", path="/h2", host="b.com")


def test_from_clash_ws_host_header_is_case_insensitive():
    node = from_clash({"name": "W", "type": "vmess", "server": "a.com", "port": 443, "uuid": UUID,
                       "network": "ws", "ws-opts": {"path": "/ws", "headers": {"host": "b.com"}}})
    assert node.transport.host == "b.com"


MIERU = {"name": "M", "type": "mieru", "server": "203.0.113.10", "port": 11811, "transport": "TCP",
         "udp": True, "username": "user1", "password": "pass1",
         "multiplexing": "MULTIPLEXING_OFF", "handshake-mode": "HANDSHAKE_NO_WAIT"}


def test_mieru_roundtrip_single_port():
    node = from_clash(MIERU)
    assert isinstance(node, MieruNode) and node.protocol == "TCP" and node.handshake_mode == "HANDSHAKE_NO_WAIT"
    assert to_clash(node) == MIERU


def test_mieru_port_range_wins_and_port_not_emitted():
    d = {**MIERU, "port-range": "2090-2099", "transport": "udp"}
    node = from_clash(d)
    assert (node.port, node.port_range, node.protocol) == (2090, "2090-2099", "UDP")
    out = to_clash(node)
    assert out["port-range"] == "2090-2099" and "port" not in out


def test_mieru_optional_fields_omitted():
    d = {k: v for k, v in MIERU.items() if k not in ("multiplexing", "handshake-mode")}
    assert to_clash(from_clash(d)) == d


def test_mieru_unknown_multiplexing_passes_through():
    assert to_clash(from_clash({**MIERU, "multiplexing": "MULTIPLEXING_FUTURE"}))["multiplexing"] == "MULTIPLEXING_FUTURE"


@pytest.mark.parametrize("patch", [
    {"transport": "QUIC"}, {"port-range": "2099-2090"}, {"port-range": "0-10"}, {"port-range": "abc"},
])
def test_mieru_invalid_fields(patch):
    with pytest.raises(ParseError):
        from_clash({**MIERU, **patch})


def test_mieru_missing_port_and_range():
    d = {k: v for k, v in MIERU.items() if k != "port"}
    with pytest.raises(ParseError):
        from_clash(d)


def test_mieru_with_tls_is_unsupported():
    node = from_clash(MIERU).model_copy(update={"tls": TLSOptions()})
    with pytest.raises(UnsupportedNode):
        to_clash(node)
