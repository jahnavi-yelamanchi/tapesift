"""`tapesift search`: search the index in out_dir/store/ and print hits (M1 card 3). Reads only.
tapesift.store.lance is imported inside the command (R6)."""

from __future__ import annotations

import dataclasses
import json
import math
import re
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final

import typer

from tapesift.cli import ExitCode, JsonOption
from tapesift.config import ConfigError, ModelLoadError, load_config
from tapesift.schema.records import Hit, Modality

ASSET_ID_RE: Final = re.compile(r"(?:tsid1|sha256):[0-9a-f]{64}")  # ADR 0012; fullmatch


class ModalityChoice(StrEnum):
    SPEECH = "speech"
    VISUAL = "visual"
    ANY = "any"  # modality=None


def _esc(s: str, special: str = "") -> str:
    """Escape every non-printable character (control, format, separator) as \\uXXXX, and
    backslash-escape the characters in `special`."""
    out: list[str] = []
    for c in s:
        if c in special:
            out.append("\\" + c)
        elif c.isprintable():
            out.append(c)
        else:
            out.append(f"\\u{ord(c):04x}" if ord(c) <= 0xFFFF else f"\\U{ord(c):08x}")
    return "".join(out)


def _qt(s: str) -> str:
    """Quote and escape untrusted text: no control, format or separator character survives."""
    return '"' + _esc(s, '\\"') + '"'


def _hms(t: float) -> str:
    if not math.isfinite(t):
        return "?"
    cs = math.floor(t * 100 + 0.5)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def render(query: str, hits: Sequence[Hit]) -> str:
    """Human output; declared not machine-stable (use --json). No trailing newline."""
    if not hits:
        return f"no results for {_qt(query)}"
    n = len(hits)
    lines = [f"{n} result{'' if n == 1 else 's'} for {_qt(query)} (text from media; untrusted)"]
    for i, h in enumerate(hits, 1):
        when = (
            f"{_hms(h.start_s)}-{_hms(h.end_s)}"
            if h.modality is Modality.SPEECH
            else _hms(h.start_s)
        )
        lines.append(
            f"{i}  {h.score:.3f}  {h.modality.value}  {when}  {_qt(h.path)}  {_qt(h.asset_id)}"
        )
        lines.append(f"   text: {_qt(h.text)}")
        if h.media_text:
            lines.append(f"   on-screen: {', '.join(_qt(m) for m in h.media_text)}")
    return "\n".join(lines)


def _fail(message: str, code: ExitCode) -> typer.Exit:
    typer.echo(f"error: {_esc(message)}", err=True)  # messages can echo store metadata
    return typer.Exit(code)


def search(
    query: Annotated[str, typer.Argument(help="What to look for, in plain words.")],
    config: Annotated[
        Path | None, typer.Option("--config", help="Config file (default ./tapesift.toml).")
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", help="Index folder, as given to tapesift index --out.")
    ] = None,
    k: Annotated[int, typer.Option("--k", min=1, help="Number of results.")] = 10,
    modality: Annotated[
        ModalityChoice, typer.Option("--modality", help="speech, visual or any.")
    ] = ModalityChoice.ANY,
    asset: Annotated[str | None, typer.Option("--asset", help="Only this asset ID.")] = None,
    as_json: JsonOption = False,
) -> None:
    """Search indexed speech and captions; prints ranked moments with timestamps."""
    from tapesift.store import lance

    if query.strip() == "":
        raise typer.BadParameter("must not be empty", param_hint="QUERY")
    if asset is not None and not ASSET_ID_RE.fullmatch(asset):
        raise typer.BadParameter(
            "not an asset ID (tsid1:<64 hex> or sha256:<64 hex>)", param_hint="--asset"
        )
    try:
        cfg = load_config(config, out_dir=out)
    except ConfigError as e:
        raise _fail(str(e), ExitCode.BAD_INPUT) from None
    try:
        idx = lance.open_index(cfg.out_dir)
    except lance.StoreError as e:
        raise _fail(str(e), ExitCode.BAD_INPUT) from None
    except ModelLoadError as e:
        raise _fail(str(e), ExitCode.ENVIRONMENT) from None
    hits = idx.search(
        query,
        k,
        modality=None if modality is ModalityChoice.ANY else Modality(modality.value),
        asset_id=asset,
    )
    if as_json:
        payload = {"query": query, "hits": [dataclasses.asdict(h) for h in hits]}
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        typer.echo(render(query, hits))
