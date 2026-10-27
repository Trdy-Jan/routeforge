import json

import pytest

from routeforge.ir.node import Hysteria2Node, TLSOptions, Transport, TuicNode, VmessNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri import parse_uri, to_uri
from routeforge.parsers.uri._common import b64encode_text

UUID = "b831381d-6324-4d53-ad4f-8cda48b30811"

VMESS_WS_TLS = (
    "vmess://eyJ2IjogIjIiLCAicHMiOiAi5pel5pysIDAxIiwgImFkZCI6ICJqcC5leGFtcGxlLmNvbSIsICJwb3J0IjogIjQ0MyIsICJp"
    "ZCI6ICJiODMxMzgxZC02MzI0LTRkNTMtYWQ0Zi04Y2RhNDhiMzA4MTEiLCAiYWlkIjogIjAiLCAic2N5IjogImF1dG8iLCAibmV0Ijog"
    "IndzIiwgInR5cGUiOiAibm9uZSIsICJob3N0IjogImpwLmV4YW1wbGUuY29tIiwgInBhdGgiOiAiL3JheSIsICJ0bHMiOiAidGxzIiwg"
    "InNuaSI6ICJqcC5leGFtcGxlLmNvbSJ9"
)


def test_vmess_ws_tls_with_chinese_name():
    assert parse_uri(VMESS_WS_TLS) == VmessNode(
        name="日本 01",
        server="jp.example.com",
        port=443,
        uuid=UUID,
        tls=TLSOptions(sni="jp.example.com"),
        transport=Transport(type="ws", path="/ray", host="jp.example.com"),
    )


def test_vmess_grpc_service_name_comes_from_path_field():
    payload = {"add": "a.com", "port": 443, "id": UUID, "net": "grpc", "path": "gun", "tls": "tls"}
    node = parse_uri("vmess://" + b64encode_text(json.dumps(payload)))
    assert node.transport == Transport(type="grpc", service_name="gun")
    assert node.name == "a.com:443"


def test_hysteria2_with_obfs_and_hy2_alias():
    uri = "hy2://pw@h.com:443?sni=a.com&insecure=1&obfs=salamander&obfs-password=x#H"
    assert parse_uri(uri) == Hysteria2Node(
        name="H", server="h.com", port=443, password="pw",
        obfs="salamander", obfs_password="x", tls=TLSOptions(sni="a.com", insecure=True),
    )
    assert isinstance(parse_uri(uri.replace("hy2://", "hysteria2://")), Hysteria2Node)


def test_tuic():
    node = parse_uri(f"tuic://{UUID}:pa%3Ass@h.com:443?congestion_control=bbr&alpn=h3&sni=a.com&allow_insecure=1#T")
    assert node == TuicNode(
        name="T", server="h.com", port=443, uuid=UUID, password="pa:ss",
        congestion_control="bbr", tls=TLSOptions(sni="a.com", alpn=["h3"], insecure=True),
    )


@pytest.mark.parametrize(
    "node",
    [
        VmessNode(name="日本 01", server="jp.example.com", port=443, uuid=UUID,
                  tls=TLSOptions(sni="jp.example.com", alpn=["h2"], fingerprint="chrome"),
                  transport=Transport(type="ws", path="/ray", host="jp.example.com")),
        VmessNode(name="tcp", server="1.2.3.4", port=10086, uuid=UUID, alter_id=64, cipher="aes-128-gcm"),
        VmessNode(name="g", server="a.com", port=443, uuid=UUID, tls=TLSOptions(),
                  transport=Transport(type="grpc", service_name="gun")),
        Hysteria2Node(name="H 🇯🇵", server="2001:db8::1", port=8443, password="p@ss",
                      obfs="salamander", obfs_password="x", tls=TLSOptions(sni="a.com", insecure=True)),
        TuicNode(name="T", server="h.com", port=443, uuid=UUID, password="pa:ss",
                 congestion_control="bbr", tls=TLSOptions(sni="a.com", alpn=["h3"])),
    ],
)
def test_dump_parse_roundtrip(node):
    assert parse_uri(to_uri(node)) == node


@pytest.mark.parametrize(
    "bad",
    [
        "vmess://!!!",
        "vmess://" + b64encode_text("[1, 2]"),
        "vmess://" + b64encode_text('{"port": "1", "id": "x"}'),
        "vmess://" + b64encode_text('{"add": "a", "port": "99999", "id": "x"}'),
        "vmess://" + b64encode_text('{"add": "a", "port": "1", "id": "x", "net": "kcp"}'),
        "hysteria2://pw@h.com:443,20000-30000#hop",
        f"tuic://{UUID}@h.com:443#nopassword",
    ],
)
def test_malformed_raises_parse_error(bad):
    with pytest.raises(ParseError):
        parse_uri(bad)


@pytest.mark.parametrize(
    "fields",
    [
        {"add": None, "port": "1", "id": "x"},
        {"add": "", "port": "1", "id": "x"},
        {"add": "a", "port": "1", "id": None},
        {"add": "a", "port": "1", "id": ""},
    ],
)
def test_vmess_null_or_empty_add_or_id_is_parse_error(fields):
    with pytest.raises(ParseError):
        parse_uri("vmess://" + b64encode_text(json.dumps(fields)))
