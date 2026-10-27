from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine


def make_engine(url: str) -> Engine:
    if url == "sqlite://":  # 测试用内存库：所有线程共享同一连接
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, connect_args={"check_same_thread": False})


def init_db(engine: Engine) -> None:
    import routeforge.db.models  # noqa: F401  注册表结构

    SQLModel.metadata.create_all(engine)
