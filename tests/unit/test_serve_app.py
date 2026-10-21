"""Local web UI app (docs/specs/40-web-ui.md, Acceptance tests 1-16). A fake store, a spy scan and
Starlette's TestClient: no model weights, no network, no real server."""

import dataclasses
import importlib.resources
import json
import os
import re
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tapesift.media.types import AssetInfo
from tapesift.schema.records import AssetRecord, Caption, Hit, Modality, Provenance, Utterance
from tapesift.serve.app import CSP, SECURITY_HEADERS, STATIC_FILES, create_app

# isort: split
from tests.fakes import FakeEmbedder, MemoryStore

FIXTURES = Path(__file__).parents[1].resolve() / "fixtures"
CLEAN = FIXTURES / "clean.mp4"
ID_A = "tsid1:" + "a" * 64
ID_B = "tsid1:" + "b" * 64
ID_C = "tsid1:" + "c" * 64
NOT_FOUND = {"detail": "not found"}
SCRIPT_TEXT = "<script>alert(1)</script>"
IMG_TEXT = "</p><img src=x onerror=alert(1)>"


def _record(
    asset_id: str,
    path: Path,
    utterances: tuple[Utterance, ...] = (),
    captions: tuple[Caption, ...] = (),
) -> AssetRecord:
    info = AssetInfo(asset_id, path, 10.0, None, (), ())
    return AssetRecord(info, utterances, captions, (), Provenance("0.1.0", None, None, None))


def _utt(start_s: float, end_s: float, text: str) -> Utterance:
    return Utterance(start_s, end_s, text, "en", 1.0, ())


class SpyStore(MemoryStore):
    """MemoryStore that counts search calls."""

    def __init__(self) -> None:
        super().__init__(FakeEmbedder())
        self.search_calls = 0

    def search(
        self,
        query: str,
        k: int = 10,
        *,
        modality: Modality | None = None,
        asset_id: str | None = None,
    ) -> list[Hit]:
        self.search_calls += 1
        return super().search(query, k, modality=modality, asset_id=asset_id)


class SpyScan:
    """The scan() the app receives: returns a copy of `media` and counts its calls."""

    def __init__(self, media: dict[str, str]) -> None:
        self.media = media
        self.calls = 0

    def __call__(self) -> Mapping[str, str]:
        self.calls += 1
        return dict(self.media)


@dataclasses.dataclass
class Env:
    store: SpyStore
    scan: SpyScan
    client: TestClient
    b_path: Path


@pytest.fixture
def env(tmp_path: Path) -> Env:
    b_path = tmp_path / "b_clip.mp4"
    b_path.write_bytes(b"not really a video" * 10)
    store = SpyStore()
    store.upsert(
        _record(
            ID_A,
            CLEAN,
            utterances=(
                _utt(1.5, 4.25, "The quarterly pricing review starts at nine."),
                _utt(5.0, 8.0, "Revenue grew twelve percent."),
            ),
        )
    )
    store.upsert(
        _record(
            ID_B,
            b_path,
            captions=(
                Caption(2.0, SCRIPT_TEXT, 1.0, (IMG_TEXT,)),
                Caption(3.0, "a chart", None, ()),
            ),
        )
    )
    scan = SpyScan({ID_A: str(CLEAN), ID_B: str(b_path)})
    app = create_app(store, scan, allowed_hosts=["testserver"])
    return Env(store, scan, TestClient(app), b_path)


def _client_for(media: dict[str, str]) -> tuple[TestClient, SpyScan]:
    scan = SpyScan(media)
    return TestClient(create_app(SpyStore(), scan, allowed_hosts=["testserver"])), scan


def _bounded_get(client: TestClient, url: str) -> Any:
    """GET in a thread so a request that blocks (a FIFO opened by mistake) fails, not hangs."""
    out: list[Any] = []
    t = threading.Thread(target=lambda: out.append(client.get(url)), daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), f"GET {url} did not return"
    return out[0]


