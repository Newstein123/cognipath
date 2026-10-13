"""Heading-aware markdown chunking with metadata inheritance.

One chunk per `##` section. Each chunk inherits the document's YAML frontmatter and
may override fields with an HTML comment on the first line of the section:

    ## Exercise: Spot the missing index
    <!-- meta: kind=exercise, difficulty=intermediate -->

Heading-aware beats fixed-size windows here for two reasons: provenance stays exact
(`caching.md § Cache Invalidation`), and chunk boundaries land on concept boundaries,
which is what the capability graph will key off later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

from .config import MAX_CHUNK_CHARS

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
SECTION_META_RE = re.compile(r"\A<!--\s*meta:\s*(.*?)\s*-->\s*$", re.MULTILINE)

DEFAULT_KIND = "explanation"


@dataclass
class Chunk:
    id: str
    doc: str
    section: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None

    @property
    def citation(self) -> str:
        return f"{self.doc} § {self.section}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Chunk":
        return cls(**d)


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from body. Returns ({}, raw) when absent."""
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    meta = yaml.safe_load(m.group(1)) or {}
    return meta, raw[m.end():]


def _parse_section_meta(body: str) -> tuple[dict[str, str], str]:
    """Pull an optional `<!-- meta: k=v, k=v -->` directive off the top of a section."""
    m = SECTION_META_RE.match(body.lstrip("\n"))
    if not m:
        return {}, body
    overrides: dict[str, str] = {}
    for pair in m.group(1).split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            overrides[k.strip()] = v.strip()
    return overrides, SECTION_META_RE.sub("", body.lstrip("\n"), count=1)


def _split_long(text: str, limit: int) -> list[str]:
    """Split on blank lines, packing paragraphs up to `limit` chars."""
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for para in text.split("\n\n"):
        if current and len(current) + len(para) + 2 > limit:
            parts.append(current.strip())
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current.strip():
        parts.append(current.strip())
    return parts


def chunk_document(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    doc_meta, body = parse_frontmatter(raw)
    doc_name = path.name

    # Sections are `## ` headings. Anything before the first one (the `# Title`) is
    # dropped: it carries no content the frontmatter doesn't already capture.
    sections = re.split(r"^## +(.+?)\s*$", body, flags=re.MULTILINE)
    chunks: list[Chunk] = []
    # re.split with one capture group yields [preamble, h1, body1, h2, body2, ...]
    for i in range(1, len(sections), 2):
        heading = sections[i].strip()
        section_body = sections[i + 1] if i + 1 < len(sections) else ""
        overrides, section_body = _parse_section_meta(section_body)
        section_body = section_body.strip()
        if not section_body:
            continue

        metadata = {
            "concept": doc_meta.get("concept", doc_meta.get("id", doc_name)),
            "capability": doc_meta.get("capability"),
            "difficulty": doc_meta.get("difficulty"),
            "prerequisites": doc_meta.get("prerequisites", []),
            "source": doc_meta.get("source"),
            "kind": DEFAULT_KIND,
        }
        metadata.update(overrides)

        for n, piece in enumerate(_split_long(section_body, MAX_CHUNK_CHARS)):
            suffix = f".{n}" if n else ""
            slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
            # Embedded text carries its own headings so an isolated chunk still
            # states what it is about — this measurably helps retrieval.
            embed_text = f"{metadata['concept']} — {heading}\n\n{piece}"
            chunks.append(
                Chunk(
                    id=f"{doc_name}#{slug}{suffix}",
                    doc=doc_name,
                    section=heading,
                    text=embed_text,
                    metadata=dict(metadata),
                )
            )
    return chunks


def chunk_corpus(knowledge_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        chunks.extend(chunk_document(path))
    return chunks
