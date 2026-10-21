"""Local web UI (spec 40): one static page plus three JSON/media routes over M1's Store.
Indexed text is untrusted media text (Y1): it leaves this module only as JSON values, and the
page writes it with textContent. Media is served only by asset ID, from the paths the runner
recorded (E7 scan_assets); no client string is ever used as a path."""

from __future__ import annotations

import dataclasses
import mimetypes
import os
import re
import stat
import threading
from collections.abc import Awaitable, Callable, Mapping, Sequence
from importlib import resources
from pathlib import Path, PurePath
from typing import Annotated, Final, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from tapesift.schema.records import Modality
from tapesift.store.types import Store

ASSET_ID_RE: Final = re.compile(r"(?:tsid1|sha256):[0-9a-f]{64}")  # ADR 0012; fullmatch
DEFAULT_K: Final = 20
MAX_K: Final = 100
MAX_QUERY_CHARS: Final = 1000
STATIC_FILES: Final = {
    "app.js": "text/javascript; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
}
CSP: Final = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; "
    "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS: Final[Mapping[str, str]] = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}
LOOPBACK_HOSTS: Final = ("127.0.0.1", "localhost", "[::1]")  # Host-header names, card 4

_NOT_FOUND: Final = "not found"


def _static(name: str) -> bytes:
    return (resources.files("tapesift.serve") / "static" / name).read_bytes()


def create_app(
    store: Store,
    scan: Callable[[], Mapping[str, str]],
    *,
    allowed_hosts: Sequence[str],
) -> FastAPI:
    """scan() returns asset ID -> recorded absolute path (cli/serve.py passes
    lambda: scan_assets(out_dir / "assets")). allowed_hosts goes to TrustedHostMiddleware;
    ["*"] turns the check off."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    page = _static("index.html")
    static = {name: _static(name) for name in STATIC_FILES}
    media = dict(scan())
    # ponytail: full rescan on a miss; ceiling: thousands of large asset JSONs; upgrade: an index
    # of path by ID written by the runner.
    lock = threading.Lock()
    # ponytail: one search at a time; fine for one local user.

    def lookup(asset_id: str) -> str | None:
        nonlocal media
        path = media.get(asset_id)
        if path is None:
            media = dict(scan())
            path = media.get(asset_id)
        return path

    @app.get("/")
    def index() -> Response:
        return Response(page, media_type="text/html; charset=utf-8")

    @app.get("/static/app.js")
    @app.get("/static/app.css")
    def static_file(request: Request) -> Response:
        name = request.url.path.rsplit("/", 1)[1]
        return Response(static[name], media_type=STATIC_FILES[name])

    @app.get("/api/search")
    def search(
        q: Annotated[str, Query(max_length=MAX_QUERY_CHARS)],
        k: Annotated[int, Query(ge=1, le=MAX_K)] = DEFAULT_K,
        modality: Literal["any", "speech", "visual"] = "any",
        asset: str | None = None,
    ) -> JSONResponse:
        if q.strip() == "":
            raise HTTPException(422, "q: must not be blank")
        if asset is not None and not ASSET_ID_RE.fullmatch(asset):
            raise HTTPException(422, "asset: not an asset ID")
        with lock:
            hits = store.search(
                q,
                k,
                modality=None if modality == "any" else Modality(modality),
                asset_id=asset,
            )
        return JSONResponse({"query": q, "hits": [dataclasses.asdict(h) for h in hits]})

    @app.get("/api/assets")
    def assets() -> JSONResponse:
        rows = sorted((PurePath(p).name, aid) for aid, p in scan().items())
        return JSONResponse({"assets": [{"asset_id": aid, "name": n} for n, aid in rows]})

    @app.get("/media/{asset_id}")
    def media_file(asset_id: str) -> FileResponse:
        # Every failure is the same 404, so the response never shows whether a path exists.
        if not ASSET_ID_RE.fullmatch(asset_id):
            raise HTTPException(404, _NOT_FOUND)
        path = lookup(asset_id)
        if path is None or not Path(path).is_absolute():
            raise HTTPException(404, _NOT_FOUND)
        try:
            st = os.stat(path)  # noqa: PTH116  (a stat_result is what FileResponse takes)
        except OSError:
            raise HTTPException(404, _NOT_FOUND) from None
        if not stat.S_ISREG(st.st_mode):
            raise HTTPException(404, _NOT_FOUND)
        return FileResponse(
            path,
            media_type=mimetypes.guess_type(path)[0] or "application/octet-stream",
            stat_result=st,
            content_disposition_type="inline",
        )

    return app
