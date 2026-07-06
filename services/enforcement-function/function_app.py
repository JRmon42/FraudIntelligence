"""Enforcement Azure Function — async action path for high-risk fraud alerts.

Consumes the Service Bus ``highrisk-alerts`` queue (identity-based connection)
and takes the durable action that must NOT sit inside the 18 ms synchronous
scoring budget:

* ``DECLINE``        -> block the card + open a case
* ``STEP_UP``        -> enforce SCA (3-D Secure) on subsequent attempts
* ``MANUAL_REVIEW``  -> open a case for an analyst, notify the customer

The decision logic is factored into :func:`decide_enforcement` so it can be
unit-tested without the Functions host. Case persistence to Cosmos is
best-effort and only attempted when ``COSMOS_ENDPOINT`` is configured.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import azure.functions as func
import structlog

logging.basicConfig(level=logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger(__name__)

QUEUE_NAME = os.getenv("ENFORCEMENT_QUEUE", "highrisk-alerts")


@dataclass
class EnforcementAction:
    """The durable action the enforcement consumer decides to take."""

    transaction_id: str
    decision: str
    actions: list[str] = field(default_factory=list)
    open_case: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "decision": self.decision,
            "actions": self.actions,
            "open_case": self.open_case,
        }


# Map a scoring decision to the durable enforcement actions.
_ACTIONS: dict[str, list[str]] = {
    "DECLINE": ["block_card", "open_case", "notify_customer"],
    "STEP_UP": ["enforce_sca"],
    "MANUAL_REVIEW": ["open_case", "notify_customer"],
}


def decide_enforcement(alert: dict[str, Any]) -> EnforcementAction:
    """Pure decision function: alert payload -> enforcement action.

    ``decision`` is normalised (case/spacing) so upstream variants such as
    ``"step_up"`` / ``"Step-Up"`` all map correctly.
    """

    raw = str(alert.get("decision", "")).strip().upper().replace("-", "_").replace(" ", "_")
    tx_id = str(alert.get("transaction_id") or alert.get("transactionId") or "unknown")
    actions = _ACTIONS.get(raw, [])
    return EnforcementAction(
        transaction_id=tx_id,
        decision=raw or "UNKNOWN",
        actions=list(actions),
        open_case="open_case" in actions,
    )


app = func.FunctionApp()


@app.function_name(name="enforce")
@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name=QUEUE_NAME,
    connection="ServiceBusConnection",
)
def enforce(msg: func.ServiceBusMessage) -> None:
    """Service Bus trigger: parse the alert and execute enforcement."""

    try:
        alert = json.loads(msg.get_body().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        log.warning("enforcement_bad_message", error=str(exc))
        return

    action = decide_enforcement(alert)
    log.info("enforcement_action", **action.as_dict())

    if action.open_case:
        _persist_case(alert, action)


def _persist_case(alert: dict[str, Any], action: EnforcementAction) -> None:
    """Best-effort case creation in Cosmos (skipped when unconfigured)."""

    endpoint = os.getenv("COSMOS_ENDPOINT")
    if not endpoint:
        log.info("enforcement_case_skipped", reason="no_cosmos_endpoint", **action.as_dict())
        return
    try:
        from azure.cosmos import CosmosClient  # noqa: PLC0415
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        container = client.get_database_client(
            os.getenv("COSMOS_DATABASE", "fraud")
        ).get_container_client(os.getenv("COSMOS_CASES_CONTAINER", "cases"))
        container.upsert_item(
            {
                "id": action.transaction_id,
                "source": "enforcement-function",
                "decision": action.decision,
                "actions": action.actions,
                "alert": alert,
            }
        )
        log.info("enforcement_case_opened", transaction_id=action.transaction_id)
    except Exception as exc:  # pragma: no cover - network/SDK failures
        log.warning("enforcement_case_failed", error=str(exc))
