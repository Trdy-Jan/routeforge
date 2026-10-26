from dataclasses import dataclass, field
from typing import Protocol

from routeforge.ir.resolved import ResolvedProfile


@dataclass
class RenderResult:
    content: str
    content_type: str
    file_ext: str
    warnings: list[str] = field(default_factory=list)


class Renderer(Protocol):
    target: str

    def render(self, profile: ResolvedProfile) -> RenderResult: ...
