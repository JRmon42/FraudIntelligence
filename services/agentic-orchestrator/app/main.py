"""Service entrypoint and CLI."""

from __future__ import annotations

import argparse
import os

import uvicorn

from .api import build_app


def _bool_env(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


# Default ASGI app — uses env vars for configuration (suitable for containers).
app = build_app(
    mock_llm=_bool_env(os.getenv("MOCK_LLM"), False),
    mock_cosmos=_bool_env(os.getenv("MOCK_COSMOS"), True),
)


def cli() -> None:
    parser = argparse.ArgumentParser("fi-orchestrator")
    parser.add_argument("--host", default=os.getenv("SERVICE_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SERVICE_PORT", "8080")))
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic LLM stub")
    parser.add_argument("--mock-cosmos", action="store_true", help="Use in-memory Cosmos stub")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if args.mock_llm:
        os.environ["MOCK_LLM"] = "true"
    if args.mock_cosmos:
        os.environ["MOCK_COSMOS"] = "true"

    target_app = build_app(
        mock_llm=args.mock_llm or _bool_env(os.getenv("MOCK_LLM"), False),
        mock_cosmos=args.mock_cosmos or _bool_env(os.getenv("MOCK_COSMOS"), True),
    )
    uvicorn.run(target_app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    cli()
