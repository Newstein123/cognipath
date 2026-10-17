"""Central configuration for the RAG spike."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Course material lives in the active course pack (cognith_course).
def knowledge_dir() -> Path:
    from cognith_course import path

    return path("knowledge")


def index_path() -> Path:
    from cognith_course import path

    return path("index.json")


def tests_path() -> Path:
    from cognith_course import path

    return path("tests.yaml")

# --- Models -----------------------------------------------------------------
# gemini-embedding-001 is chosen over gemini-embedding-2 because it supports the
# task_type parameter, letting us embed documents and queries asymmetrically
# (RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY). That asymmetry is the highest-leverage
# knob in retrieval quality.
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768  # supported range 128-3072; 768/1536/3072 recommended
# Overridable for A/B testing: COGNITH_MODEL=gemini-3.5-flash-lite python eval.py
GENERATION_MODEL = os.environ.get("COGNITH_MODEL", "gemini-3.8-flash")

# --- Provider limits ----------------------------------------------------------
# Every Gemini call is ONE HTTP attempt of at most this many seconds. The SDK's own retry
# sleeps for whatever the server's Retry-After header says, uncapped: a free-tier daily
# quota answers 429 with "retry in 8h44m", which left lessons, grading and the tutor
# pending for hours with no error. A failed call now surfaces, and the learner retries.
GEMINI_TIMEOUT_S = float(os.environ.get("COGNITH_GEMINI_TIMEOUT_S", "60"))

# --- Retrieval --------------------------------------------------------------
TOP_K = 5

# Minimum cosine similarity for the best-matching chunk before we are willing to
# call Gemini at all. Below this the question is treated as out-of-corpus.
#
# CALIBRATED, NOT GUESSED — `python eval.py --calibrate` on 2026-09-20 showed the
# in-corpus and out-of-corpus classes OVERLAP:
#
#     lowest in-corpus      0.616  ("a user updated their profile but...")
#     highest out-of-corpus 0.662  ("what is the CAP theorem?")
#
# CAP theorem scores HIGHER than a legitimate question, so no threshold can
# separate them. The floor is therefore set conservatively: its job is cheap
# rejection of clearly-unrelated queries (weather 0.489, "write me code" 0.531),
# not defence against plausible-but-uncovered ones. That is Layer 2's job.
#
# Raising this to ~0.66 to catch CAP theorem would refuse real questions.
MIN_SCORE = 0.55

# Chunks longer than this are split on paragraph boundaries.
MAX_CHUNK_CHARS = 1200

# --- Grounding --------------------------------------------------------------
ABSTAIN_MESSAGE = (
    "I don't have enough information in the current learning materials to answer this."
)
