"""公开订阅接口：客户端用 token 拉取渲染后的配置。"""

import logging
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session, select

from routeforge.api.deps import CacheDep, SessionDep
from routeforge.cache import RenderCache
from routeforge.db.models import ProfileRow, Source, utcnow
from routeforge.renderers import RENDERERS
from routeforge.services.render import render_profile
from routeforge.sources.fetch import format_userinfo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["subscribe"])


@dataclass(frozen=True)
class CachedSub:
    content: str
    content_type: str
    file_ext: str
    userinfo: str | None


@router.get("/sub/{token}")
def subscribe(token: str, session: SessionDep, cache: CacheDep, target: str = "mihomo") -> Response:
    row = session.exec(select(ProfileRow).where(ProfileRow.token == token)).first()
    if row is None:
        raise HTTPException(status_code=404)
    if target not in RENDERERS:
        raise HTTPException(status_code=400, detail=f"不支持的目标格式：{target}")

    key = (row.id, target)
    sub = cache.get(key) or _render_or_fallback(session, row, target, cache, key)
    if sub is None:
        return PlainTextResponse("方案配置有误且没有可用的历史版本，请在管理界面检查方案", status_code=500)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.name, safe='')}.{sub.file_ext}",
        "profile-update-interval": "24",
    }
    if sub.userinfo:
        headers["subscription-userinfo"] = sub.userinfo
    return Response(content=sub.content, media_type=sub.content_type, headers=headers)


def _render_or_fallback(session: Session, row: ProfileRow, target: str, cache: RenderCache, key) -> CachedSub | None:
    try:
        outcome = render_profile(session, row.to_profile(), target)
    except Exception:
        logger.exception("渲染方案 #%s（%s）出错，回退到历史版本", row.id, target)
        outcome = None
    if outcome is not None and outcome.result is not None:
        r = outcome.result
        entry = {"content": r.content, "content_type": r.content_type, "file_ext": r.file_ext}
        if (row.last_good or {}).get(target) != entry:
            try:
                row.last_good = {**(row.last_good or {}), target: entry}
                row.last_good_at = utcnow()
                session.add(row)
                session.commit()
            except Exception:
                logger.exception("保存方案 #%s 的最近可用版本失败", row.id)
                session.rollback()
        sub = CachedSub(r.content, r.content_type, r.file_ext, _userinfo_header(session, outcome.source_ids))
        cache.put(key, sub)
        return sub
    saved = (row.last_good or {}).get(target)
    if saved is None:
        return None
    return CachedSub(saved["content"], saved["content_type"], saved["file_ext"], None)


def _userinfo_header(session: Session, source_ids: list[int]) -> str | None:
    if len(source_ids) != 1:
        return None
    source = session.get(Source, source_ids[0])
    if source is None or not source.userinfo:
        return None
    return format_userinfo(source.userinfo)
