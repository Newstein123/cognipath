"""In-memory vector store persisted to index.json.

Small enough (~42 chunks) that a brute-force dot product is instant and fully
inspectable. Swap for Vertex Vector Search when the corpus outgrows this.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .chunker import Chunk
from .config import EMBED_DIM, EMBED_MODEL, index_path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Store:
    def __init__(self, chunks: list[Chunk], manifest: dict[str, Any] | None = None):
        self.chunks = chunks
        self.manifest = manifest or {}
        self._matrix = (
            np.array([c.embedding for c in chunks], dtype=np.float32)
            if chunks and chunks[0].embedding is not None
            else np.zeros((0, EMBED_DIM), dtype=np.float32)
        )

    # --- persistence --------------------------------------------------------
    def save(self, path: Path | None = None) -> None:
        path = path or index_path()
        payload = {
            "manifest": {
                "embed_model": EMBED_MODEL,
                "dim": EMBED_DIM,
                "chunk_count": len(self.chunks),
                **self.manifest,
            },
            "chunks": [c.to_dict() for c in self.chunks],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> "Store":
        path = path or index_path()
        if not path.exists():
            raise FileNotFoundError(
                f"No index at {path}. Run `python ingest.py` first."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = payload.get("manifest", {})
        if manifest.get("embed_model") != EMBED_MODEL or manifest.get("dim") != EMBED_DIM:
            raise RuntimeError(
                f"Index was built with {manifest.get('embed_model')}/"
                f"{manifest.get('dim')}d but config wants {EMBED_MODEL}/{EMBED_DIM}d. "
                "Re-run `python ingest.py`."
            )
        return cls([Chunk.from_dict(c) for c in payload["chunks"]], manifest)

    # --- search -------------------------------------------------------------
    def search(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        capability: str | None = None,
        difficulty: str | None = None,
        kind: str | None = None,
        docs: list[str] | None = None,
    ) -> list[Hit]:
        """Cosine similarity (vectors are normalized, so this is a dot product).

        The metadata filters prove the authored metadata reaches retrieval.

        `docs` restricts the search to named source documents (by `Chunk.doc`, e.g.
        "caching.md"). Added for the capability layer, which joins on DOCUMENT ids rather
        than on the `capability` tag — the tags turned out too coarse, one `system-design`
        tag covering three different documents. Filtering here rather than after the
        top-k matters: the chunks a capability needs may not be in the global top-k.
        """
        if not len(self._matrix):
            return []
        scores = self._matrix @ query_vector

        keep = np.ones(len(self.chunks), dtype=bool)
        for field_name, wanted in (
            ("capability", capability),
            ("difficulty", difficulty),
            ("kind", kind),
        ):
            if wanted is not None:
                keep &= np.array(
                    [c.metadata.get(field_name) == wanted for c in self.chunks]
                )
        if docs is not None:
            wanted_docs = set(docs)
            keep &= np.array([c.doc in wanted_docs for c in self.chunks])
        if not keep.any():
            return []
        scores = np.where(keep, scores, -np.inf)

        top = np.argsort(-scores)[:k]
        return [
            Hit(chunk=self.chunks[i], score=float(scores[i]))
            for i in top
            if np.isfinite(scores[i])
        ]
