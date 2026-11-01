import httpx
import pytest

from tests.test_api_profiles import GOOD, create_profile, import_hk

ROUTER = "http://192.168.31.2"
LOGIN = f"{ROUTER}/cgi-bin/luci"



def login_ok(request: httpx.Request) -> httpx.Response:
    body = request.content.decode()
    if "luci_password=pw" not in body:
        return httpx.Response(403, text="login page")
    return httpx.Response(302, headers={"Location": "/cgi-bin/luci/", "Set-Cookie": "sysauth_http=abc; path=/"})


class PrefixRoutes(dict):
    def get(self, url, default=None):
        if "/admin/services/openclash/update_config" in url and "update" in self:
            return self["update"]
        return super().get(url, default)


@pytest.fixture
def routes() -> dict:
    # 更新接口带时间戳参数，按前缀匹配
    return PrefixRoutes()


def settings_body(**kw) -> dict:
    body = {"router_url": "192.168.31.2/", "username": "root", "password": "pw", "config_name": "192_168_31_88.yaml",
            "profile_id": None, "auto_push": False}
    body.update(kw)
    return body


def setup_router(routes) -> list:
    calls: list = []
    routes[LOGIN] = login_ok

    def update(request: httpx.Request) -> httpx.Response:
        if request.headers.get("cookie") != "sysauth_http=abc":
            return httpx.Response(403)
        calls.append(request.url.params["filename"])
        return httpx.Response(200, json={"info": 0})

    routes["update"] = update
    return calls


def test_requires_login(client):
    assert client.get("/api/openclash/settings").status_code == 401


def test_settings_roundtrip_hides_password(admin):
    out = admin.put("/api/openclash/settings", json=settings_body()).json()
    assert out["router_url"] == ROUTER
    assert out["config_name"] == "192_168_31_88"
    assert out["has_password"] is True
    assert "password" not in out
    # 密码留空表示不修改
    out = admin.put("/api/openclash/settings", json=settings_body(password="", username="admin")).json()
    assert out["has_password"] is True and out["username"] == "admin"
    assert admin.get("/api/openclash/settings").json() == out


def test_login_check(admin, routes):
    setup_router(routes)
    admin.put("/api/openclash/settings", json=settings_body())
    assert admin.post("/api/openclash/test", json={}).json() == {"ok": True, "message": "登录路由器成功"}
    admin.put("/api/openclash/settings", json=settings_body(password="wrong"))
    r = admin.post("/api/openclash/test", json={}).json()
    assert r["ok"] is False and "密码" in r["message"]


def test_manual_push(admin, routes):
    calls = setup_router(routes)
    admin.put("/api/openclash/settings", json=settings_body())
    r = admin.post("/api/openclash/push", json={}).json()
    assert r["ok"] is True and r["trigger"] == "manual"
    assert calls == ["192_168_31_88"]
    assert admin.get("/api/openclash/settings").json()["status"]["ok"] is True


def test_manual_push_reports_router_error(admin, routes):
    routes[LOGIN] = httpx.ConnectError("refused")
    admin.put("/api/openclash/settings", json=settings_body())
    r = admin.post("/api/openclash/push", json={}).json()
    assert r["ok"] is False and "无法连接" in r["message"]


def test_auto_push_only_when_content_changes(admin, app, routes):
    calls = setup_router(routes)
    import_hk(admin)
    p = create_profile(admin)
    admin.put(f"/api/profiles/{p['id']}", json=GOOD)
    pusher = app.state.openclash

    admin.put("/api/openclash/settings", json=settings_body(profile_id=p["id"]))
    assert pusher.push_if_changed() is False  # 未开启自动推送

    admin.put("/api/openclash/settings", json=settings_body(profile_id=p["id"], auto_push=True))
    assert pusher.push_if_changed() is True
    assert pusher.push_if_changed() is False  # 内容没变
    assert calls == ["192_168_31_88"]

    admin.put(f"/api/profiles/{p['id']}", json={**GOOD, "rules": [{"type": "MATCH", "target": "DIRECT"}]})
    assert pusher.push_if_changed() is True
    assert pusher.status.trigger == "auto"
    assert len(calls) == 2


def test_cache_invalidation_marks_dirty(admin, app):
    pusher = app.state.openclash
    pusher._dirty.clear()
    create_profile(admin)
    assert pusher._dirty.is_set()


def test_stok_login(routes, engine):
    from routeforge.openclash import OpenClashConfig, trigger_update
    from tests.helpers import mock_client

    seen = []
    routes[LOGIN] = lambda r: httpx.Response(
        302, headers={"Location": "/cgi-bin/luci/;stok=deadbeef/", "Set-Cookie": "sysauth=xyz; path=/"})
    routes["update"] = lambda r: seen.append(str(r.url)) or httpx.Response(200)
    cfg = OpenClashConfig(router_url=ROUTER, username="root", password="pw", config_name="c")
    trigger_update(mock_client(routes), cfg)
    assert seen[0].startswith(f"{ROUTER}/cgi-bin/luci/;stok=deadbeef/admin/services/openclash/update_config")


def test_openclash_reported_failure(admin, routes):
    setup_router(routes)
    routes["update"] = lambda r: httpx.Response(200, json={"status": "error", "message": "config not found"})
    admin.put("/api/openclash/settings", json=settings_body())
    r = admin.post("/api/openclash/push", json={}).json()
    assert r["ok"] is False and "config not found" in r["message"]
