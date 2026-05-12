"""Structured logging + OpenTelemetry bootstrap."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .settings import Settings

_TRACER: trace.Tracer | None = None


def configure_logging(settings: Settings) -> None:
    """Configure stdlib + structlog for JSON structured output."""

    level = getattr(logging, settings.scoring_api_log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def configure_tracing(settings: Settings) -> trace.Tracer:
    """Initialise the OTLP tracer provider (idempotent)."""

    global _TRACER
    if _TRACER is not None:
        return _TRACER

    resource_attrs: dict[str, Any] = {
        "service.name": settings.otel_service_name,
        "service.version": settings.model_version,
    }
    for kv in settings.otel_resource_attributes.split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            resource_attrs[k.strip()] = v.strip()

    provider = TracerProvider(resource=Resource.create(resource_attrs))

    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
                )
            )
        except Exception:  # noqa: BLE001 - tracing is best-effort
            structlog.get_logger(__name__).warning(
                "otel_exporter_init_failed", endpoint=settings.otel_exporter_otlp_endpoint
            )

    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer("scoring-api")
    return _TRACER


def get_tracer() -> trace.Tracer:
    """Return the active tracer, falling back to the no-op tracer."""

    return _TRACER or trace.get_tracer("scoring-api")
