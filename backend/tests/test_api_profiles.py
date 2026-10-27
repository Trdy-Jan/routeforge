SS_HK = "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#%E9%A6%99%E6%B8%AF%2001"
GOOD = {
    "name": "方案A",
    "groups": [{"name": "Proxy", "members": [{"kind": "filter", "name_regex": "香港"}]}],
    "rules": [{"type": "MATCH", "target": "Proxy"}],
}


def create_profile(admin, name="我的方案") -> dict:
    resp = admin.post("/api/profiles", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def import_hk(admin) -> None:
    sid = admin.post("/api/sources", json={"kind": "manual", "name": "手动"}).json()["id"]
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": SS_HK})


def test_requires_login(client):
    assert client.get("/api/profiles").status_code == 401
    assert client.get("/api/templates").status_code == 401


def test_create_get_update_delete(admin):
    p = create_profile(admin)
    assert p["profile"] == {"name": "我的方案", "groups": [], "rules": [], "rule_providers": [], "chains": []}
    assert len(p["token"]) >= 40 and p["last_good_at"] is None

    updated = admin.put(f"/api/profiles/{p['id']}", json=GOOD).json()
    assert updated["profile"]["name"] == "方案A"
    assert updated["profile"]["groups"][0]["type"] == "select"
    assert admin.get(f"/api/profiles/{p['id']}").json() == updated
    assert admin.get("/api/profiles").json() == [{"id": p["id"], "name": "方案A", "token": p["token"]}]

    bad = {"name": "x", "groups": [{"name": "G", "type": "bogus"}]}
    assert admin.put(f"/api/profiles/{p['id']}", json=bad).status_code == 422

    assert admin.delete(f"/api/profiles/{p['id']}").status_code == 204
    assert admin.get(f"/api/profiles/{p['id']}").status_code == 404


def test_templates_list_and_apply(admin):
    templates = admin.get("/api/templates").json()
    assert len(templates) == 6
    assert {"id": "ads", "name": "广告拦截"}.items() <= templates[0].items()

    p = create_profile(admin)
    applied = admin.post(f"/api/profiles/{p['id']}/apply-template", json={"template_id": "ai"}).json()
    assert [g["name"] for g in applied["profile"]["profile"]["groups"]] == ["节点选择", "AI 服务"]
    assert any("节点选择" in n for n in applied["notes"])
    assert admin.get(f"/api/profiles/{p['id']}").json()["profile"] == applied["profile"]["profile"]
    assert admin.post(f"/api/profiles/{p['id']}/apply-template", json={"template_id": "nope"}).status_code == 404


def test_preview_renders_or_reports_errors(admin):
    import_hk(admin)
    p = create_profile(admin)
    admin.put(f"/api/profiles/{p['id']}", json=GOOD)
    preview = admin.get(f"/api/profiles/{p['id']}/preview").json()
    assert preview["ok"] is True and preview["errors"] == []
    assert "香港 01" in preview["content"]

    admin.put(f"/api/profiles/{p['id']}", json={**GOOD, "rules": []})
    broken = admin.get(f"/api/profiles/{p['id']}/preview").json()
    assert broken["ok"] is False and broken["content"] is None
    assert any("MATCH" in e for e in broken["errors"])

    assert admin.get(f"/api/profiles/{p['id']}/preview", params={"target": "surge"}).status_code == 400


def test_rotate_token(admin):
    p = create_profile(admin)
    rotated = admin.post(f"/api/profiles/{p['id']}/rotate-token", json={}).json()
    assert rotated["token"] != p["token"] and len(rotated["token"]) >= 40


def test_update_rejects_blank_or_overlong_name(admin):
    p = create_profile(admin)
    for name in ("", "   ", "x" * 101):
        resp = admin.put(f"/api/profiles/{p['id']}", json={**GOOD, "name": name})
        assert resp.status_code == 422
    assert admin.get(f"/api/profiles/{p['id']}").json()["profile"]["name"] == "我的方案"
    assert admin.put(f"/api/profiles/{p['id']}", json={**GOOD, "name": "x" * 100}).status_code == 200
