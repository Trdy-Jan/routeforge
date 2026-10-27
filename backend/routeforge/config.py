import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_FALSY = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    admin_password: str | None
    cookie_secure: bool = True
    static_dir: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        data_dir = Path(env.get("ROUTEFORGE_DATA_DIR", "./data"))
        static = env.get("ROUTEFORGE_STATIC_DIR")
        return cls(
            data_dir=data_dir,
            database_url=f"sqlite:///{(data_dir / 'routeforge.db').as_posix()}",
            admin_password=env.get("ROUTEFORGE_ADMIN_PASSWORD") or None,
            cookie_secure=env.get("ROUTEFORGE_COOKIE_SECURE", "true").strip().lower() not in _FALSY,
            static_dir=Path(static) if static else None,
        )
