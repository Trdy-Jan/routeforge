import httpx

from tests.helpers import import_text

SUB_URL = "https://airport.example/sub"
LINKS = (
    "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#A\n"
    "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8389#B\n"
    "broken\n"
)


def create_manual(admin) -> int:
    resp = admin.post("/api/sources", json={"kind": "manual", "name": "手动"})
    assert resp.status_code == 201
    return resp.json()["id"]


def create_subscription(admin, routes) -> dict:
    routes[SUB_URL] = httpx.Response(200, text=LINKS, headers={"subscription-userinfo": "upload=1; download=2; total=3"})
    resp = admin.post("/api/sources", json={"kind": "subscription", "name": "机场", "url": SUB_URL})
    assert resp.status_code == 201
    return resp.json()


def test_requires_login(client):
    assert client.get("/api/sources").status_code == 401
    assert client.get("/api/nodes").status_code == 401


def test_manual_source_import_list_and_edit(admin):
    sid = create_manual(admin)
    parsed, result = import_text(admin, sid, LINKS)
    assert result.json() == {"added": 2}
    assert parsed["errors"] == [{"line": "broken", "message": "不是分享链接"}]

    nodes = admin.get("/api/nodes", params={"source_id": sid}).json()
    assert [n["name"] for n in nodes] == ["A", "B"]
    assert (nodes[0]["type"], nodes[0]["server"], nodes[0]["port"]) == ("ss", "1.2.3.4", 8388)

    a_id = nodes[0]["id"]
    renamed = admin.patch(f"/api/nodes/{a_id}", json={"name": "香港 A"}).json()
    assert renamed["name"] == "香港 A" and renamed["data"]["name"] == "香港 A"
    assert [n["id"] for n in admin.get("/api/nodes", params={"q": "香港"}).json()] == [a_id]

    bulk = admin.post("/api/nodes/bulk", json={"ids": [n["id"] for n in nodes], "enabled": False})
    assert bulk.json() == {"updated": 2}
    assert all(not n["enabled"] for n in admin.get("/api/nodes").json())
    assert admin.get("/api/sources").json()[0]["node_count"] == 2

    assert admin.delete(f"/api/nodes/{a_id}").status_code == 204
    assert len(admin.get("/api/nodes").json()) == 1


def test_subscription_source_fetches_on_create_and_keeps_nodes_on_failure(admin, routes):
    src = create_subscription(admin, routes)
    assert src["node_count"] == 2 and src["last_error"] is None
    assert src["userinfo"] == {"upload": 1, "download": 2, "total": 3}

    routes[SUB_URL] = httpx.Response(503)
    result = admin.post(f"/api/sources/{src['id']}/refresh", json={}).json()
    assert result["ok"] is False and "503" in result["error"]

    after = admin.get("/api/sources").json()[0]
    assert after["node_count"] == 2 and "503" in after["last_error"]


def test_subscription_nodes_cannot_be_renamed_deleted_or_imported(admin, routes):
    src = create_subscription(admin, routes)
    nid = admin.get("/api/nodes").json()[0]["id"]
    assert admin.patch(f"/api/nodes/{nid}", json={"name": "x"}).status_code == 400
    assert admin.patch(f"/api/nodes/{nid}", json={"enabled": False}).json()["enabled"] is False
    assert admin.delete(f"/api/nodes/{nid}").status_code == 400
    assert admin.post(f"/api/sources/{src['id']}/nodes/parse", json={"text": LINKS}).status_code == 400
    cfg = {"name": "X", "type": "ss", "server": "a", "port": 1, "cipher": "aes-128-gcm", "password": "p"}
    r = admin.post(f"/api/sources/{src['id']}/nodes/import", json={"nodes": [{"name": "X", "config": cfg}]})
    assert r.status_code == 400


def test_source_validation_and_kind_rules(admin):
    assert admin.post("/api/sources", json={"kind": "subscription", "name": "x"}).status_code == 422
    assert admin.post("/api/sources", json={"kind": "subscription", "name": "x", "url": "ftp://a"}).status_code == 422
    assert admin.post("/api/sources", json={"kind": "manual", "name": ""}).status_code == 422
    sid = create_manual(admin)
    assert admin.post(f"/api/sources/{sid}/refresh", json={}).status_code == 400
    assert admin.patch(f"/api/sources/{sid}", json={"url": "https://a"}).status_code == 400
    assert admin.patch(f"/api/sources/{sid}", json={"name": "改名"}).json()["name"] == "改名"
    assert admin.patch("/api/sources/999", json={"name": "x"}).status_code == 404


