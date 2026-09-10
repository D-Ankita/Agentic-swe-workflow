from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SearchHit:
    path: str
    score: float
    excerpt: str


class CodeRetriever:
    """Local lexical RAG that keeps code context on the developer machine."""

    def __init__(self, root: Path, max_file_bytes: int = 200_000):
        self.root = root
        self.max_file_bytes = max_file_bytes

    @staticmethod
    def _terms(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", text.lower())

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        wanted = set(self._terms(query))
        hits: list[SearchHit] = []
        ignored = {".git", ".forge", "node_modules", ".venv", "__pycache__"}
        for path in self.root.rglob("*"):
            if not path.is_file() or any(part in ignored for part in path.parts):
                continue
            try:
                if path.stat().st_size > self.max_file_bytes:
                    continue
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            # Names often carry more intent than implementation text (for example,
            # ``payments.py``), so index the relative path alongside file contents.
            terms = self._terms(str(path.relative_to(self.root))) + self._terms(content)
            overlap = wanted.intersection(terms)
            if overlap:
                score = sum(1 + math.log1p(terms.count(term)) for term in overlap)
                lines = [line.strip() for line in content.splitlines() if wanted.intersection(self._terms(line))]
                hits.append(SearchHit(str(path.relative_to(self.root)), score, "\n".join(lines[:6])[:1000]))
        return sorted(hits, key=lambda hit: (-hit.score, hit.path))[:limit]
