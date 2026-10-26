"""方案 → 目标格式：加载节点库、resolve、渲染。"""

from dataclasses import dataclass, field

from sqlmodel import Session

from routeforge.ir.profile import Profile
from routeforge.renderers import RenderResult, get_renderer
from routeforge.resolver import resolve
from routeforge.services.library import load_library


@dataclass
class RenderOutcome:
    result: RenderResult | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_ids: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.result is not None


def render_profile(session: Session, profile: Profile, target: str) -> RenderOutcome:
    renderer = get_renderer(target)
    resolved = resolve(profile, load_library(session))
    if not resolved.ok:
        return RenderOutcome(result=None, errors=resolved.errors, warnings=resolved.warnings)
    result = renderer.render(resolved.profile)
    return RenderOutcome(
        result=result,
        warnings=resolved.warnings + result.warnings,
        source_ids=resolved.profile.source_ids,
    )
