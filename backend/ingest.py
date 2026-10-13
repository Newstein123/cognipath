#!/usr/bin/env python3
"""Build index.json from knowledge/*.md."""

from __future__ import annotations

import sys

from cognith_rag.chunker import chunk_corpus
from cognith_rag.config import EMBED_DIM, EMBED_MODEL, INDEX_PATH, KNOWLEDGE_DIR
from cognith_rag.embeddings import embed_documents
from cognith_rag.store import Store, file_hash


def main() -> int:
    chunks = chunk_corpus(KNOWLEDGE_DIR)
    if not chunks:
        print(f"No markdown found in {KNOWLEDGE_DIR}", file=sys.stderr)
        return 1

    by_doc: dict[str, int] = {}
    for c in chunks:
        by_doc[c.doc] = by_doc.get(c.doc, 0) + 1

    print(f"Chunked {len(by_doc)} documents into {len(chunks)} chunks:")
    for doc, n in sorted(by_doc.items()):
        print(f"  {doc:28} {n:3} chunks")

    print(f"\nEmbedding with {EMBED_MODEL} at {EMBED_DIM}d (task=RETRIEVAL_DOCUMENT)...")
    vectors = embed_documents([c.text for c in chunks])
    for chunk, vec in zip(chunks, vectors):
        chunk.embedding = vec.tolist()

    manifest = {
        "files": {
            p.name: file_hash(p) for p in sorted(KNOWLEDGE_DIR.glob("*.md"))
        }
    }
    Store(chunks, manifest).save()
    size_mb = INDEX_PATH.stat().st_size / 1e6
    print(f"Wrote {INDEX_PATH.name} ({len(chunks)} chunks, {size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
