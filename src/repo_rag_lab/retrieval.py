from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from .corpus import RepoDocument

TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class Chunk:
    source: Path
    text: str


def chunk_documents(documents: list[RepoDocument], chunk_size: int = 1200) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in documents:
        text = doc.text.strip()
        if not text:
            continue
        for start in range(0, len(text), chunk_size):
            snippet = text[start : start + chunk_size]
            chunks.append(Chunk(source=doc.path, text=snippet))
    return chunks


def retrieve(question: str, chunks: list[Chunk], top_k: int = 4) -> list[Chunk]:
    scored = [(score(question, chunk.text), chunk) for chunk in chunks]
    ranked = [
        chunk
        for value, chunk in sorted(scored, key=lambda item: item[0], reverse=True)
        if value > 0
    ]
    return ranked[:top_k]


def score(question: str, text: str) -> float:
    q_terms = TOKEN_RE.findall(question.lower())
    if not q_terms:
        return 0.0
    t_terms = TOKEN_RE.findall(text.lower())
    if not t_terms:
        return 0.0
    overlap = sum(1 for term in q_terms if term in t_terms)
    density = overlap / math.sqrt(len(t_terms))
    return overlap + density