def test_delete_source_removes_nodes(admin):
    sid = create_manual(admin)
    import_text(admin, sid, LINKS)
    assert admin.delete(f"/api/sources/{sid}").status_code == 204
    assert admin.get("/api/sources").json() == []
    assert admin.get("/api/nodes").json() == []


def test_match_filter(admin):
    sid = create_manual(admin)
    import_text(admin, sid, LINKS)
    matched = admin.post("/api/nodes/match", json={"source_id": sid, "name_regex": "^A$"}).json()
    assert [n["name"] for n in matched] == ["A"]
    assert admin.post("/api/nodes/match", json={"name_regex": "("}).status_code == 400


def test_create_subscription_with_malformed_url_is_422(admin):
    resp = admin.post("/api/sources", json={"kind": "subscription", "name": "x", "url": "http://[::1"})
    assert resp.status_code == 422
    assert admin.get("/api/sources").json() == []


def test_patch_malformed_url_is_400(admin, routes):
    routes["https://a.example/s"] = httpx.Response(200, text="trojan://pw@a.example.com:443#A\n")
    sid = admin.post("/api/sources", json={"kind": "subscription", "name": "x", "url": "https://a.example/s"}).json()["id"]
    assert admin.patch(f"/api/sources/{sid}", json={"url": "http://[::1"}).status_code == 400


def test_changing_url_clears_last_fetched_at(admin, routes):
    routes["https://a.example/s"] = httpx.Response(200, text="trojan://pw@a.example.com:443#A\n")
    created = admin.post("/api/sources", json={"kind": "subscription", "name": "x", "url": "https://a.example/s"}).json()
    assert created["last_fetched_at"] is not None
    same = admin.patch(f"/api/sources/{created['id']}", json={"url": "https://a.example/s"}).json()
    assert same["last_fetched_at"] is not None
    changed = admin.patch(f"/api/sources/{created['id']}", json={"url": "https://b.example/s"}).json()
    assert changed["last_fetched_at"] is None


def test_bulk_ids_capped(admin):
    resp = admin.post("/api/nodes/bulk", json={"ids": list(range(5001)), "enabled": False})
    assert resp.status_code == 422


def test_edit_manual_node_config(admin):
    sid = create_manual(admin)
    import_text(admin, sid, LINKS)
    node = admin.get("/api/nodes").json()[0]
    admin.patch(f"/api/nodes/{node['id']}", json={"enabled": False})

    config = admin.get(f"/api/nodes/{node['id']}/config").json()["config"]
    assert "server: 1.2.3.4" in config and "cipher: aes-256-gcm" in config

    new = ("name: 新节点\ntype: trojan\nserver: example.com\nport: 443\npassword: pw\n"
           "sni: sni.example.com\nnetwork: ws\nws-opts:\n  path: /ws\n")
    updated = admin.patch(f"/api/nodes/{node['id']}", json={"config": new}).json()
    assert (updated["name"], updated["type"], updated["server"], updated["port"]) == ("新节点", "trojan", "example.com", 443)
    assert updated["data"]["tls"]["sni"] == "sni.example.com"
    assert updated["data"]["transport"] == {"type": "ws", "path": "/ws", "host": None, "service_name": None}
    assert updated["enabled"] is False and updated["position"] == node["position"]


def test_edit_node_config_validation(admin, routes):
    sid = create_manual(admin)
    import_text(admin, sid, LINKS)
    nid = admin.get("/api/nodes").json()[0]["id"]
    for bad in ("name: x\ntype: ss\nserver: a\nport: 0\ncipher: c\npassword: p\n",  # 端口非法
                "name: x\ntype: wireguard\nserver: a\nport: 1\n",  # 不支持的类型
                "[1, 2]",  # 不是映射
                "a: [",  # YAML 语法错误
                "type: ss\nserver: a\nport: 1\ncipher: c\npassword: p\n"):  # 缺少名称
        resp = admin.patch(f"/api/nodes/{nid}", json={"config": bad})
        assert resp.status_code == 400, bad
    assert admin.get("/api/nodes").json()[0]["name"] == "A"

    src = create_subscription(admin, routes)
    sub_nid = admin.get("/api/nodes", params={"source_id": src["id"]}).json()[0]["id"]
    assert admin.get(f"/api/nodes/{sub_nid}/config").status_code == 200
    ok = "name: x\ntype: ss\nserver: a\nport: 1\ncipher: c\npassword: p\n"
    assert admin.patch(f"/api/nodes/{sub_nid}", json={"config": ok}).status_code == 400


