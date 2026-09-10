from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator


@dataclass(slots=True)
class TraceEvent:
    run_id: str
    stage: str
    status: str
    started_at: float
    duration_ms: float
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


class JsonlTracer:
    """Dependency-free trace sink suitable for later OTEL export."""

    def __init__(self, destination: Path):
        self.destination = destination

    def emit(self, event: TraceEvent) -> None:
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        with self.destination.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(event), sort_keys=True) + "\n")

    @contextmanager
    def span(self, run_id: str, stage: str) -> Iterator[dict[str, float | int]]:
        started = time.time()
        usage: dict[str, float | int] = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
        try:
            yield usage
        except Exception as exc:
            self.emit(TraceEvent(run_id, stage, "error", started, (time.time() - started) * 1000, error=str(exc)))
            raise
        else:
            self.emit(TraceEvent(run_id, stage, "ok", started, (time.time() - started) * 1000, **usage))

