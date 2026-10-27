"""OpenTelemetry tracing to a JSON Lines file, using GenAI semantic-convention attribute names."""

import json
from collections.abc import Sequence
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult


class JsonLinesExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self.path.open("a") as out:
            for span in spans:
                out.write(span.to_json(indent=None) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def configure(path: Path | None) -> trace.Tracer:
    provider = TracerProvider(resource=Resource.create({"service.name": "agent-eval-gate"}))
    if path is not None:
        provider.add_span_processor(SimpleSpanProcessor(JsonLinesExporter(path)))
    return provider.get_tracer("agent_eval_gate")


def read_spans(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
