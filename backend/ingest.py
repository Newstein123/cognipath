#!/usr/bin/env python3
"""Build index.json from knowledge/*.md."""

from __future__ import annotations

import sys

from cognith_rag.chunker import chunk_corpus
from cognith_rag.config import EMBED_DIM, EMBED_MODEL, index_path, knowledge_dir
from cognith_rag.embeddings import embed_documents
from cognith_rag.store import Store, file_hash


def main() -> int:
    chunks = chunk_corpus(knowledge_dir())
    if not chunks:
        print(f"No markdown found in {knowledge_dir()}", file=sys.stderr)
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
            p.name: file_hash(p) for p in sorted(knowledge_dir().glob("*.md"))
        }
    }
    Store(chunks, manifest).save()
    size_mb = index_path().stat().st_size / 1e6
    print(f"Wrote {index_path().name} ({len(chunks)} chunks, {size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
