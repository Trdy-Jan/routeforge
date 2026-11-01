"""设置：推送到 OpenClash。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from routeforge.api.deps import HttpDep, SessionDep, require_admin
from routeforge.openclash import (
    OpenClashError, OpenClashPusher, PushStatus, check_login, load_config, normalize_router_url, save_config,
)

router = APIRouter(prefix="/api/openclash", tags=["openclash"], dependencies=[Depends(require_admin)])


class StatusOut(BaseModel):
    at: datetime
    ok: bool
    message: str
    trigger: str


class SettingsOut(BaseModel):
    router_url: str
    username: str
    has_password: bool
    config_name: str
    profile_id: int | None
    auto_push: bool
    status: StatusOut | None


class SettingsIn(BaseModel):
    router_url: str = Field(max_length=200)
    username: str = Field(max_length=100)
    password: str | None = Field(default=None, max_length=200)  # 留空表示不修改
    config_name: str = Field(max_length=200)
    profile_id: int | None = None
    auto_push: bool = False

    @field_validator("router_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return normalize_router_url(v)

    @field_validator("config_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        return v[:-5] if v.endswith(".yaml") else v[:-4] if v.endswith(".yml") else v


class ActionOut(BaseModel):
    ok: bool
    message: str


def _pusher(request: Request) -> OpenClashPusher:
    return request.app.state.openclash


def _status_out(s: PushStatus | None) -> StatusOut | None:
    return StatusOut(at=s.at, ok=s.ok, message=s.message, trigger=s.trigger) if s else None


def _settings_out(session, pusher: OpenClashPusher) -> SettingsOut:
    cfg = load_config(session)
    return SettingsOut(router_url=cfg.router_url, username=cfg.username, has_password=bool(cfg.password),
                       config_name=cfg.config_name, profile_id=cfg.profile_id, auto_push=cfg.auto_push,
                       status=_status_out(pusher.status))


@router.get("/settings", response_model=SettingsOut)
def get_settings(session: SessionDep, request: Request) -> SettingsOut:
    return _settings_out(session, _pusher(request))


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, session: SessionDep, request: Request) -> SettingsOut:
    cfg = load_config(session)
    data = body.model_dump(exclude={"password"})
    if body.password:
        data["password"] = body.password
    save_config(session, cfg.model_copy(update=data))
    pusher = _pusher(request)
    pusher.notify_changed()  # 开启自动推送时，若方案内容与上次推送不同会立即推一次
    return _settings_out(session, pusher)


@router.post("/test", response_model=ActionOut)
def test(session: SessionDep, http: HttpDep) -> ActionOut:
    try:
        return ActionOut(ok=True, message=check_login(http, load_config(session)))
    except OpenClashError as e:
        return ActionOut(ok=False, message=str(e))


@router.post("/push", response_model=StatusOut)
def push(request: Request) -> StatusOut:
    status = _pusher(request).push_now()
    return _status_out(status)
