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
