"""Gemini embeddings with asymmetric query/document task types."""

from __future__ import annotations

import os

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from .config import EMBED_DIM, EMBED_MODEL, GEMINI_TIMEOUT_S

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
        _client = genai.Client(api_key=key, http_options=http_options())
    return _client


def http_options(**extra) -> types.HttpOptions:
    """Every Gemini call: bounded in time, never asleep on Retry-After.

    No HTTP status is retried: status 0 never occurs. A 429 here is a quota whose
    Retry-After can be hours, which the SDK would sleep through uncapped (see
    config.GEMINI_TIMEOUT_S), and retrying a 5xx spends quota too. attempts=1 because the
    constructor turns 0 into 1 anyway. Dropped connections and timeouts are not retried
    either, so each call is one attempt of at most GEMINI_TIMEOUT_S — checked against the
    SDK in tests/test_provider_failures.py.
    """
    return types.HttpOptions(
        timeout=int(GEMINI_TIMEOUT_S * 1000),  # milliseconds, per attempt
        retry_options=types.HttpRetryOptions(attempts=1, http_status_codes=[0]),
        **extra,
    )


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
