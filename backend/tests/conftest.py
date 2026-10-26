import pytest

from routeforge.db.session import init_db, make_engine


@pytest.fixture
def engine():
    e = make_engine("sqlite://")
    init_db(e)
    return e
