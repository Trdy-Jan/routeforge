from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from routeforge.api.deps import CacheDep, SessionDep, require_admin
from routeforge.cache import RenderCache
from routeforge.db.models import ProfileRow, new_token
from routeforge.ir.profile import Profile
from routeforge.renderers import RENDERERS
from routeforge.services.render import render_profile
from routeforge.templates import apply_template, load_templates

router = APIRouter(prefix="/api/profiles", tags=["profiles"], dependencies=[Depends(require_admin)])


class ProfileSummary(BaseModel):
    id: int
    name: str
    token: str


class ProfileOut(BaseModel):
    id: int
    token: str
    last_good_at: datetime | None
    profile: Profile


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApplyTemplateIn(BaseModel):
    template_id: str


class ApplyTemplateOut(BaseModel):
    profile: ProfileOut
    notes: list[str]


class PreviewOut(BaseModel):
    ok: bool
    content: str | None
    errors: list[str]
    warnings: list[str]


def _get(session: Session, profile_id: int) -> ProfileRow:
    row = session.get(ProfileRow, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    return row


def _out(row: ProfileRow) -> ProfileOut:
    return ProfileOut(id=row.id, token=row.token, last_good_at=row.last_good_at, profile=row.to_profile())


def _save(session: Session, row: ProfileRow, cache: RenderCache) -> ProfileRow:
    session.add(row)
    session.commit()
    session.refresh(row)
    cache.invalidate()
    return row


@router.get("")
def list_profiles(session: SessionDep) -> list[ProfileSummary]:
    rows = session.exec(select(ProfileRow).order_by(ProfileRow.id)).all()
    return [ProfileSummary(id=r.id, name=r.name, token=r.token) for r in rows]


@router.post("", status_code=201)
def create_profile(body: ProfileCreate, session: SessionDep, cache: CacheDep) -> ProfileOut:
    return _out(_save(session, ProfileRow.new(body.name), cache))


@router.get("/{profile_id}")
def get_profile(profile_id: int, session: SessionDep) -> ProfileOut:
    return _out(_get(session, profile_id))


@router.put("/{profile_id}")
def update_profile(profile_id: int, body: Profile, session: SessionDep, cache: CacheDep) -> ProfileOut:
    row = _get(session, profile_id)
    row.set_profile(body)
    return _out(_save(session, row, cache))


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, session: SessionDep, cache: CacheDep) -> Response:
    session.delete(_get(session, profile_id))
    session.commit()
    cache.invalidate()
    return Response(status_code=204)


@router.post("/{profile_id}/apply-template")
def apply(profile_id: int, body: ApplyTemplateIn, session: SessionDep, cache: CacheDep) -> ApplyTemplateOut:
    row = _get(session, profile_id)
    template = load_templates().get(body.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    profile, notes = apply_template(row.to_profile(), template)
    row.set_profile(profile)
    return ApplyTemplateOut(profile=_out(_save(session, row, cache)), notes=notes)


@router.post("/{profile_id}/rotate-token")
def rotate_token(profile_id: int, session: SessionDep, cache: CacheDep) -> ProfileOut:
    row = _get(session, profile_id)
    row.token = new_token()
    return _out(_save(session, row, cache))


@router.get("/{profile_id}/preview")
def preview(profile_id: int, session: SessionDep, target: str = "mihomo") -> PreviewOut:
    row = _get(session, profile_id)
    if target not in RENDERERS:
        raise HTTPException(status_code=400, detail=f"不支持的目标格式：{target}")
    outcome = render_profile(session, row.to_profile(), target)
    return PreviewOut(
        ok=outcome.ok,
        content=outcome.result.content if outcome.result else None,
        errors=outcome.errors,
        warnings=outcome.warnings,
    )
