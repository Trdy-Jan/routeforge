import pytest
from pydantic import ValidationError

from routeforge.ir.node import NodeAdapter, Reality, SSNode, TLSOptions, Transport, VlessNode


def test_discriminated_union_picks_class_by_type():
    node = NodeAdapter.validate_python(
        {"type": "ss", "name": "a", "server": "1.1.1.1", "port": 8388, "cipher": "aes-128-gcm", "password": "p"}
    )
    assert isinstance(node, SSNode)
    assert node.udp is True
    assert node.tls is None and node.transport is None and node.via is None


def test_vless_reality_json_roundtrip():
    node = VlessNode(
        name="R",
        server="ex.com",
        port=443,
        uuid="u",
        flow="xtls-rprx-vision",
        tls=TLSOptions(sni="www.apple.com", fingerprint="chrome", reality=Reality(public_key="pk", short_id="ab")),
        transport=Transport(type="grpc", service_name="gun"),
    )
    assert NodeAdapter.validate_json(NodeAdapter.dump_json(node)) == node


def test_port_out_of_range_rejected():
    with pytest.raises(ValidationError):
        SSNode(name="a", server="h", port=70000, cipher="c", password="p")


def test_tcp_is_not_a_transport_type():
    with pytest.raises(ValidationError):
        Transport(type="tcp")
