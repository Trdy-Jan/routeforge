"""管理员密码、会话密钥与登录限速。"""

import secrets
import time
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlmodel import Session

from routeforge.db.models import Setting

ADMIN_HASH_KEY = "admin_password_hash"
SESSION_SECRET_KEY = "session_secret"
_hasher = PasswordHasher()


class ConfigError(RuntimeError):
    pass


def bootstrap_secrets(session: Session, admin_password: str | None) -> str:
    if session.get(Setting, ADMIN_HASH_KEY) is None:
        if not admin_password:
            raise ConfigError("首次启动必须设置环境变量 ROUTEFORGE_ADMIN_PASSWORD")
        session.add(Setting(key=ADMIN_HASH_KEY, value=_hasher.hash(admin_password)))
        new_password = True
    else:
        new_password = False
    secret = session.get(Setting, SESSION_SECRET_KEY)
    if secret is None:
        secret = Setting(key=SESSION_SECRET_KEY, value=secrets.token_urlsafe(32))
    elif new_password:  # 密码重置后让旧会话全部失效
        secret.value = secrets.token_urlsafe(32)
    session.add(secret)
    session.commit()
    return secret.value


def verify_password(session: Session, password: str) -> bool:
    row = session.get(Setting, ADMIN_HASH_KEY)
    if row is None:
        return False
    try:
        return _hasher.verify(row.value, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


class LoginLimiter:
    """滑动窗口内失败 max_failures 次后锁定 lockout 秒。仅内存，单进程有效。"""

    def __init__(self, max_failures: int = 5, window: float = 300, lockout: float = 300,
                 clock: Callable[[], float] = time.monotonic):
        self.max_failures = max_failures
        self.window = window
        self.lockout = lockout
        self.clock = clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def is_locked(self, key: str) -> bool:
        return self._locked_until.get(key, 0) > self.clock()

    def record_failure(self, key: str) -> None:
        now = self.clock()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        recent.append(now)
        if len(recent) >= self.max_failures:
            self._locked_until[key] = now + self.lockout
            recent = []
        self._failures[key] = recent

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)
