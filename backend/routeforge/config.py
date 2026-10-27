import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_FALSY = {"0", "false", "no", "off"}
_TRUTHY = {"1", "true", "yes", "on"}


def _parse_cookie_secure(raw: str) -> bool | None:
    """true/false 强制开关；auto（默认）按请求是否为 HTTPS 决定。"""
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    admin_password: str | None
    cookie_secure: bool | None = None  # None = auto
    static_dir: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        data_dir = Path(env.get("ROUTEFORGE_DATA_DIR", "./data"))
        static = env.get("ROUTEFORGE_STATIC_DIR")
        return cls(
            data_dir=data_dir,
            database_url=f"sqlite:///{(data_dir / 'routeforge.db').as_posix()}",
            admin_password=env.get("ROUTEFORGE_ADMIN_PASSWORD") or None,
            cookie_secure=_parse_cookie_secure(env.get("ROUTEFORGE_COOKIE_SECURE", "auto")),
            static_dir=Path(static) if static else None,
        )