# 1
def test_index_page(env: Env) -> None:
    r = env.client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    assert '<script src="/static/app.js" defer></script>' in r.text
    assert r.headers["content-security-policy"] == CSP


# 2
@pytest.mark.parametrize("name", ["app.js", "app.css"])
def test_static_files(env: Env, name: str) -> None:
    r = env.client.get(f"/static/{name}")
    assert r.status_code == 200
    assert r.headers["content-type"] == STATIC_FILES[name]
    packaged = importlib.resources.files("tapesift.serve").joinpath("static", name).read_bytes()
    assert r.content == packaged


# 3
@pytest.mark.parametrize(
    "path",
    [
        "/static/x.js",
        "/static/../serve/app.py",
        "/static/%2e%2e/app.py",
        "/docs",
        "/redoc",
        "/openapi.json",
    ],
)
def test_unknown_paths_404(env: Env, path: str) -> None:
    assert env.client.get(path).status_code == 404


# 4
@pytest.mark.parametrize("path", ["/", "/api/assets", "/api/search?q=x", "/media/" + ID_A, "/nope"])
def test_security_headers_everywhere(env: Env, path: str) -> None:
    r = env.client.get(path)
    for name, value in SECURITY_HEADERS.items():
        sent = [v for k, v in r.headers.multi_items() if k.lower() == name.lower()]
        assert sent == [value], f"{name} on {path}"


# 5
def test_search_json_shape(env: Env) -> None:
    q = "quarterly pricing review"
    r = env.client.get("/api/search", params={"q": q, "k": 2})
    assert r.status_code == 200
    body = r.json()
    assert list(body) == ["query", "hits"]
    for hit in body["hits"]:
        assert list(hit) == [
            "asset_id",
            "path",
            "start_s",
            "end_s",
            "modality",
            "text",
            "media_text",
            "score",
            "trust",
        ]
    first = body["hits"][0]
    assert first["asset_id"] == ID_A
    assert first["modality"] == "speech"
    assert (first["start_s"], first["end_s"]) == (1.5, 4.25)
    assert first["trust"] == "untrusted_media"
    expected = {"query": q, "hits": [dataclasses.asdict(h) for h in env.store.search(q, 2)]}
    assert body == json.loads(json.dumps(expected))


# 6
@pytest.mark.parametrize("which", ["speech", "visual", "asset"])
def test_search_filters(env: Env, which: str) -> None:
    params: dict[str, str | int] = {"q": "pricing chart alert revenue", "k": 100}
    if which == "asset":
        params["asset"] = ID_B
    else:
        params["modality"] = which
    r = env.client.get("/api/search", params=params)
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert hits
    if which == "asset":
        assert {h["asset_id"] for h in hits} == {ID_B}
    else:
        assert {h["modality"] for h in hits} == {which}


# 7
@pytest.mark.parametrize(
    "params",
    [
        {"q": "   "},
        {"q": "x", "k": 0},
        {"q": "x", "k": 101},
        {"q": "x", "modality": "audio"},
        {"q": "x", "asset": "../x"},
        {"q": "a" * 1001},
    ],
    ids=["blank", "k0", "k101", "modality", "asset", "long_q"],
)
def test_search_rejects_bad_params(env: Env, params: dict[str, str | int]) -> None:
    r = env.client.get("/api/search", params=params)
    assert r.status_code == 422
    assert env.store.search_calls == 0


# 8
def test_untrusted_text_is_json_data(env: Env) -> None:
    r = env.client.get("/api/search", params={"q": "alert", "k": 100})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["x-content-type-options"] == "nosniff"
    visual_b = [h for h in r.json()["hits"] if h["asset_id"] == ID_B and h["text"] == SCRIPT_TEXT]
    assert len(visual_b) == 1
    assert visual_b[0]["text"] == SCRIPT_TEXT
    assert visual_b[0]["media_text"] == [IMG_TEXT]


