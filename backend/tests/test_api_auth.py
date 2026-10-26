import pytest
from fastapi.testclient import TestClient

from routeforge.app import create_app
from routeforge.auth import ConfigError, LoginLimiter
from routeforge.config import Settings
from tests.helpers import ADMIN_PASSWORD


def test_login_me_logout(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": ADMIN_PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").json() == {"admin": True}
    assert client.post("/api/auth/logout", json={}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_session_cookie_flags(client):
    resp = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    cookie = resp.headers["set-cookie"].lower()
    assert "routeforge_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_lockout_after_five_failures(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": ADMIN_PASSWORD}).status_code == 429


def test_limiter_unlocks_after_lockout_window():
    now = [0.0]
    limiter = LoginLimiter(max_failures=2, window=60, lockout=100, clock=lambda: now[0])
    limiter.record_failure("ip")
    now[0] = 61  # 第一次失败已滑出窗口
    limiter.record_failure("ip")
    assert not limiter.is_locked("ip")
    limiter.record_failure("ip")
    assert limiter.is_locked("ip")
    now[0] = 162
    assert not limiter.is_locked("ip")


def test_non_json_post_rejected(client):
    resp = client.post("/api/auth/login", data={"password": ADMIN_PASSWORD})
    assert resp.status_code == 415


def test_first_start_requires_admin_password(tmp_path):
    settings = Settings(data_dir=tmp_path, database_url=f"sqlite:///{(tmp_path / 'r.db').as_posix()}",
                        admin_password=None, cookie_secure=False)
    with pytest.raises(ConfigError):
        create_app(settings, start_scheduler=False)


def test_password_only_needed_on_first_start(tmp_path):
    url = f"sqlite:///{(tmp_path / 'r.db').as_posix()}"
    create_app(Settings(data_dir=tmp_path, database_url=url, admin_password="first", cookie_secure=False),
               start_scheduler=False)
    app = create_app(Settings(data_dir=tmp_path, database_url=url, admin_password=None, cookie_secure=False),
                     start_scheduler=False)
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"password": "first"}).status_code == 200
