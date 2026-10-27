from routeforge.renderers.base import Renderer, RenderResult
from routeforge.renderers.mihomo import MihomoRenderer

RENDERERS: dict[str, Renderer] = {
    "mihomo": MihomoRenderer(),
}


def get_renderer(target: str) -> Renderer:
    return RENDERERS[target]


__all__ = ["RENDERERS", "Renderer", "RenderResult", "get_renderer"]
