import httpx

ADMIN_PASSWORD = "secret-pw"


def mock_client(routes: dict) -> httpx.Client:
    """routes: url -> httpx.Response | Exception | (request -> httpx.Response)"""

    def handler(request: httpx.Request) -> httpx.Response:
        route = routes.get(str(request.url))
        if route is None:
            return httpx.Response(404)
        if isinstance(route, Exception):
            raise route
        if callable(route):
            return route(request)
        return route

    return httpx.Client(transport=httpx.MockTransport(handler))


def import_text(admin, sid, text):
    """手动节点源导入：先解析，再导入全部解析结果。返回 (解析结果, 导入响应)。"""
    parsed = admin.post(f"/api/sources/{sid}/nodes/parse", json={"text": text}).json()
    items = [{"name": n["name"], "config": n["config"]} for n in parsed["nodes"]]
    return parsed, admin.post(f"/api/sources/{sid}/nodes/import", json={"nodes": items})
