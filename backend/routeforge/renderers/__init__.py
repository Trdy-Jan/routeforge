from routeforge.renderers.base import Renderer, RenderResult
from routeforge.renderers.mihomo import MihomoRenderer, ShadowrocketRenderer

RENDERERS: dict[str, Renderer] = {
    "mihomo": MihomoRenderer(),
    "shadowrocket": ShadowrocketRenderer(),
}


def get_renderer(target: str) -> Renderer:
    return RENDERERS[target]


__all__ = ["RENDERERS", "Renderer", "RenderResult", "get_renderer"]
