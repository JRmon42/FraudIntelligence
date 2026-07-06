"""Unit tests for the enforcement decision logic (no Functions host needed)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from function_app import decide_enforcement  # noqa: E402


def test_decline_blocks_and_opens_case():
    action = decide_enforcement({"transaction_id": "t1", "decision": "DECLINE"})
    assert action.open_case is True
    assert "block_card" in action.actions
    assert "notify_customer" in action.actions
    assert action.transaction_id == "t1"


def test_step_up_enforces_sca_no_case():
    action = decide_enforcement({"transaction_id": "t2", "decision": "step_up"})
    assert action.decision == "STEP_UP"
    assert action.actions == ["enforce_sca"]
    assert action.open_case is False


def test_manual_review_opens_case():
    action = decide_enforcement({"transactionId": "t3", "decision": "Manual-Review"})
    assert action.open_case is True
    assert "open_case" in action.actions


def test_unknown_decision_is_noop():
    action = decide_enforcement({"decision": "APPROVE"})
    assert action.actions == []
    assert action.open_case is False
    assert action.transaction_id == "unknown"
