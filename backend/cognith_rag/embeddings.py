"""Gemini embeddings with asymmetric query/document task types."""

from __future__ import annotations

import os

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from .config import EMBED_DIM, EMBED_MODEL

_client: genai.Client | None = None

# Batch size for embed_content. Kept modest to stay well inside request limits.
BATCH_SIZE = 32


def get_client() -> genai.Client:
    global _client
    if _client is None:
        load_dotenv()
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key "
                "from https://aistudio.google.com/apikey"
            )
        _client = genai.Client(api_key=key)
    return _client


def normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize so cosine similarity reduces to a dot product.

    Required: gemini-embedding-001 only returns unit-length vectors at the full 3072
    dimensions. Truncated output_dimensionality values come back un-normalized.
    """
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _embed(texts: list[str], task_type: str) -> np.ndarray:
    client = get_client()
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        resp = client.models.embed_content(
            model=EMBED_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBED_DIM,
            ),
        )
        out.extend(e.values for e in resp.embeddings)
    return normalize(np.array(out, dtype=np.float32))


def embed_documents(texts: list[str]) -> np.ndarray:
    """Embed corpus chunks. Uses RETRIEVAL_DOCUMENT."""
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> np.ndarray:
    """Embed a single question. Uses RETRIEVAL_QUERY."""
    return _embed([text], "RETRIEVAL_QUERY")[0]
