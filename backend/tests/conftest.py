import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from routeforge.app import create_app
from routeforge.config import Settings
from routeforge.db.session import init_db, make_engine
from tests.helpers import ADMIN_PASSWORD, mock_client


@pytest.fixture
def engine():
    e = make_engine("sqlite://")
    init_db(e)
    return e


@pytest.fixture
def routes() -> dict:
    return {}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, database_url="sqlite://", admin_password=ADMIN_PASSWORD, cookie_secure=False)


@pytest.fixture
def app(settings, routes):
    return create_app(settings, http_client=mock_client(routes), start_scheduler=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    resp = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert resp.status_code == 200
    return client


@pytest.fixture
def db(app):
    with Session(app.state.engine) as s:
        yield s
