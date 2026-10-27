from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from routeforge.cache import RenderCache


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_cache(request: Request) -> RenderCache:
    return request.app.state.cache


def get_http(request: Request) -> httpx.Client:
    return request.app.state.http


def require_admin(request: Request) -> None:
    if not request.session.get("admin"):
        raise HTTPException(status_code=401, detail="未登录")


SessionDep = Annotated[Session, Depends(get_session)]
CacheDep = Annotated[RenderCache, Depends(get_cache)]
HttpDep = Annotated[httpx.Client, Depends(get_http)]
