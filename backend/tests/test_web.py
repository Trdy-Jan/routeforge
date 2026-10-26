import pytest
from fastapi.testclient import TestClient

from routeforge.app import create_app
from routeforge.config import Settings
from tests.helpers import ADMIN_PASSWORD, mock_client


@pytest.fixture
def web_client(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "favicon.ico").write_bytes(b"ICO")
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    settings = Settings(data_dir=tmp_path, database_url="sqlite://", admin_password=ADMIN_PASSWORD,
                        cookie_secure=False, static_dir=static)
    with TestClient(create_app(settings, http_client=mock_client({}), start_scheduler=False)) as c:
        yield c


def test_index_and_spa_fallback(web_client):
    assert web_client.get("/").text == "<html>INDEX</html>"
    assert web_client.get("/profiles/3").text == "<html>INDEX</html>"


def test_static_files(web_client):
    js = web_client.get("/assets/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert web_client.get("/favicon.ico").content == b"ICO"


def test_api_and_sub_paths_are_not_swallowed(web_client):
    resp = web_client.get("/api/unknown")
    assert resp.status_code == 404 and resp.headers["content-type"].startswith("application/json")
    assert web_client.get("/sub/nope").status_code == 404
    assert web_client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("url", [
    "/..%2Fsecret.txt",
    "/%2e%2e/secret.txt",
    "/..%5Csecret.txt",
    "/a%00b",
])
def test_invalid_or_traversal_paths_return_index(web_client, url):
    resp = web_client.get(url)
    assert resp.status_code == 200
    assert resp.text == "<html>INDEX</html>"


def test_absolute_path_outside_static_returns_index(web_client, tmp_path):
    secret = str(tmp_path / "secret.txt").replace("\\", "/")
    resp = web_client.get("//" + secret)
    assert resp.status_code == 200
    assert resp.text == "<html>INDEX</html>"


def test_no_static_dir_means_no_frontend(client):
    assert client.get("/").status_code == 404
