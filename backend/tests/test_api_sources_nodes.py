import httpx

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
    result = admin.post(f"/api/sources/{sid}/nodes/import", json={"text": LINKS}).json()
    assert result["added"] == 2
    assert result["errors"] == [{"line": "broken", "message": "不是分享链接"}]

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
    assert admin.post(f"/api/sources/{src['id']}/nodes/import", json={"text": LINKS}).status_code == 400


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
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": LINKS})
    assert admin.delete(f"/api/sources/{sid}").status_code == 204
    assert admin.get("/api/sources").json() == []
    assert admin.get("/api/nodes").json() == []


def test_match_filter(admin):
    sid = create_manual(admin)
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": LINKS})
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
