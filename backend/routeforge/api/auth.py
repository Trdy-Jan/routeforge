from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from routeforge.api.deps import SessionDep, require_admin
from routeforge.auth import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str = Field(max_length=1024)


@router.post("/login")
def login(body: LoginIn, request: Request, session: SessionDep) -> dict:
    limiter = request.app.state.limiter
    key = request.client.host if request.client else "unknown"
    if limiter.is_locked(key):
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 5 分钟后再试")
    if not verify_password(session, body.password):
        limiter.record_failure(key)
        raise HTTPException(status_code=401, detail="密码错误")
    limiter.reset(key)
    request.session["admin"] = True
    return {"ok": True}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_admin)])
def me() -> dict:
    return {"admin": True}
