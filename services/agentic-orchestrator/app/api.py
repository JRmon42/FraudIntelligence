"""FastAPI surface for the agentic orchestrator."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .agents import build_default_agents
from .cosmos import build_cases, build_graph
from .llm import build_llm
from .planner import Planner, build_kernel
from .state import Alert, WorkflowState
from .telemetry import logger
from .tools import register_with_semantic_kernel


class ServiceContext:
    """Wires together LLM, Cosmos clients, agents and planner."""

    def __init__(
        self, *, mock_llm: bool | None = None, mock_cosmos: bool | None = None
    ) -> None:
        self.llm = build_llm(mock=mock_llm)
        self.cases = build_cases(mock=mock_cosmos)
        self.graph = build_graph(mock=mock_cosmos)
        self.kernel = build_kernel()
        self.tool_metadata = (
            register_with_semantic_kernel(
                self.kernel, graph=self.graph, cases=self.cases
            )
            if self.kernel
            else {}
        )
        self.agents = build_default_agents(self.llm, graph=self.graph, cases=self.cases)
        self.planner = Planner(self.agents, kernel=self.kernel)
        self.live_subscribers: dict[str, list[asyncio.Queue]] = {}

    async def publish(self, case_id: str, event: dict[str, Any]) -> None:
        for q in list(self.live_subscribers.get(case_id, [])):
            await q.put(event)

    def subscribe(self, case_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.live_subscribers.setdefault(case_id, []).append(q)
        return q

    def unsubscribe(self, case_id: str, q: asyncio.Queue) -> None:
        if q in self.live_subscribers.get(case_id, []):
            self.live_subscribers[case_id].remove(q)


# ---------- request/response schemas ----------


class AlertIn(BaseModel):
    transaction_id: str | None = None
    card_id: str | None = None
    merchant_id: str | None = None
    device_id: str | None = None
    customer_id: str | None = None
    amount: float | None = None
    currency: str = "EUR"
    score: float | None = None
    reason_codes: list[str] = []
    raw: dict[str, Any] = {}


class AlertResponse(BaseModel):
    case_id: str
    classification: str
    status: str


class ReplayRequest(BaseModel):
    reflection_budget: int = 2


# ---------- router factory ----------


def build_router(ctx: ServiceContext) -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.post("/alerts", response_model=AlertResponse)
    async def post_alert(payload: AlertIn) -> AlertResponse:
        alert = Alert(**payload.model_dump())
        state = WorkflowState(alert=alert)

        async def _run_and_publish() -> None:
            async for ev in ctx.planner.stream(state):
                await ctx.publish(state.case_id, ev)
            await ctx.cases.upsert(state.to_case())

        # Run inline so the client gets the final classification synchronously,
        # but also publish events for any live WS subscribers.
        await _run_and_publish()
        case = state.to_case()
        return AlertResponse(
            case_id=case.case_id,
            classification=case.classification.value,
            status=case.status,
        )

    @router.get("/cases/{case_id}")
    async def get_case(case_id: str) -> dict[str, Any]:
        case = await ctx.cases.get(case_id)
        if case is None:
            raise HTTPException(404, "case not found")
        return case.model_dump(mode="json")

    @router.post("/cases/{case_id}/replay")
    async def replay_case(case_id: str, req: ReplayRequest) -> dict[str, Any]:
        case = await ctx.cases.get(case_id)
        if case is None:
            raise HTTPException(404, "case not found")
        state = WorkflowState(
            alert=case.alert,
            case_id=case.case_id,
            reflection_budget=req.reflection_budget,
        )
        async for ev in ctx.planner.stream(state):
            await ctx.publish(case_id, ev)
        await ctx.cases.upsert(state.to_case())
        return state.to_case().model_dump(mode="json")

    @router.get("/agents")
    async def list_agents() -> dict[str, Any]:
        return {
            "agents": [a.metadata for a in ctx.agents.values()],
            "tools": ctx.tool_metadata,
            "llm": "mock" if getattr(ctx.llm, "is_mock", False) else "azure_openai",
        }

    @router.websocket("/cases/{case_id}/events")
    async def case_events(ws: WebSocket, case_id: str) -> None:
        await ws.accept()
        q = ctx.subscribe(case_id)
        try:
            while True:
                ev = await q.get()
                await ws.send_text(json.dumps(ev, default=str))
                if ev.get("event") == "end":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            ctx.unsubscribe(case_id, q)

    return router


def build_app(
    *, mock_llm: bool | None = None, mock_cosmos: bool | None = None
) -> FastAPI:
    app = FastAPI(title="Heimdall Agentic Orchestrator", version="0.1.0")
    ctx = ServiceContext(mock_llm=mock_llm, mock_cosmos=mock_cosmos)
    app.state.ctx = ctx
    app.include_router(build_router(ctx))

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    logger.info("orchestrator_ready", llm="mock" if ctx.llm.is_mock else "azure")
    return app