# 9
def test_assets_list_rescans(env: Env, tmp_path: Path) -> None:
    def expected() -> list[dict[str, str]]:
        rows = [(Path(p).name, aid) for aid, p in env.scan.media.items()]
        return [{"asset_id": aid, "name": name} for name, aid in sorted(rows)]

    r = env.client.get("/api/assets")
    assert r.status_code == 200
    assert list(r.json()) == ["assets"]
    # B's file name sorts before A's although A's id sorts first: order is by name.
    assert r.json()["assets"] == [
        {"asset_id": ID_B, "name": "b_clip.mp4"},
        {"asset_id": ID_A, "name": "clean.mp4"},
    ]
    assert r.json()["assets"] == expected()

    env.scan.media[ID_C] = str(tmp_path / "a_new.mp4")
    r2 = env.client.get("/api/assets")
    assert r2.json()["assets"] == expected()
    assert r2.json()["assets"][0] == {"asset_id": ID_C, "name": "a_new.mp4"}


# 10
def test_media_full_and_ranges(env: Env) -> None:
    data = CLEAN.read_bytes()
    size = len(data)

    full = env.client.get(f"/media/{ID_A}")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert int(full.headers["content-length"]) == size
    assert full.headers["content-type"] == "video/mp4"
    assert full.content == data

    part = env.client.get(f"/media/{ID_A}", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 0-99/{size}"
    assert part.content == data[:100]

    past_end = env.client.get(f"/media/{ID_A}", headers={"Range": f"bytes={size}-"})
    assert past_end.status_code == 416

    for r in (full, part, past_end):
        assert CLEAN.name not in r.headers.get("content-disposition", "")


# 11
@pytest.mark.parametrize(
    "asset_id",
    [
        "..%2F..%2Fetc%2Fpasswd",
        "tsid1:" + "A" * 64,
        "tsid1:" + "a" * 63,
        "md5:" + "a" * 64,
        "a",
    ],
    ids=["traversal", "uppercase", "short", "md5", "a"],
)
def test_media_bad_id_404(env: Env, asset_id: str) -> None:
    r = env.client.get(f"/media/{asset_id}")
    assert r.status_code == 404
    if asset_id.startswith(".."):
        # The client decodes %2F, so no route matches and Starlette's own 404 body answers
        # ("Not Found"); the spec's route-level body cannot apply. Still no file is touched.
        assert r.json()["detail"].lower() == "not found"
    else:
        assert r.json() == NOT_FOUND


# 12
@pytest.mark.parametrize("kind", ["unknown_id", "relative", "missing", "directory", "fifo"])
def test_media_unsafe_or_unindexed_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.chdir(FIXTURES)  # a relative "clean.mp4" would resolve here if it were opened
    media: dict[str, str] = {}
    if kind == "relative":
        media[ID_C] = "clean.mp4"
    elif kind == "missing":
        media[ID_C] = str(tmp_path / "gone.mp4")
    elif kind == "directory":
        (tmp_path / "a_dir").mkdir()
        media[ID_C] = str(tmp_path / "a_dir")
    elif kind == "fifo":
        os.mkfifo(tmp_path / "a.fifo")
        media[ID_C] = str(tmp_path / "a.fifo")
    client, _ = _client_for(media)
    r = _bounded_get(client, f"/media/{ID_C}")
    assert r.status_code == 404
    assert r.json() == NOT_FOUND


# 13
def test_media_rescans_on_miss(env: Env, tmp_path: Path) -> None:
    late = tmp_path / "late.mp4"
    late.write_bytes(b"late bytes")
    base = env.scan.calls

    assert env.client.get(f"/media/{ID_A}").status_code == 200
    assert env.scan.calls == base  # a hit does not rescan

    env.scan.media[ID_C] = str(late)
    r = env.client.get(f"/media/{ID_C}")
    assert r.status_code == 200
    assert r.content == b"late bytes"
    assert env.scan.calls == base + 1  # exactly one rescan on the miss

    assert env.client.get(f"/media/{ID_C}").status_code == 200
    assert env.scan.calls == base + 1  # and the new entry is now a hit


# 14
def test_foreign_host_rejected(env: Env) -> None:
    for path in ("/", "/api/search?q=x", f"/media/{ID_A}"):
        assert env.client.get(path, headers={"Host": "evil.example"}).status_code == 400
        assert env.client.get(path, headers={"Host": "testserver"}).status_code == 200


# 15
class _SlowStore:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self._guard = threading.Lock()

    def upsert(self, record: AssetRecord) -> None:
        raise NotImplementedError

    def delete(self, asset_id: str) -> None:
        raise NotImplementedError

    def search(
        self,
        query: str,
        k: int = 10,
        *,
        modality: Modality | None = None,
        asset_id: str | None = None,
    ) -> list[Hit]:
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        with self._guard:
            self.active -= 1
        return []


def test_search_is_serialized() -> None:
    store = _SlowStore()
    app = create_app(store, SpyScan({}), allowed_hosts=["testserver"])
    codes: list[int] = []

    def go() -> None:
        codes.append(TestClient(app).get("/api/search", params={"q": "x"}).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert codes == [200] * 4
    assert store.max_active == 1


# 16
_STATIC = ("index.html", "app.js", "app.css")
_SINKS = [
    r"innerHTML",
    r"outerHTML",
    r"insertAdjacentHTML",
    r"document\.write",
    r"eval\(",
    r"new\s+Function",
    r"setTimeout\(\s*[\"'`]",
    r"setInterval\(\s*[\"'`]",
    r"localStorage",
    r"sessionStorage",
    r"indexedDB",
    r"document\.cookie",
    r"https?://",
    r"[\"'(=]\s*//[^\s/]",  # protocol-relative URL
]


def _static(name: str) -> str:
    return importlib.resources.files("tapesift.serve").joinpath("static", name).read_text("utf-8")


def test_static_has_no_html_sinks() -> None:
    for name in _STATIC:
        text = _static(name)
        for pattern in _SINKS:
            assert not re.search(pattern, text), f"{name}: {pattern}"

    html = _static("index.html")
    assert not re.search(r"\son[a-z]+\s*=", html), "inline event handler attribute"
    assert not re.search(r"<style", html, re.IGNORECASE)
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    assert scripts, "index.html has no script tag"
    assert all(body.strip() == "" and "src=" in attrs for attrs, body in scripts)
    assert not re.search(r"<style", _static("app.css"), re.IGNORECASE)

    js = _static("app.js")
    assert not re.search(r"\.on[a-z]+\s*=(?!=)", js), "on<event> property assignment"
    for token in ("textContent", "encodeURIComponent", "addEventListener"):
        assert token in js


# review fix 2: only audio and video types leave /media as such
@pytest.mark.parametrize("name", ["page.html", "logo.svg", "run.js", "noext"])
def test_media_non_av_type_is_opaque(tmp_path: Path, name: str) -> None:
    f = tmp_path / name
    f.write_bytes(b"<script>alert(1)</script>")
    client, _ = _client_for({ID_C: str(f)})
    r = client.get(f"/media/{ID_C}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"


# review fix 3: a 500 (a store failing mid-session) still carries every security header
def test_500_carries_security_headers() -> None:
    class BrokenStore(SpyStore):
        def search(
            self,
            query: str,
            k: int = 10,
            *,
            modality: Modality | None = None,
            asset_id: str | None = None,
        ) -> list[Hit]:
            raise RuntimeError("index gone: /private/path")

    app = create_app(BrokenStore(), SpyScan({}), allowed_hosts=["testserver"])
    r = TestClient(app, raise_server_exceptions=False).get("/api/search?q=x")
    assert r.status_code == 500
    assert r.json() == {"detail": "internal error"}
    for name, value in SECURITY_HEADERS.items():
        assert r.headers[name] == value
