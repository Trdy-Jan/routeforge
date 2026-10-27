"""启动入口：python -m routeforge"""

import logging
import os
import sys

import uvicorn

from routeforge.app import create_app
from routeforge.auth import ConfigError
from routeforge.config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        app = create_app(Settings.from_env())
    except ConfigError as e:
        print(f"启动失败：{e}", file=sys.stderr)
        raise SystemExit(1) from e
    uvicorn.run(
        app,
        host=os.environ.get("ROUTEFORGE_HOST", "0.0.0.0"),
        port=int(os.environ.get("ROUTEFORGE_PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("ROUTEFORGE_FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )


if __name__ == "__main__":
    main()
