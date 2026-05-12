"""Pydantic state objects shared across the multi-agent workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Classification(str, Enum):
    SUSPECTED_FRAUD_RING = "suspected_fraud_ring"
    ACCOUNT_TAKEOVER = "account_takeover"
    CARD_PRESENT_FRAUD = "card_present_fraud"
    FALSE_POSITIVE_CANDIDATE = "false_positive_candidate"
    DISPUTE = "dispute"
    UNKNOWN = "unknown"


class ReflectionVerdict(str, Enum):
    ACCEPT = "accept"
    REPLAN = "replan"
    ESCALATE = "escalate"


class Alert(BaseModel):
    """Inbound fraud alert / event payload."""

    alert_id: str = Field(default_factory=lambda: f"alert-{uuid4().hex[:12]}")
    transaction_id: str | None = None
    card_id: str | None = None
    merchant_id: str | None = None
    device_id: str | None = None
    customer_id: str | None = None
    amount: float | None = None
    currency: str = "EUR"
    score: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    received_at: str = Field(default_factory=_utcnow)


class TimelineEntry(BaseModel):
    ts: str = Field(default_factory=_utcnow)
    agent: str
    action: str
    detail: dict[str, Any] = Field(default_factory=dict)
    span_id: str | None = None


class AgentMessage(BaseModel):
    role: str  # "agent" | "system" | "tool"
    agent: str
    content: str
    data: dict[str, Any] = Field(default_factory=dict)
    ts: str = Field(default_factory=_utcnow)


class AgentResult(BaseModel):
    """Standardised return value from every agent's ``run`` method."""

    agent: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    next_agent: str | None = None
    reason: str | None = None
    done: bool = False
    error: str | None = None


class GraphFindings(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    anomaly_score: float = 0.0
    notes: list[str] = Field(default_factory=list)


class PolicyFindings(BaseModel):
    sca_exemptions_applied: list[str] = Field(default_factory=list)
    sca_exemptions_blocked: list[str] = Field(default_factory=list)
    eba_categories: list[str] = Field(default_factory=list)
    rationale: str = ""


class CaseRecord(BaseModel):
    case_id: str
    alert: Alert
    status: str = "open"  # open | closed | escalated
    classification: Classification = Classification.UNKNOWN
    graph: GraphFindings | None = None
    policy: PolicyFindings | None = None
    narrative_sar: str | None = None
    narrative_eba: str | None = None
    timeline: list[TimelineEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)


class WorkflowState(BaseModel):
    """Shared state passed between agents and persisted across replays."""

    case_id: str = Field(default_factory=lambda: f"case-{uuid4().hex[:12]}")
    alert: Alert
    classification: Classification = Classification.UNKNOWN
    messages: list[AgentMessage] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)

    graph: GraphFindings | None = None
    policy: PolicyFindings | None = None
    narrative_sar: str | None = None
    narrative_eba: str | None = None

    # planning
    visited: list[str] = Field(default_factory=list)
    next_agent: str | None = "TriageAgent"
    reflection_verdict: ReflectionVerdict | None = None
    reflection_budget: int = 2
    reflections_used: int = 0
    done: bool = False

    def append_message(self, msg: AgentMessage) -> None:
        self.messages.append(msg)

    def append_timeline(self, entry: TimelineEntry) -> None:
        self.timeline.append(entry)

    def to_case(self) -> CaseRecord:
        return CaseRecord(
            case_id=self.case_id,
            alert=self.alert,
            status="closed" if self.done else "open",
            classification=self.classification,
            graph=self.graph,
            policy=self.policy,
            narrative_sar=self.narrative_sar,
            narrative_eba=self.narrative_eba,
            timeline=self.timeline,
        )
