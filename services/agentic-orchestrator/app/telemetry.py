"""Telemetry helpers — OpenTelemetry spans + structured logging."""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from typing import Any

import structlog

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover
    _OTEL_AVAILABLE = False


_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=_log_level, format="%(message)s")
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, _log_level, logging.INFO)
    ),
)

logger = structlog.get_logger("agentic-orchestrator")

_tracer = None
if _OTEL_AVAILABLE:
    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "fi-agentic-orchestrator")}
    )
    provider = TracerProvider(resource=resource)
    if os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("agentic-orchestrator")


@contextlib.contextmanager
def agent_span(agent: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    """Context manager that creates a span for an agent step."""

    ctx: dict[str, Any] = {"span_id": None}
    if _tracer is None:
        yield ctx
        return
    with _tracer.start_as_current_span(f"agent.{agent}") as span:
        for k, v in attrs.items():
            try:  # noqa: SIM105  (best-effort span attribute; suppress keeps pragma)
                span.set_attribute(k, v)
            except Exception:  # pragma: no cover
                pass
        sc = span.get_span_context()
        ctx["span_id"] = format(sc.span_id, "016x") if sc and sc.span_id else None
        yield ctx
