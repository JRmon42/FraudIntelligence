"""Pure-python sliding-window aggregator + state shape used by the function."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

EntityType = Literal["card", "merchant"]

WINDOWS_S: dict[str, int] = {
    "1m": 60,
    "5m": 5 * 60,
    "1h": 60 * 60,
    "24h": 24 * 60 * 60,
}

# Cap retained events to bound document size in Cosmos (24h * conservative TPS).
MAX_RETAINED_EVENTS = 50_000


@dataclass
class TxnEvent:
    """Minimal projection of an upstream transaction event."""

    transaction_id: str
    card_id: str
    merchant_id: str
    amount: float
    currency: str
    timestamp: datetime


@dataclass
class WindowState:
    """Per-(entity_type, entity_id) sliding-window state stored in Cosmos."""

    entity_type: EntityType
    entity_id: str
    # Each retained event: (epoch_seconds, amount, merchant_id)
    events: list[tuple[float, float, str]] = field(default_factory=list)
    last_seen_iso: str = ""

    @property
    def entity_key(self) -> str:
        return f"{self.entity_type}:{self.entity_id}"

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> WindowState:
        return cls(
            entity_type=doc["entity_type"],
            entity_id=doc["entity_id"],
            events=[tuple(e) for e in doc.get("events", [])],  # type: ignore[misc]
            last_seen_iso=doc.get("last_seen_iso", ""),
        )

    def to_doc(self, features: dict[str, float | int]) -> dict[str, Any]:
        return {
            "id": self.entity_key,
            "entity_key": self.entity_key,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "events": self.events,
            "features": features,
            "last_seen_iso": self.last_seen_iso,
        }


def parse_event(payload: dict[str, Any]) -> TxnEvent:
    """Coerce a raw EH JSON body into a typed TxnEvent."""

    ts_raw = payload["timestamp"]
    ts = (
        ts_raw
        if isinstance(ts_raw, datetime)
        else datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    )
    return TxnEvent(
        transaction_id=str(payload["transaction_id"]),
        card_id=str(payload["card_id"]),
        merchant_id=str(payload["merchant_id"]),
        amount=float(payload["amount"]),
        currency=str(payload.get("currency", "EUR")),
        timestamp=ts,
    )


def _prune(events: list[tuple[float, float, str]], now_s: float) -> list[tuple[float, float, str]]:
    cutoff = now_s - WINDOWS_S["24h"]
    pruned = [e for e in events if e[0] >= cutoff]
    if len(pruned) > MAX_RETAINED_EVENTS:
        pruned = pruned[-MAX_RETAINED_EVENTS:]
    return pruned


def update_state(state: WindowState, event: TxnEvent) -> WindowState:
    """Append the new event and trim the retained log."""

    ts = event.timestamp.timestamp()
    state.events.append((ts, event.amount, event.merchant_id))
    state.events = _prune(sorted(state.events, key=lambda e: e[0]), ts)
    state.last_seen_iso = event.timestamp.isoformat()
    return state


def compute_features(state: WindowState, now: datetime | None = None) -> dict[str, float | int]:
    """Roll up sliding-window counts/sums from the retained event log."""

    now_s = (now or datetime.fromisoformat(state.last_seen_iso)).timestamp()
    out: dict[str, float | int] = {}
    for label, span in WINDOWS_S.items():
        cutoff = now_s - span
        window: Iterable[tuple[float, float, str]] = [e for e in state.events if e[0] >= cutoff]
        count = 0
        amount = 0.0
        merchants: set[str] = set()
        for _, amt, mid in window:
            count += 1
            amount += amt
            merchants.add(mid)
        out[f"count_{label}"] = count
        out[f"amount_{label}"] = round(amount, 4)
        if label == "1h":
            out["unique_merchants_1h"] = len(merchants)
    return out


def fold_event(state: WindowState, event: TxnEvent) -> tuple[WindowState, dict[str, float | int]]:
    """Convenience: update state + compute new feature snapshot in one step."""

    new_state = update_state(state, event)
    feats = compute_features(new_state, now=event.timestamp)
    return new_state, feats


def build_feature_event(
    event: TxnEvent,
    card_features: dict[str, float | int],
    merchant_features: dict[str, float | int],
) -> dict[str, Any]:
    """Outbound payload for `feature.events`."""

    return {
        "transaction_id": event.transaction_id,
        "card_id": event.card_id,
        "merchant_id": event.merchant_id,
        "ts": event.timestamp.isoformat(),
        "card_features": card_features,
        "merchant_features": merchant_features,
        "schema_version": "v1",
    }


# Re-export for tests
def seconds_between(a: datetime, b: datetime) -> float:
    return (a - b) / timedelta(seconds=1)
