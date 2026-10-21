# 40. Local web UI: `tapesift serve` (U1)

Issue: none yet (lead files it; the spec number is 40)   Lane: Core   Status: draft
Owner change (2026-10-20): tapesift must not be terminal-only. The local UI moves forward from v0.3 (S4) into the MVP. The HTTP API in S4 builds on this later.

## Summary
- `tapesift serve` starts a local web page. It has a search box, a result list with times and a thumbnail, a player, and filters for file and for speech or visual.
- Clicking a result plays the source file at that moment. The server sends the file with HTTP range requests.
- The stack is FastAPI and uvicorn (the planned `serve` extra), plus one static HTML page, one JS file and one CSS file. There is no React and no build step.
- There is no auth. The server binds 127.0.0.1 by default. Any other address needs an explicit `--host` and logs a warning.
- The server sends only files that are indexed assets, looked up by asset ID. It never takes a path from the client. Every string from the index is untrusted: the page writes it with `textContent` only.

## Goal
After this lands, `tapesift serve [--config FILE] [--out DIR] [--host H] [--port P]` serves a local UI. It searches the index in `out_dir` through M1's `Store.search` and plays hits from `/media/<asset_id>`.

## Read first
- docs/specs/25-m1-interfaces.md (approved): `Store.search`, `Hit`, `Modality`, card 3 (the `{"query", "hits"}` shape, `trust`, `media_text` kept separate), R6 (lazy imports), R7 (`load_config`), the `LanceStore(cfg, embedder)` and `OnnxEmbedder(cfg)` constructors, `MemoryStore` and `FakeEmbedder`.
- docs/specs/30-runner.md (approved): `runner.run.scan_assets(assets_dir) -> dict[str, str]` (asset ID to the recorded `asset.path`), card 5 (the stored `asset.path` is absolute), and the layout `out_dir/assets/`, `out_dir/store/`.
- docs/specs/29-search.md (draft, being finalized): card 6 (`StoreError`, exit 2), the no-index check, the `--out` flag (card 2), and `hms` and `qt` in `render`.
- docs/spec.md: lines 198 (extras), 212 (exit codes), 237 (the `serve` row), S4 (377), Y1 (513, untrusted media text), Y3 (no telemetry and no network calls).
- ADR 0008: never load real weights on the laptop. Laptop tests use `MemoryStore(FakeEmbedder())`.
- Code: `src/tapesift/cli/__init__.py` (`ExitCode`, `app`), `scripts/cloud/modal_gpu.py` (the Modal pattern).
- **Observed by the planner on 2026-10-20.** Scratch venv under /tmp; nothing in the repo.
  - **Versions.** PyPI has fastapi 0.156.4 (MIT), uvicorn 0.54.0 (BSD-3-Clause) and starlette 1.9.0 (BSD-3-Clause).
  - **New packages in a plain install.** fastapi brings `opentelemetry-api` 1.45.1 (Apache-2.0) and `annotated-doc`. uvicorn brings `click` and `h11`, both already locked. starlette's `anyio` is already locked.
  - **opentelemetry-api.** It is imported by fastapi. With no SDK or exporter installed, it sends nothing.
  - **Starlette `FileResponse` handles ranges.** On a 10,240-byte file:
    - no Range header gives 200 with `accept-ranges: bytes`;
    - `bytes=100-199` gives 206, `content-range: bytes 100-199/10240` and 100 bytes;
    - `bytes=10000-` gives 206 and 240 bytes;
    - `bytes=20000-30000` gives 416 and `bytes */10240`;
    - a multi-range request gives 206 `multipart/byteranges`.
  - **The test client.** With starlette 1.9.0, `starlette.testclient` imported with `httpx` raises `StarletteDeprecationWarning: ... install httpx2 instead`, and `filterwarnings = error` turns that into a failure. With `httpx2` 2.15.1 (BSD-3-Clause), `python -W error` runs clean.
  - **Host-header parsing.** `TrustedHostMiddleware` parses the Host header with `parse_host_header`:
    - `127.0.0.1:8765` becomes `127.0.0.1`, and `[::1]:8765` becomes `[::1]`;
    - a bare `::1` gives None, which returns 400.
  - **Signatures.** `uvicorn.Server.run(sockets=...)` exists. `uvicorn.Config` takes `server_header`, `access_log`, `proxy_headers`, `timeout_keep_alive` and `lifespan`.
  - **AV1 decode.** PyAV 19.0.1's bundled FFmpeg decodes AV1 (`libdav1d`), so index and playback agree on AV1 mp4.
  - **Pricing.** Modal (modal.com/pricing, 2026-10-20): $0.0000131 per physical core-second and $0.00000222 per GiB-second. A 2-core, 8 GiB box is about $0.16 per hour.

**Name dependencies.**
- Every name here comes from M1 or E7, both approved, except one: `tapesift.store.lance.StoreError` comes from E6's draft (29-search card 6). E7 (approved) already depends on it with the same caveat. If E6 card 6 changes, `cli/serve.py` step 4 follows it.
- No other unapproved name is used.
- This spec does not call `tapesift.cli.search.load_embedder` or `open_store` (E6 draft names). It builds the store from M1's constructors.

