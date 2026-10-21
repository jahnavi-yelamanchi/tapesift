"""Test 25 of docs/specs/40-web-ui.md: the app behind a real uvicorn server on a real socket."""

import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from conftest import FIXTURES

from tapesift.media.types import AssetInfo
from tapesift.schema.records import AssetRecord, Caption, Provenance, Utterance
from tapesift.serve.app import LOOPBACK_HOSTS, create_app

# isort: split
from tests.fakes import FakeEmbedder, MemoryStore

ID_A = "tsid1:" + "a" * 64
ID_B = "tsid1:" + "b" * 64


def _record(asset_id: str, path: Path, *, utt: bool) -> AssetRecord:
    info = AssetInfo(asset_id, path, 10.0, None, (), ())
    utterances = (
        (
            Utterance(1.5, 4.25, "The quarterly pricing review starts at nine.", "en", 1.0, ()),
            Utterance(5.0, 8.0, "Revenue grew twelve percent.", "en", 1.0, ()),
        )
        if utt
        else ()
    )
    captions = (
        ()
        if utt
        else (
            Caption(2.0, "<script>alert(1)</script>", 1.0, ("</p><img src=x onerror=alert(1)>",)),
            Caption(3.0, "a chart", None, ()),
        )
    )
    return AssetRecord(info, utterances, captions, (), Provenance("0.1.0", None, None, None))


def test_real_uvicorn_over_socket(tmp_path: Path) -> None:
    clean = (FIXTURES / "clean.mp4").resolve()
    b_file = tmp_path / "b.mp4"
    b_file.write_bytes(b"b" * 64)
    store = MemoryStore(FakeEmbedder())
    store.upsert(_record(ID_A, clean, utt=True))
    store.upsert(_record(ID_B, b_file, utt=False))
    media = {ID_A: str(clean), ID_B: str(b_file)}
    app = create_app(store, lambda: media, allowed_hosts=sorted(LOOPBACK_HOSTS))

    sock = socket.create_server(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    # The exact Config of tapesift.cli.serve._run (spec 40).
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="warning",
            access_log=False,
            server_header=False,
            proxy_headers=False,
            timeout_keep_alive=5,
            lifespan="off",
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started

        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(f"{base}/api/search?q=pricing", timeout=10) as resp:  # noqa: S310
            assert resp.status == 200
            hits = json.loads(resp.read())["hits"]
        assert hits[0]["asset_id"] == ID_A

        req = urllib.request.Request(f"{base}/media/{ID_A}", headers={"Range": "bytes=0-15"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            assert resp.status == 206
            assert resp.read() == clean.read_bytes()[:16]
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
    assert not thread.is_alive()
