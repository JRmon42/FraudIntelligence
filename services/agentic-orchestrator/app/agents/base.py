"""Abstract base class for all agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import json
import re

from ..llm import BaseLLM
from ..state import AgentMessage, AgentResult, TimelineEntry, WorkflowState
from ..telemetry import agent_span, logger


class Agent(ABC):
    """Abstract single-responsibility agent.

    Subclasses implement :meth:`_run` and declare their :attr:`tools`. The
    public :meth:`run` wraps the call in an OTEL span, mutates the timeline,
    and never raises — failures are surfaced via :class:`AgentResult.error`.
    """

    name: str = "Agent"
    description: str = ""
    tools: list[str] = []

    def __init__(self, llm: BaseLLM, **deps: Any) -> None:
        self.llm = llm
        self.deps = deps

    @abstractmethod
    async def _run(self, state: WorkflowState) -> AgentResult: ...

    async def run(self, state: WorkflowState) -> AgentResult:
        with agent_span(self.name, case_id=state.case_id) as span_ctx:
            span_id = span_ctx.get("span_id")
            try:
                result = await self._run(state)
            except Exception as exc:
                logger.exception("agent_failed", agent=self.name, case_id=state.case_id)
                result = AgentResult(agent=self.name, summary=f"error: {exc}", error=str(exc))

            state.append_timeline(
                TimelineEntry(
                    agent=self.name,
                    action=result.summary,
                    detail={
                        "next_agent": result.next_agent,
                        "reason": result.reason,
                        "data_keys": sorted(result.data.keys()),
                        "error": result.error,
                    },
                    span_id=span_id,
                )
            )
            state.append_message(
                AgentMessage(
                    role="agent",
                    agent=self.name,
                    content=result.summary,
                    data=result.data,
                )
            )
            state.visited.append(self.name)
            return result

    @property
    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "tools": self.tools}

    @staticmethod
    def parse_json(content: str | None) -> dict[str, Any]:
        """Best-effort parse of an LLM JSON response.

        Real models sometimes wrap JSON in ```json fences or add stray prose even
        when asked for JSON. Try a strict parse first, then strip code fences and
        finally extract the first balanced ``{...}`` object. Returns ``{}`` on
        failure so callers can fall back to their deterministic defaults.
        """
        if not content:
            return {}
        text = content.strip()
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            pass
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        try:
            obj = json.loads(fenced)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            pass
        start, end = fenced.find("{"), fenced.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(fenced[start : end + 1])
                return obj if isinstance(obj, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}
