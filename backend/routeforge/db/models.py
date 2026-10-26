import secrets
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from routeforge.ir.node import Node, NodeAdapter
from routeforge.ir.profile import Profile


def utcnow() -> datetime:
    # sqlmodel 0.0.48 的 datetime 列只接受带时区的值，因此返回 aware UTC。
    return datetime.now(UTC)


def new_token() -> str:
    return secrets.token_urlsafe(32)


class Source(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str  # "manual" | "subscription"
    name: str
    url: str | None = None
    refresh_interval: int = 360  # 分钟
    user_agent: str = "clash.meta"
    last_fetched_at: datetime | None = None  # 最近一次拉取尝试
    last_error: str | None = None
    userinfo: dict | None = Field(default=None, sa_column=Column(JSON))


class NodeRow(SQLModel, table=True):
    __tablename__ = "node"

    id: int | None = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="source.id", index=True)
    name: str  # 与 data["name"] 同步，用于刷新时按名称匹配
    data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    enabled: bool = True
    position: int = 0

    @classmethod
    def from_node(cls, source_id: int, node: Node, position: int) -> "NodeRow":
        return cls(source_id=source_id, name=node.name, data=NodeAdapter.dump_python(node, mode="json"),
                   position=position)

    def to_node(self) -> Node:
        return NodeAdapter.validate_python(self.data)

    def set_node(self, node: Node) -> None:
        self.name = node.name
        self.data = NodeAdapter.dump_python(node, mode="json")


class ProfileRow(SQLModel, table=True):
    __tablename__ = "profile"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    token: str = Field(index=True, unique=True)
    data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # {target: {"content": str, "content_type": str, "file_ext": str}}
    last_good: dict | None = Field(default=None, sa_column=Column(JSON))
    last_good_at: datetime | None = None

    @classmethod
    def new(cls, name: str) -> "ProfileRow":
        return cls(name=name, token=new_token(), data=Profile(name=name).model_dump(mode="json"))

    def to_profile(self) -> Profile:
        return Profile.model_validate({**self.data, "name": self.name})

    def set_profile(self, profile: Profile) -> None:
        self.name = profile.name
        self.data = profile.model_dump(mode="json")


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
