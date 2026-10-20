"""The search store Protocol. E6 implements it (LanceDB); tests use tests/fakes.MemoryStore."""

from __future__ import annotations

from typing import Protocol

from tapesift.schema.records import AssetRecord, Hit, Modality


class Store(Protocol):
    def upsert(self, record: AssetRecord) -> None:
        """Replace every row of record.asset.id with one SPEECH row per utterance and one VISUAL
        row per caption. A VISUAL row is embedded from caption.text and its media_text,
        space-joined (so on-screen words are searchable); its Hit keeps them in separate fields.
        Rows are embedded with kind="passage". Idempotent."""
        ...

    def delete(self, asset_id: str) -> None:
        """Remove every row of asset_id. Unknown ids are a no-op. E7 calls it when a path it
        indexed before now has a different asset id (the file changed)."""
        ...

    def search(
        self,
        query: str,
        k: int = 10,
        *,
        modality: Modality | None = None,
        asset_id: str | None = None,
    ) -> list[Hit]:
        """At most k hits by score, descending; ties by (asset_id, start_s) ascending. The query
        is embedded with kind="query". modality None means both (the CLI's "any"); asset_id
        restricts to one asset (--asset). k < 1 raises ValueError. An empty store returns []."""
        ...
