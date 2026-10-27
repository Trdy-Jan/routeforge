from urllib.parse import quote

import httpx
import yaml

SUB_URL = "https://airport.example/sub"
SS_HK = "ss://YWVzLTI1Ni1nY206dGVzdA@1.2.3.4:8388#%E9%A6%99%E6%B8%AF%2001"
GOOD = {
    "name": "我的方案",
    "groups": [{"name": "Proxy", "members": [{"kind": "filter", "name_regex": "."}]}],
    "rules": [{"type": "MATCH", "target": "Proxy"}],
}


def make_profile(admin, body=GOOD) -> dict:
    p = admin.post("/api/profiles", json={"name": body["name"]}).json()
    assert admin.put(f"/api/profiles/{p['id']}", json=body).status_code == 200
    return {"id": p["id"], "token": p["token"]}


def manual_with(admin, links: str) -> int:
    sid = admin.post("/api/sources", json={"kind": "manual", "name": "手动"}).json()["id"]
    admin.post(f"/api/sources/{sid}/nodes/import", json={"text": links})
    return sid


def proxy_names(resp) -> list[str]:
    return [p["name"] for p in yaml.safe_load(resp.text)["proxies"]]


def test_unknown_token_is_404(client):
    assert client.get("/sub/does-not-exist").status_code == 404


def test_returns_yaml_and_headers_without_login(admin):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    admin.post("/api/auth/logout", json={})

    resp = admin.get(f"/sub/{p['token']}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/yaml")
    assert resp.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote('我的方案')}.yaml"
    assert resp.headers["profile-update-interval"] == "24"
    assert "subscription-userinfo" not in resp.headers
    assert proxy_names(resp) == ["香港 01"]


def test_userinfo_only_when_all_nodes_from_one_subscription(admin, routes):
    routes[SUB_URL] = httpx.Response(200, text=SS_HK,
                                     headers={"subscription-userinfo": "upload=1; download=2; total=3; expire=4"})
    admin.post("/api/sources", json={"kind": "subscription", "name": "机场", "url": SUB_URL})
    p = make_profile(admin)
    first = admin.get(f"/sub/{p['token']}")
    assert first.headers["subscription-userinfo"] == "upload=1; download=2; total=3; expire=4"

    manual_with(admin, "trojan://pw@a.example.com:443#B")  # 导入会让缓存失效
    second = admin.get(f"/sub/{p['token']}")
    assert "subscription-userinfo" not in second.headers
    assert proxy_names(second) == ["香港 01", "B"]


def test_broken_profile_falls_back_to_last_good(admin):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    good = admin.get(f"/sub/{p['token']}")
    assert good.status_code == 200

    admin.put(f"/api/profiles/{p['id']}", json={**GOOD, "rules": []})
    fallback = admin.get(f"/sub/{p['token']}")
    assert fallback.status_code == 200
    assert fallback.text == good.text
    assert admin.get(f"/api/profiles/{p['id']}").json()["last_good_at"] is not None


def test_broken_profile_without_history_is_500(admin):
    p = make_profile(admin, {**GOOD, "rules": []})
    resp = admin.get(f"/sub/{p['token']}")
    assert resp.status_code == 500
    assert "管理界面" in resp.text


def test_rotated_token_invalidates_old_link(admin):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    new_token = admin.post(f"/api/profiles/{p['id']}/rotate-token", json={}).json()["token"]
    assert admin.get(f"/sub/{p['token']}").status_code == 404
    assert admin.get(f"/sub/{new_token}").status_code == 200


def test_unknown_target_is_400(admin):
    p = make_profile(admin)
    assert admin.get(f"/sub/{p['token']}", params={"target": "surge"}).status_code == 400


def test_cache_is_used_and_invalidated_by_writes(admin, app):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    admin.get(f"/sub/{p['token']}")
    assert app.state.cache.get((p["id"], "mihomo")) is not None

    node_ids = [n["id"] for n in admin.get("/api/nodes").json()]
    admin.post("/api/nodes/bulk", json={"ids": node_ids, "enabled": False})
    assert app.state.cache.get((p["id"], "mihomo")) is None
    assert proxy_names(admin.get(f"/sub/{p['token']}")) == []


def test_render_failure_falls_back_to_last_good(admin, monkeypatch):
    manual_with(admin, SS_HK)
    p = make_profile(admin)
    first = admin.get(f"/sub/{p['token']}")
    assert first.status_code == 200
    admin.put(f"/api/profiles/{p['id']}", json=GOOD)  # invalidates cache

    def boom(*a, **k):
        raise RuntimeError("render exploded")

    monkeypatch.setattr("routeforge.api.subscribe.render_profile", boom)
    resp = admin.get(f"/sub/{p['token']}")
    assert resp.status_code == 200 and resp.text == first.text


def test_render_failure_without_history_is_500(admin, monkeypatch):
    manual_with(admin, SS_HK)
    p = make_profile(admin)

    def boom(*a, **k):
        raise RuntimeError("render exploded")

    monkeypatch.setattr("routeforge.api.subscribe.render_profile", boom)
    assert admin.get(f"/sub/{p['token']}").status_code == 500


def test_last_good_commit_failure_still_serves_content(admin, monkeypatch):
    from sqlmodel import Session
    manual_with(admin, SS_HK)
    p = make_profile(admin)

    def fail_commit(self):
        raise RuntimeError("db locked")

    monkeypatch.setattr(Session, "commit", fail_commit)
    resp = admin.get(f"/sub/{p['token']}")
    assert resp.status_code == 200 and "proxies" in resp.text
