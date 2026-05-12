"""Agent package exports."""

from .base import Agent
from .case_manager import CaseManagerAgent
from .graph_analyst import GraphAnalystAgent
from .narrative import NarrativeAgent
from .policy import PolicyAgent
from .reflector import ReflectorAgent
from .triage import TriageAgent

__all__ = [
    "Agent",
    "TriageAgent",
    "GraphAnalystAgent",
    "PolicyAgent",
    "CaseManagerAgent",
    "NarrativeAgent",
    "ReflectorAgent",
]


def build_default_agents(llm, *, graph, cases) -> dict[str, Agent]:
    """Factory used by the planner / API to build the canonical agent set."""

    return {
        "TriageAgent": TriageAgent(llm),
        "GraphAnalystAgent": GraphAnalystAgent(llm, graph=graph),
        "PolicyAgent": PolicyAgent(llm),
        "CaseManagerAgent": CaseManagerAgent(llm, cases=cases),
        "NarrativeAgent": NarrativeAgent(llm),
        "ReflectorAgent": ReflectorAgent(llm),
    }