def test_bulk_delete_skips_subscription_nodes(admin, routes):
    sid = create_manual(admin)
    import_text(admin, sid, LINKS)
    src = create_subscription(admin, routes)
    ids = [n["id"] for n in admin.get("/api/nodes").json()]
    assert len(ids) == 4

    resp = admin.post("/api/nodes/bulk-delete", json={"ids": ids + [99999]})
    assert resp.json() == {"deleted": 2, "skipped": 2}
    remaining = admin.get("/api/nodes").json()
    assert {n["source_id"] for n in remaining} == {src["id"]}


def test_bulk_delete_ids_capped(admin):
    resp = admin.post("/api/nodes/bulk-delete", json={"ids": list(range(5001))})
    assert resp.status_code == 422


def test_parse_does_not_write_and_lists_existing(admin):
    sid = create_manual(admin)
    parsed = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()
    assert [n["name"] for n in parsed["nodes"]] == ["A", "B"]
    assert parsed["errors"] == [{"line": "broken", "message": "不是分享链接"}]
    assert parsed["existing_names"] == [] and admin.get("/api/nodes").json() == []
    import_text(admin, sid, LINKS)
    again = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()
    assert sorted(again["existing_names"]) == ["A", "B"]


def test_import_selected_mieru_with_rename(admin):
    sid = create_manual(admin)
    text = "mierus://u:p@203.0.113.10?profile=d&port=2090-2099&port=443&protocol=TCP&protocol=UDP"
    parsed = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": text}).json()
    first = parsed["nodes"][0]
    assert (first["type"], first["port"], first["port_range"]) == ("mieru", 2090, "2090-2099")
    r = admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [{"name": "香港 M", "config": first["config"]}]})
    assert r.json() == {"added": 1}
    node = admin.get("/api/nodes").json()[0]
    assert (node["name"], node["port_range"]) == ("香港 M", "2090-2099")


def test_import_trims_names(admin):
    sid = create_manual(admin)
    cfg = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()["nodes"][0]["config"]
    assert admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [{"name": "  X  ", "config": cfg}]}).status_code == 200
    assert admin.get("/api/nodes").json()[0]["name"] == "X"
    assert admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [{"name": "   ", "config": cfg}]}).status_code == 400


def test_import_rejects_invalid_node_atomically(admin):
    sid = create_manual(admin)
    good = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": LINKS}).json()["nodes"][0]
    bad = {"name": "坏", "config": {**good["config"], "type": "snell"}}
    r = admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [good, bad]})
    assert r.status_code == 400 and "第 2 个节点「坏」" in r.json()["detail"]
    assert admin.get("/api/nodes").json() == []


def test_import_malformed_config_is_400_not_500(admin):
    sid = create_manual(admin)
    cfg = {"name": "V", "type": "vmess", "server": "a", "port": 1, "uuid": "b831381d-6324-4d53-ad4f-8cda48b30811",
           "network": "ws", "ws-opts": "str"}
    r = admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": [{"name": "V", "config": cfg}]})
    assert r.status_code == 400 and "第 1 个节点「V」" in r.json()["detail"]


def test_reparse_link_keeps_name_and_id(admin):
    sid = create_manual(admin)
    import_text(admin, sid, LINKS)
    node = admin.get("/api/nodes", params={"source_id": sid}).json()[0]
    link = "trojan://pw@5.6.7.8:443?sni=x.example#别的名字"
    config = admin.post(f"/api/nodes/{node['id']}/reparse", json={"text": link}).json()["config"]
    assert "type: trojan" in config and "server: 5.6.7.8" in config
    assert f"name: {node['name']}" in config and "别的名字" not in config
    # 只解析不写库
    assert admin.get("/api/nodes", params={"source_id": sid}).json()[0]["type"] == "ss"

    updated = admin.patch(f"/api/nodes/{node['id']}", json={"config": config}).json()
    assert (updated["id"], updated["name"], updated["type"]) == (node["id"], node["name"], "trojan")


def test_reparse_link_validation(admin, routes):
    sid = create_manual(admin)
    import_text(admin, sid, LINKS)
    nid = admin.get("/api/nodes", params={"source_id": sid}).json()[0]["id"]
    assert admin.post(f"/api/nodes/{nid}/reparse", json={"text": "broken"}).status_code == 400
    two = admin.post(f"/api/nodes/{nid}/reparse", json={"text": LINKS})
    assert two.status_code == 400 and "1 个" in two.json()["detail"]
    assert admin.post("/api/nodes/99999/reparse", json={"text": LINKS}).status_code == 404

    create_subscription(admin, routes)
    sub_nid = [n for n in admin.get("/api/nodes").json() if n["source_id"] != sid][0]["id"]
    assert admin.post(f"/api/nodes/{sub_nid}/reparse", json={"text": "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#A"}).status_code == 400
