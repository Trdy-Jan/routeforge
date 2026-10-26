"""节点中间模型（IR）。所有输入格式解析到这里，所有渲染器从这里输出。"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter


class Reality(BaseModel):
    public_key: str
    short_id: str = ""


class TLSOptions(BaseModel):
    sni: str | None = None
    alpn: list[str] = []
    insecure: bool = False
    fingerprint: str | None = None
    reality: Reality | None = None


class Transport(BaseModel):
    """非 tcp 传输层；tcp 用 Node.transport = None 表示。"""

    type: Literal["ws", "grpc", "h2", "httpupgrade"]
    path: str | None = None
    host: str | None = None
    service_name: str | None = None


class NodeBase(BaseModel):
    name: str
    server: str
    port: int = Field(ge=1, le=65535)
    udp: bool = True
    tls: TLSOptions | None = None
    transport: Transport | None = None
    # 仅由 resolver 写入：本节点经由哪个分组 / 节点（最终名称）出站
    via: str | None = None
    extra: dict = {}


class SSNode(NodeBase):
    type: Literal["ss"] = "ss"
    cipher: str
    password: str
    plugin: Literal["obfs", "v2ray-plugin"] | None = None
    plugin_opts: dict[str, str | bool] = {}


class VmessNode(NodeBase):
    type: Literal["vmess"] = "vmess"
    uuid: str
    alter_id: int = 0
    cipher: str = "auto"


class VlessNode(NodeBase):
    type: Literal["vless"] = "vless"
    uuid: str
    flow: str | None = None


class TrojanNode(NodeBase):
    type: Literal["trojan"] = "trojan"
    password: str
    tls: TLSOptions | None = Field(default_factory=TLSOptions)


class Hysteria2Node(NodeBase):
    type: Literal["hysteria2"] = "hysteria2"
    password: str
    obfs: str | None = None
    obfs_password: str | None = None
    up: str | None = None
    down: str | None = None
    tls: TLSOptions | None = Field(default_factory=TLSOptions)


class TuicNode(NodeBase):
    type: Literal["tuic"] = "tuic"
    uuid: str
    password: str
    congestion_control: str | None = None
    tls: TLSOptions | None = Field(default_factory=TLSOptions)


Node = Annotated[
    Union[SSNode, VmessNode, VlessNode, TrojanNode, Hysteria2Node, TuicNode],
    Field(discriminator="type"),
]

NodeAdapter: TypeAdapter[Node] = TypeAdapter(Node)
