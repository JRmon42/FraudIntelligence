"""Typed runtime settings, loaded from env vars / Azure Key Vault."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Service
    scoring_api_port: int = 8080
    scoring_api_log_level: str = "INFO"
    scoring_api_env: Literal["dev", "staging", "prod", "test"] = "dev"

    # Cosmos
    cosmos_endpoint: str = ""
    cosmos_database: str = "fraudintel"
    cosmos_cards_container: str = "cards"
    cosmos_merchants_container: str = "merchants"
    cosmos_key: str = ""

    # Redis (real-time aggregates)
    redis_url: str = "redis://localhost:6379/0"
    redis_fake: bool = False

    # Event Hubs
    eventhub_fqdn: str = ""
    eventhub_decisions: str = "decision.events"
    eventhub_conn_str: str = ""

    # Model
    model_path: str = "ml/artifacts/ensemble.onnx"
    model_version: str = "v0.0.0-stub"

    # OTEL
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "scoring-api"
    otel_resource_attributes: str = "service.namespace=fraudintel"

    # Azure Monitor / Application Insights. When set, request + dependency spans
    # are exported to App Insights (populating the `requests` table) so audit
    # KQL queries over scoring decisions work. Standard env var name:
    # APPLICATIONINSIGHTS_CONNECTION_STRING.
    applicationinsights_connection_string: str = ""

    # Key Vault
    azure_key_vault_url: str = ""

    # Cache
    card_cache_size: int = Field(default=10_000, ge=1)
    card_cache_ttl_s: float = Field(default=60.0, gt=0.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton settings."""

    return Settings()
