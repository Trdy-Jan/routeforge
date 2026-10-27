"""托管前端构建产物（单页应用）。"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_RESERVED_PREFIXES = ("api/", "sub/")


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()
    index = root / "index.html"
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(_RESERVED_PREFIXES) or path in ("api", "sub"):
            raise HTTPException(status_code=404)
        if path:
            try:
                candidate = (root / path).resolve()
                if candidate.is_relative_to(root) and candidate.is_file():
                    return FileResponse(candidate)
            except (OSError, ValueError):
                pass
        return FileResponse(index)