## Scope
May change:
- New files:
  - `src/tapesift/serve/__init__.py` (a one-line docstring);
  - `src/tapesift/serve/app.py`;
  - `src/tapesift/serve/static/index.html`, `app.js` and `app.css`, which ship as package data with no `pyproject.toml` entry (the same mechanism as E5's schema file).
- New: `src/tapesift/cli/serve.py`.
- `src/tapesift/cli/__init__.py`: two lines after the other command registrations and before `def main()`, exactly:
  ```python
  from tapesift.cli.serve import serve  # noqa: E402  (needs ExitCode and app above)
  app.command()(serve)
  ```
- New tests: `tests/unit/test_serve_app.py`, `tests/unit/test_serve_cli.py`, `tests/smoke/test_serve_http.py`.
- New: `scripts/cloud/modal_ui.py`, a real-model, real-browser check on Modal (card 6).
- `pyproject.toml` and `uv.lock`: the `serve` extra and the dev dependency in card 2. Nothing else.
- `THIRD_PARTY.md`: the rows in card 2.
- `docs/spec.md`: lines 198 and 237, and one backlog line, exactly as under "docs/spec.md edits".
- `CHANGELOG.md`: one line under Unreleased, Added: ``- `tapesift serve`: a local web page to search the index, filter by file and by speech or visual, and play each hit from its timestamp. It binds 127.0.0.1 by default, serves only indexed files, and treats indexed text as untrusted. Needs `tapesift[serve]` (FastAPI, uvicorn).``

Must not touch:
- M1's interface files: `src/tapesift/{config,hub,warning_codes}.py`, `src/tapesift/*/types.py`, `src/tapesift/schema/**`, `tests/fakes.py`, `tests/contract/**`.
- `src/tapesift/store/**` and `src/tapesift/vision/**` (E4, E6), `src/tapesift/runner/**` and `src/tapesift/pipeline/**` (E7), `src/tapesift/cli/{index,search,doctor}.py`, `src/tapesift/media/**`.
- `tests/fixtures/**`, existing tests, `.github/**`, `Makefile`, `README.md` (E9), `AGENTS.md`, `CLAUDE.md`.

## Interfaces touched
Before: there is no `serve` package and no `serve` command. After: the files below. Docstrings and comments are part of the contract.

### `src/tapesift/serve/app.py`
```python
"""Local web UI (spec 40): one static page plus three JSON/media routes over M1's Store.
Indexed text is untrusted media text (Y1): it leaves this module only as JSON values, and the
page writes it with textContent. Media is served only by asset ID, from the paths the runner
recorded (E7 scan_assets); no client string is ever used as a path."""

ASSET_ID_RE: Final = re.compile(r"(?:tsid1|sha256):[0-9a-f]{64}")  # ADR 0012; fullmatch
DEFAULT_K: Final = 20
MAX_K: Final = 100
MAX_QUERY_CHARS: Final = 1000
STATIC_FILES: Final = {"app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}
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


def create_app(
    store: Store,
    scan: Callable[[], Mapping[str, str]],
    *,
    allowed_hosts: Sequence[str],
) -> FastAPI:
    """scan() returns asset ID -> recorded absolute path (cli/serve.py passes
    lambda: scan_assets(out_dir / "assets")). allowed_hosts goes to TrustedHostMiddleware;
    ["*"] turns the check off."""
```
Behaviour of `create_app`:
- `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`. Swagger UI would load scripts from a CDN, which breaks Y3 and the CSP.
- The static files are read once, with `importlib.resources.files("tapesift.serve") / "static" / name`, when the app is built.
- Middleware:
  - `TrustedHostMiddleware(allowed_hosts=list(allowed_hosts))`;
  - an `http` middleware that sets every `SECURITY_HEADERS` entry on every response, errors and 404s included.
- **The media map.** `media = dict(scan())` at build time. `lookup(aid)` returns `media.get(aid)`. On a miss, it replaces `media` with `dict(scan())` once and tries again. `# ponytail: full rescan on a miss; ceiling: thousands of large asset JSONs; upgrade: an index of path by ID written by the runner.`
- `lock = threading.Lock()` wraps every `store.search` call. `# ponytail: one search at a time; fine for one local user.`

Routes. They are exactly these, and every other path is 404.

| Route | Response |
| --- | --- |
| `GET /` | `index.html`, `text/html; charset=utf-8` |
| `GET /static/app.js`, `GET /static/app.css` | The file, with its type from `STATIC_FILES`. These are explicit routes: no `StaticFiles` mount and no path parameter |
| `GET /api/search` | See below |
| `GET /api/assets` | `{"assets": [{"asset_id": id, "name": PurePath(path).name} ...]}` from a fresh `scan()`, sorted by `(name, asset_id)`. The page fills the file filter from this |
| `GET /media/{asset_id}` | See below |

**`GET /api/search`.** The parameters are:
- `q: str = Query(max_length=MAX_QUERY_CHARS)`;
- `k: int = Query(DEFAULT_K, ge=1, le=MAX_K)`;
- `modality: Literal["any", "speech", "visual"] = "any"`;
- `asset: str | None = None`.

The rules:
1. `q.strip() == ""` raises `HTTPException(422, "q: must not be blank")`.
2. `asset` set and not `ASSET_ID_RE.fullmatch(asset)` raises `HTTPException(422, "asset: not an asset ID")`.
3. FastAPI's own validation gives 422 for the other bad values.
4. None of these failures calls the store.
5. Then `hits = store.search(q, k, modality=None if modality == "any" else Modality(modality), asset_id=asset)`, under the lock.
6. The response is `JSONResponse({"query": q, "hits": [dataclasses.asdict(h) for h in hits]})`. That is M1 card 3's shape, the same document as `tapesift search --json`, with `media_text` as a JSON list.

**`GET /media/{asset_id}`.** Any failure below gives the same `404 {"detail": "not found"}`, so the response never shows whether a path exists.
1. `ASSET_ID_RE.fullmatch(asset_id)`, or 404.
2. `p = lookup(asset_id)`, or 404.
3. `Path(p).is_absolute()`, or 404. E7 records absolute paths (card 5), so a relative one means a tampered JSON.
4. `st = os.stat(p)`. An `OSError` gives 404. `not stat.S_ISREG(st.st_mode)` gives 404: no directories, FIFOs or devices (#21's rule).
5. `FileResponse(p, media_type=mimetypes.guess_type(p)[0] or "application/octet-stream", stat_result=st, content_disposition_type="inline")`, with no `filename`, so no header carries the file name. Starlette handles `Range`: 206, 416 and multipart.

### `src/tapesift/serve/static/` (the page; the contract is the rules, not the markup)
- **`index.html`.** No templating: the server never puts data into HTML. It holds:
  - `<meta charset="utf-8">`, a viewport meta, `<link rel="stylesheet" href="/static/app.css">` and `<script src="/static/app.js" defer></script>`;
  - a `<form>` with a labelled `<input type="search" name="q" required maxlength="1000">`, a labelled `<select name="modality">` with any, speech and visual, a labelled `<select name="asset">` whose first option is "All files" (value `""`), and a submit `<button>`;
  - `<p id="status" role="status">`, `<video id="player" controls>` and `<ol id="results">`;
  - a footer line: "Result text comes from your media files. Treat it as untrusted."
- **`app.js`.**
  - On load, it fetches `/api/assets` and appends one `<option>` per asset (`value = asset_id`, `textContent = name`).
  - On submit, it fetches `/api/search` with `URLSearchParams` (`q`, `k=20`, `modality`, and `asset` if set) and renders one `<li>` per hit:
    - a muted thumbnail `<video preload="metadata" playsinline aria-hidden="true">` with `src = "/media/" + encodeURIComponent(asset_id) + "#t=" + start_s` (card 5);
    - a `<button>` with `aria-label` "Play <name> at <time>" and visible text `<time>` (`hms(start_s)`, or `hms(start_s) + "–" + hms(end_s)` for speech), then the modality, the score to 3 places, and the file name;
    - a `<p>` with `text`;
    - when `media_text` is non-empty, a `<p class="untrusted">` whose label is "On-screen text (from the video, untrusted): ", followed by the items, each in double quotes and joined with ", ".
  - Clicking the button plays the hit:
    - if the player already holds that asset, set `currentTime = start_s`;
    - otherwise set `src` to the media URL with `#t=<start_s>`;
    - then `play()`, with the rejected promise ignored.
  - Player `error` sets the status to "This browser can't play this file (container or codec)."
  - Status texts: "Searching…", "1 result", "N results", "No results", and "Search failed (HTTP <code>)".
  - `hms(t)` is the CLI's formula (29-search): `cs = Math.floor(t * 100 + 0.5)`, giving `H:MM:SS.cc`.
- **Hard rules** (tested statically, test 16):
  - Data reaches the DOM only through `textContent`, `value`, `setAttribute("aria-label" | "src" | "class", …)` and `createElement`.
  - These never appear in any static file: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function`, `setTimeout("` or `setInterval("` with a string argument, `on<event>=` attributes, inline `<script>` bodies, `<style>` blocks, and any `http://`, `https://` or protocol-relative `//host` URL.
  - Listeners use `addEventListener`.
  - No storage APIs: nothing persists queries.
- **`app.css`.** Plain CSS. Results are a vertical list. Thumbnails are 160 px wide. The `.untrusted` style is visibly different (an italic, muted colour, with a left border).

### `src/tapesift/cli/serve.py`
```python
"""`tapesift serve`: build the store from the index in out_dir and serve the local UI (spec 40).
Module-level imports: stdlib, typer, tapesift.cli and tapesift.config only. fastapi, uvicorn,
lancedb and the embedder are imported inside the command (R6), so `tapesift --help` works
without the serve extra."""

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8765


def serve_available() -> bool:
    """True when fastapi and uvicorn are importable (importlib.util.find_spec)."""


def is_loopback(host: str) -> bool:
    """host == "localhost", or ipaddress.ip_address(host).is_loopback; a ValueError is False."""


def _run(app: FastAPI, sock: socket.socket) -> None:
    """uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False,
    server_header=False, proxy_headers=False, timeout_keep_alive=5, lifespan="off")).run(
    sockets=[sock]). Tests patch this module attribute."""


def serve(
    config: Annotated[Path | None, typer.Option("--config", help="Config file (default ./tapesift.toml).")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Index folder, as given to tapesift index --out.")] = None,
    host: Annotated[str, typer.Option("--host", help="Address to listen on. Default 127.0.0.1: this machine only.")] = DEFAULT_HOST,
    port: Annotated[int, typer.Option("--port", min=1, max=65535, help="Port to listen on.")] = DEFAULT_PORT,
) -> None:
    """Open a local web page to search the index and play each moment."""
```
The flow. Errors go to stderr as `error: <message>`.
1. `not serve_available()`: `error: tapesift serve needs the serve extra: install "tapesift[serve]"`, exit 3.
2. `cfg = load_config(config, out_dir=out)`. `ConfigError`: exit 2.
3. `not (cfg.out_dir / "store").is_dir()`: `error: no index at {cfg.out_dir}: run "tapesift index" first, or pass --out`, exit 2. This is E6's exact message, checked before any model loads.
4. `store = LanceStore(cfg, OnnxEmbedder(cfg))`, with local imports from `tapesift.store.lance` and `tapesift.vision.embed` (M1's constructors). `ModelLoadError`: exit 3. `StoreError`: exit 2.
5. **Bind.**
   - `family = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][0]`.
   - `sock = socket.create_server((host, port), family=family)`.
   - Any `OSError` (`gaierror` and "address in use" included) gives `error: cannot listen on {host}:{port}: {e.strerror or e}`, exit 2.
6. **Exposure (card 4).**
   - Loopback: `allowed = sorted({*LOOPBACK_HOSTS, h})`, where `h` is the host as it appears in a Host header (`[host]` for IPv6).
   - Otherwise:
     - `allowed = ["*"]`;
     - log a WARNING, exactly: `serving on {host}:{port} with no authentication: anyone who can reach this address can search the index and play every indexed file`.
7. `app = create_app(store, lambda: scan_assets(cfg.out_dir / "assets"), allowed_hosts=allowed)`, with `scan_assets` from `tapesift.runner.run` (E7).
8. Print the URL to stderr: `tapesift UI: http://{h}:{port}/  (Ctrl-C to stop)`. If `sys.stderr.isatty()` and the host is loopback, call `webbrowser.open(url)`. Its failure is ignored.
9. `_run(app, sock)`. Ctrl-C stops uvicorn cleanly, and the command exits 0.

### `scripts/cloud/modal_ui.py` (card 6; costs money; the lead asks the owner before each run)
- It follows the pattern of `modal_gpu.py`: the image `python:3.12-slim-trixie`, then `uv==0.11.27`, then the repo, then `uv sync --frozen --all-extras` (CPU torch on Linux comes from the lock).
- One function: `cpu=2`, `memory=8192`, `timeout=(minutes + 30) * 60`, `max_containers=1`, `retries=0`. Its inputs are `--paths` (repo-relative files; default `tests/fixtures/speech.mp4,tests/fixtures/burned_text.mp4,tests/fixtures/clean.mp4`), an optional `--video-url` with `--sha256`, and `--minutes 30`.
- With `--video-url`, it fetches the file inside the container with `urllib.request.urlopen(url, timeout=60)` and checks the sha256; a mismatch exits non-zero.
- It writes a config (`profile = "cpu"`, `[asr] model = "tiny"`), then runs `tapesift index <paths> --out /tmp/idx --config <it>`.
- Inside `with modal.forward(8765) as tunnel:`, it starts `tapesift serve --out /tmp/idx --host 0.0.0.0 --port 8765` as a subprocess and prints `tunnel.url`. It stops the server after `--minutes`, and every subprocess has a timeout.
- The non-loopback warning prints, as designed. The tunnel URL is unguessable but public, so use it only with public or test media.

### docs/spec.md edits
1. **Line 198.** `` | `serve` | FastAPI + uvicorn HTTP API | Not every user wants a server | `` becomes `` | `serve` | FastAPI + uvicorn: the local web UI (`tapesift serve`), later the HTTP API (S4) | Not every user wants a server | ``.
2. **Line 237.** The row becomes ``| `tapesift serve [--config FILE] [--out DIR] [--host] [--port]` | Local web UI: search, filter by file and modality, play each hit at its timestamp (owner, 2026-10-20). S4 adds `POST /index`, `GET /jobs/{id}` and OpenAPI docs | v0.1.x (UI); v0.3 (API) |``.
3. **The v0.1 backlog,** after the E9 line: ``- [ ] **U1** Local web UI, `tapesift serve` (owner, 2026-10-20; docs/specs/40-web-ui.md). Done when: on the fixture index, a search plays the hit at its timestamp in a browser, and untrusted text renders as text. *Lane: Core*``

## Acceptance
**Baseline.** U1 builds on main after E6 merges. Its PR leaves draft after E7 merges (it imports `scan_assets`). The builder states the base count `B passed, D deselected`.

**Test setup.**
- `tests/unit/test_serve_app.py` builds the app with `create_app(MemoryStore(FakeEmbedder()), scan, allowed_hosts=["testserver"])` and drives it with `fastapi.testclient.TestClient`. `scan` is a spy that returns the test's dict and counts its calls.
- It seeds two records:
  - **A**, `"tsid1:" + "a" * 64`, with the path `str(FIXTURES / "clean.mp4")` (absolute). It has utterances `(1.5, 4.25, "The quarterly pricing review starts at nine.")` and `(5.0, 8.0, "Revenue grew twelve percent.")`.
  - **B**, `"tsid1:" + "b" * 64`, with a `tmp_path` file. It has captions `Caption(2.0, "<script>alert(1)</script>", 1.0, ("</p><img src=x onerror=alert(1)>",))` and `Caption(3.0, "a chart", None, ())`.
- There are no model weights and no network.

### `tests/unit/test_serve_app.py`: 16 functions, 41 cases
| Test | Cases | Asserts |
| --- | --- | --- |
| 1 `test_index_page` | 1 | `GET /`: 200, `text/html; charset=utf-8`; the body contains `<script src="/static/app.js" defer></script>`; `content-security-policy == CSP` |
| 2 `test_static_files[app.js, app.css]` | 2 | 200 with the `STATIC_FILES` type; bytes equal the packaged file |
| 3 `test_unknown_paths_404[...]` | 6 | `/static/x.js`, `/static/../serve/app.py`, `/static/%2e%2e/app.py`, `/docs`, `/redoc`, `/openapi.json`: each 404 |
| 4 `test_security_headers_everywhere[...]` | 5 | `/`, `/api/assets`, `/api/search?q=x`, `/media/<A>` and `/nope` each carry every `SECURITY_HEADERS` entry exactly |
| 5 `test_search_json_shape` | 1 | `q=quarterly pricing review&k=2`: keys exactly `["query", "hits"]`; hit keys exactly `["asset_id", "path", "start_s", "end_s", "modality", "text", "media_text", "score", "trust"]` in order; `hits[0]` is A, speech, 1.5-4.25, `trust == "untrusted_media"`; the body equals `{"query": q, "hits": [asdict(h) for h in store.search(q, 2)]}` after a JSON round trip |
| 6 `test_search_filters[speech, visual, asset]` | 3 | `k=100`: every hit has that modality, or is B (`asset=<B>`); each is non-empty |
| 7 `test_search_rejects_bad_params[...]` | 6 | blank `"   "`, `k=0`, `k=101`, `modality=audio`, `asset=../x`, a `q` of 1001 characters: each 422, and the store spy saw no call |
| 8 `test_untrusted_text_is_json_data` | 1 | Searching "alert": `application/json`; B's `text` and `media_text` come back exactly as stored (`"<script>alert(1)</script>"`, `["</p><img src=x onerror=alert(1)>"]`); `x-content-type-options: nosniff` |
| 9 `test_assets_list_rescans` | 1 | `{"assets": [...]}` sorted by name. An asset added to the spy's dict after `create_app` appears on the next call |
| 10 `test_media_full_and_ranges` | 1 | A: 200, `accept-ranges: bytes`, `content-length` equals the file size, `video/mp4`. `Range: bytes=0-99` gives 206, `content-range: bytes 0-99/<size>`, and bytes equal to the file's first 100. `bytes=<size>-` gives 416. No `content-disposition` names the file |
| 11 `test_media_bad_id_404[...]` | 5 | `..%2F..%2Fetc%2Fpasswd`, `tsid1:` + 64 uppercase hex, `tsid1:` + 63 hex, `md5:` + 64 hex, `a`: each 404 `{"detail": "not found"}` |
| 12 `test_media_unsafe_or_unindexed_404[...]` | 5 | An unknown well-formed ID; a JSON path that is relative (`"clean.mp4"`); a missing file; a directory; a FIFO (`os.mkfifo`, POSIX): each 404 with the same body. The FIFO case returns at once, because `stat` runs before any open |
| 13 `test_media_rescans_on_miss` | 1 | A file added to the spy after start is served (200). The scan count rises by exactly 1 on that miss and stays the same on a hit |
| 14 `test_foreign_host_rejected` | 1 | `Host: evil.example` gives 400 on `/`, `/api/search?q=x` and `/media/<A>`; `Host: testserver` gives 200 |
| 15 `test_search_is_serialized` | 1 | A store whose `search` sleeps 0.05 s and records overlap: 4 concurrent requests (threads) never overlap |
| 16 `test_static_has_no_html_sinks` | 1 | A regex scan of the 3 static files finds none of the hard-rule tokens (the list under `static/`), no `on[a-z]+\s*=` attribute in index.html, no `<script>` with a body, no `<style>`, no `https?://` or `//` URL, and no `.on[a-z]+ =` property assignment in app.js. app.js does contain `textContent`, `encodeURIComponent` and `addEventListener` |

### `tests/unit/test_serve_cli.py`: 8 functions, 9 cases
Uses `CliRunner`. It patches `tapesift.cli.serve._run` (a recorder: app, socket), the store builder's imports (it monkeypatches `tapesift.store.lance.LanceStore` and `tapesift.vision.embed.OnnxEmbedder` to return `MemoryStore(FakeEmbedder())`), and `webbrowser.open`.

| Test | Cases | Asserts |
| --- | --- | --- |
| 17 `test_missing_extra_exits_3` | 1 | `serve_available` patched to False: exit 3, the exact message |
| 18 `test_no_index_exits_2_before_model_load` | 1 | Empty `--out`: exit 2, the exact message; the embedder constructor was not called; `out/store` doesn't exist afterwards |
| 19 `test_bad_config_exits_2` | 1 | `--config` with `colour = 1`: exit 2; stderr contains `colour: Extra inputs are not permitted` |
| 20 `test_backend_errors[model, store]` | 2 | `ModelLoadError("x")` exits 3 with `error: x`; `StoreError("y")` exits 2 with `error: y` |
| 21 `test_port_in_use_exits_2` | 1 | The test holds a socket on an ephemeral port; `--port <it>` exits 2; stderr starts `error: cannot listen on 127.0.0.1:<port>:` |
| 22 `test_loopback_default` | 1 | No flags: `_run` got a socket bound to 127.0.0.1, and the app's allowed hosts are exactly `["127.0.0.1", "[::1]", "localhost"]`. No WARNING; stderr has `tapesift UI: http://127.0.0.1:<port>/` |
| 23 `test_non_loopback_warns` | 1 | `--host 0.0.0.0 --port <a free port the test picked>`: exactly one WARNING with the exact text; allowed hosts `["*"]`; `webbrowser.open` not called |
| 24 `test_cli_import_stays_light` | 1 | `subprocess.run([sys.executable, "-c", "import sys, tapesift.cli; print(sorted({'fastapi','starlette','uvicorn','lancedb','onnxruntime','torch'} & set(sys.modules)))"], timeout=60)` prints `[]` |

### `tests/smoke/test_serve_http.py`: 1 function
| Test | Cases | Asserts |
| --- | --- | --- |
| 25 `test_real_uvicorn_over_socket` | 1 | `create_app` with the A and B records, bound on `127.0.0.1:0`, runs through `cli.serve._run`'s exact Config in a daemon thread. `urllib.request.urlopen(..., timeout=10)` gets `/api/search?q=pricing` (200, A first) and `/media/<A>` with `Range: bytes=0-15` (206, 16 bytes). Then `server.should_exit = True` and `join(10)`; the thread is dead |

**Count.** 25 test functions and 51 collected cases, all local. None is marked `model` or `gpu`.

### Commands
| Command | Expected |
| --- | --- |
| `uv run pytest tests/unit/test_serve_app.py -q` | `41 passed` |
| `uv run pytest tests/unit/test_serve_cli.py -q` | `9 passed` |
| `uv run pytest tests/smoke/test_serve_http.py -q` | `1 passed` |
| `uv run pytest -q -m "not gpu and not model"` | `B + 51 passed`, `D deselected`, with no failed, error, skipped or xfailed |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff format --check .` and `uv run ruff check .` | clean |
| `uv lock --check` | exit 0 |
| `grep -c -E '^serve = \[' pyproject.toml` | `1` |
| `grep -rn -E 'innerHTML\|outerHTML\|insertAdjacentHTML\|document\.write\|eval\(' src/tapesift/serve/static` | no output |
| `grep -rn -E 'https?://' src/tapesift/serve/static` | no output |
| A1 below | `[]` |
| A2 below | prints a line containing `tapesift/serve/static/app.js` |
| `uv run tapesift serve --help` | exit 0; lists `--config`, `--out`, `--host` and `--port` |
| `git diff --numstat main -- CHANGELOG.md` | `1	0	CHANGELOG.md` |
| `git diff --name-only main...HEAD` | exactly these 16 paths: `CHANGELOG.md`, `THIRD_PARTY.md`, `docs/spec.md`, `pyproject.toml`, `uv.lock`, `scripts/cloud/modal_ui.py`, `src/tapesift/cli/__init__.py`, `src/tapesift/cli/serve.py`, `src/tapesift/serve/__init__.py`, `src/tapesift/serve/app.py`, `src/tapesift/serve/static/index.html`, `src/tapesift/serve/static/app.js`, `src/tapesift/serve/static/app.css`, `tests/unit/test_serve_app.py`, `tests/unit/test_serve_cli.py`, `tests/smoke/test_serve_http.py` |
| `make check` | exits 0 |
| **Manual, on Modal (card 6, after owner OK):** `uvx --from modal==1.5.1 modal run scripts/cloud/modal_ui.py` | The lead opens the printed URL in a browser (gstack `/browse`) and records the following in the PR, with screenshots. "pricing review" lists speech.mp4 first, and clicking it plays from about 0:00. "ignore previous instructions" lists burned_text.mp4, with its on-screen words in the untrusted line shown as literal text. The browser console shows no CSP violations |

```bash
# A1: R6 holds with serve registered; prints []
uv run python -c "import sys, tapesift.cli; print(sorted({'fastapi','starlette','uvicorn','torch','transformers','lancedb','pyarrow','onnxruntime'} & set(sys.modules)))"
# A2: the static files ship in the wheel
uv build --wheel -o /tmp/u1-dist >/dev/null && unzip -l /tmp/u1-dist/tapesift-*.whl | grep 'tapesift/serve/static/app.js'
```

## Out of scope ("Later")
- **Indexing from the UI** (`POST /index`, jobs), the OpenAPI docs and a stable API (S4, v0.3). The `/api/*` routes here are declared unstable.
- **Server-side thumbnails** (a JPEG of the frame at `t`). That needs a seeking single-frame grab in the Media lane (card 5).
- **Auth, TLS and multi-user use.** Remote use is `--host` plus the warning only.
- Live search-as-you-type, URL query state, pagination past `MAX_K`, and highlighting matched words.
- A transcript or timeline view per asset (`show`, S6), and an export button.
- Transcoding for formats a browser can't play (mkv with some codecs, avi, ProRes). The page says so instead.
- Robotics datasets (Open X-Embodiment, LeRobot). See docs/specs/v01-lean-plan.md, "Later".
- `tapesift mcp` (S8).

## Risks
- **Browser codec support.** A browser plays mp4 (h264, AV1), webm and most mov files. mkv, avi and ProRes may not play; the player's `error` event shows a message. The index is unaffected.
- **Thumbnails cost range requests.** 20 thumbnails make about 20 range streams, and browsers cap 6 connections per host, so thumbnails trickle in. That is fine on one machine. Card 5 has the upgrade.
- **The file can change after indexing.** `/media` serves whatever regular file is at the recorded path now. It is still only an indexed path, and no client input can name another file. A local attacker who can swap files in your media folder already has that access. With `--host`, the warning covers it. Re-checking the asset ID on every request would read 16 MiB per request.
- **Stat-then-open race.** A regular file swapped for a FIFO between `stat` and open could block one worker thread. This is local-only and needs write access to the media folder. Noted, not fixed.
- **Untrusted text stays safe only by discipline.** JSON is served as `application/json` with `nosniff`. The page never parses data as HTML, test 16 enforces that statically, and the CSP blocks inline scripts if a sink slips in. No JS runtime runs in CI, so the Modal browser check (card 6) is the behavioural check.
- **opentelemetry-api comes in with fastapi.** It is an API package only, with no exporter, so it makes no network calls (Y3). Y3's offline CI run (v0.3) is the real check.
- **E6 and E7 timing.** This needs `LanceStore`, `OnnxEmbedder` and `StoreError` (E6) and `scan_assets` (E7). The PR stays draft until both merge. If E6 card 6 renames `StoreError`, step 4 follows.
- **The search lock** serializes queries. With one local user that's invisible. Remove it when S4 needs concurrency (onnxruntime sessions are thread-safe; Lance reads are MVCC).
- **IPv6 loopback.** `--host ::1` works and the Host check accepts `[::1]`. A bare `::1` Host header gets 400, which is correct.
- **`make check` time.** These tests use no models. TestClient is fast, and one real uvicorn start takes under 1 s.

## Decision cards
The lead decided every card below in lean mode (opus, 2026-10-20), under the owner's instruction to decide everything except money over about $5 and credentials. Only card 6 spends money. It is under $5 and marked for the owner because the lead asked for that.

### Decision (T3, CLI command and flags): card 1. `tapesift serve [--config] [--out] [--host] [--port]`
**Context.** The owner wants a UI in the MVP. Spec 237 had `serve [--host] [--port]` in v0.3 as an API. A shipped command and its flags are permanent.

**Options.**
- **A. One command, `serve`** (chosen). It serves the UI now and the API later (S4), with the same flags as `search` (`--config`, `--out`) plus `--host` (default `127.0.0.1`) and `--port` (default `8765`). On a terminal, it opens the browser.
- **B. A separate `tapesift ui`.** Cons: two server commands once S4 lands.
- **C. A `--ui` flag on `search`.** Cons: it mixes a one-shot command with a long-running server.

**Hardest to reverse.** The command name and the defaults. Changing the bind default would be a security change.
**Decided.** A. Port 8765 avoids the common 8000 and 8080. There is no `--no-browser` flag: the browser opens only when stderr is a TTY and the host is loopback.
**Would change my mind.** Users ask for headless runs on a TTY. Then add `--no-browser`; it is additive.

### Decision (T2, dependency): card 2. fastapi and uvicorn in `serve`, httpx2 in dev
**Context.** The lead allowed fastapi and uvicorn in the `serve` extra. The stdlib `http.server` has no Range support (about 40 lines to own), and S4 wants FastAPI anyway. starlette 1.9's TestClient wants `httpx2`; with `httpx`, its deprecation warning fails `filterwarnings = error`.

**Decided.**
- `uv add --optional serve "fastapi>=0.156.4" "uvicorn>=0.54.0"`. Plain uvicorn: no `[standard]`, uvloop or httptools.
- `uv add --dev "httpx2>=2.15.1"`.
- Exact versions are pinned by `uv.lock`, as for every other dependency (floors in pyproject, matching the repo style).
- THIRD_PARTY.md rows under Python libraries:
  ```
  | fastapi | Local web UI server (serve extra); brings starlette (BSD-3-Clause), opentelemetry-api (Apache-2.0, API only, no exporter) | MIT |
  | uvicorn | HTTP server for the web UI (serve extra) | BSD-3-Clause |
  ```
  httpx2 is dev-only, so it gets no row (the same as pytest).

**Would change my mind.** opentelemetry-api ever makes a network call by default. Then pin fastapi below the version that does, or move to bare Starlette (a card).

### Decision (T2, HTTP surface): card 3. Routes `/`, `/static/*`, `/api/search`, `/api/assets`, `/media/{asset_id}`
**Context.** Spec 237 sketches the S4 API as `GET /search` and `GET /assets/{id}`. The UI needs search, a file list and media.

**Options.**
- **A. Use the `/api/` prefix, declared unstable until S4** (chosen). `/api/search` returns exactly the `--json` document (M1 card 3), so there is one result shape everywhere.
- **B. Take spec 237's paths now.** Cons: it freezes the public API before S4 designs it.

**Decided.** A. S4 may keep these paths or add versioned ones. `/media/{asset_id}` is by ID only.

### Decision (T2, security): card 4. No auth; loopback by default; media by ID only; Host allow-list; headers
**Context.** The server is a local, single-user tool over private media. The real threats are:
- a web page in the same browser reaching 127.0.0.1, through DNS rebinding or embedding;
- path traversal through the media route;
- injected text from media (Y1) running as HTML;
- someone binding `0.0.0.0` by accident.

**Decided.**
- Bind `127.0.0.1` by default. Any other host is explicit (`--host`) and logs the exact WARNING.
- Host allow-list on loopback (`TrustedHostMiddleware`). That blocks DNS rebinding. It is off (`*`) for an explicit non-loopback host.
- Media only by `ASSET_ID_RE`, looked up in the runner's recorded paths. Only absolute, regular files. One identical 404 for every failure.
- Read-only GET routes only, so there is no CSRF surface. No CORS headers. `Cross-Origin-Resource-Policy: same-origin` stops other sites embedding `/media`.
- Strict CSP with no inline script or style. Plus nosniff, `no-referrer` and `DENY` framing. Docs routes are off (they would use a CDN).
- The page writes data with `textContent` only, statically tested. Media words are shown in a separate "untrusted" line, never mixed into the caption.
- No uvicorn access log, so search queries don't land in logs (Y3). No `Server` header.

**Would change my mind.** A real multi-user need. Then token auth arrives with S4, by card.

### Decision (T2, UX/perf): card 5. Thumbnails in the browser, from `<video preload="metadata" src="…#t=start">`
**Options.**
- **A. A browser-side thumbnail** (chosen). No server code: the browser seeks with a range request and paints that frame.
- **B. A server-side JPEG at `t`.** That needs a seeking single-frame decode. The current decoder iterates from the start, which is too slow for a frame at 2 h. It also needs a JPEG encoder, which is Media-lane work.
- **C. No thumbnails.** Cons: the owner asked for them.

**Decided.** A. There's no thumbnail for formats the browser can't play, and audio-only hits show an empty frame. B is "Later".

### Decision (T2, costs money): card 6. One Modal CPU run for a real-browser check (owner OK needed: about $0.50, at most $1)
**Context.** ADR 0008 forbids loading model weights on the laptop, so the full UI path can't run locally with real models: the real embedder, real captions, and real playback of indexed fixtures.

**What runs.**
- `scripts/cloud/modal_ui.py` on 2 cores and 8 GiB (about $0.16/h):
  - the image build is about 5 minutes;
  - indexing the 3 fixtures with tiny models is about 3 minutes, mostly model downloads;
  - the UI stays up for 30 minutes through `modal.forward`.
- That is under 1 hour in total, so **about $0.16-0.50**. The function `timeout` (60 min), `max_containers=1` and `retries=0` cap it near **$1**.
- The same script with `--video-url` and `--sha256` serves the owner's X1 talk for the demo (see the lean plan). Each 30-minute session costs about $0.10 on top of the index time.

**Decided.** Run once before the PR leaves draft, after the owner's OK. It needs no new credentials (the owner's existing Modal login).

### T1 calls (list them in the PR)
1. `ASSET_ID_RE` is defined in `serve/app.py`, the same pattern as E6's in `cli/search.py`. Consolidate both into one module later; the two are deliberately not cross-imported, so the serve module never imports the search CLI.
2. `DEFAULT_K = 20`, `MAX_K = 100` and `MAX_QUERY_CHARS = 1000`.
3. The store is built from M1's constructors in `cli/serve.py`. It does not use E7's `pipeline.index.open_store`, so the UI does not wait on E7's phase 2. It only needs `scan_assets`.
4. The media map rescans on a miss, and `/api/assets` rescans on every call (ponytail comments).
5. One lock around `store.search`.
6. The browser opens only on a TTY with a loopback host.
7. The bind happens before uvicorn starts (`socket.create_server`), so "address in use" is a clean exit 2.
8. The FIFO test uses `os.mkfifo`, POSIX only, which covers both CI OSes.
