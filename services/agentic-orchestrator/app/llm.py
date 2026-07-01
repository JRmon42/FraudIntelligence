"""LLM client wrapper around Azure OpenAI with a deterministic mock mode.

The mock mode allows tests and the offline demo to run without Azure
credentials while still exercising the full agent / planner code paths.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMMessage:
    role: str
    content: str


class BaseLLM:
    is_mock: bool = False

    async def chat(self, messages: list[LLMMessage], tools: list[dict] | None = None, **kwargs: Any) -> dict:
        raise NotImplementedError


class MockLLM(BaseLLM):
    """Deterministic stub used when ``--mock-llm`` is enabled.

    It inspects the *system* role message for a routing hint (the agent name)
    and returns a canned response shaped like an Azure OpenAI response.
    """

    is_mock = True

    CANNED: dict[str, dict[str, Any]] = {
        "TriageAgent": {
            "classification": "suspected_fraud_ring",
            "rationale": (
                "High-velocity authorisations across multiple cards sharing a device fingerprint "
                "and a single merchant MCC indicate a coordinated fraud ring."
            ),
            "recommended_agents": ["GraphAnalystAgent", "PolicyAgent", "NarrativeAgent"],
        },
        "PolicyAgent": {
            "sca_exemptions_applied": [],
            "sca_exemptions_blocked": ["low_value", "trusted_beneficiary"],
            "eba_categories": ["fraud_card_not_present", "organised_fraud"],
            "rationale": (
                "PSD2 RTS Art. 16 low-value exemption is blocked because cumulative spend exceeds "
                "EUR 100 in 24h. EBA reporting under category C (organised fraud) is required."
            ),
        },
        "NarrativeAgent": {
            "sar": (
                "## Suspicious Activity Report\n\n"
                "Subject: Coordinated card-not-present fraud ring detected on {date}.\n\n"
                "A network of {n_cards} payment cards transacted with merchant {merchant_id} via "
                "shared device fingerprint {device_id} within a 90-minute window. The aggregate "
                "exposure is {amount} {currency}. Graph analysis revealed a 2-hop neighbourhood "
                "containing {n_nodes} entities with anomaly score {anomaly_score:.2f}.\n\n"
                "Recommended action: freeze affected cards, file SAR with the FIU, and notify the "
                "acquirer."
            ),
            "eba": (
                "## EBA Fraud Reporting Narrative\n\n"
                "Reporting category: organised fraud (C). Channel: card-not-present. "
                "PSD2 SCA was enforced; no exemption applied. Loss event classified as confirmed "
                "fraud per EBA Guidelines on Fraud Reporting under PSD2."
            ),
        },
        "ReflectorAgent": {
            "verdict": "accept",
            "reason": "All required artefacts (graph, policy, narrative) are present and consistent.",
            "missing_steps": [],
        },
    }

    async def chat(self, messages: list[LLMMessage], tools: list[dict] | None = None, **kwargs: Any) -> dict:
        agent_hint = ""
        for m in messages:
            if m.role == "system" and m.content.startswith("AGENT:"):
                agent_hint = m.content.split("AGENT:", 1)[1].strip().split()[0]
                agent_hint = agent_hint.rstrip(".,;:")
                break
        payload = self.CANNED.get(agent_hint, {"text": "ok"})
        return {
            "content": json.dumps(payload),
            "tool_calls": [],
            "model": "mock-gpt-4o",
            "agent_hint": agent_hint,
        }


class AzureOpenAILLM(BaseLLM):
    """Thin Azure OpenAI Chat Completions wrapper using ``httpx``.

    Kept intentionally minimal — production deployments should swap this for
    the official ``openai`` SDK. We avoid that dependency here so the service
    can be installed in air-gapped CI environments.
    """

    # Entra ID token scope for Azure OpenAI (used when key auth is disabled).
    _AAD_SCOPE = "https://cognitiveservices.azure.com/.default"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-06-01",
        use_aad: bool = False,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        # When the Azure OpenAI account has local (key) auth disabled we must use
        # a managed-identity / Entra ID bearer token instead of an api-key header.
        self.use_aad = use_aad
        self._credential: Any = None

    async def _auth_headers(self) -> dict[str, str]:
        if not self.use_aad:
            return {"api-key": self.api_key}
        if self._credential is None:
            from azure.identity.aio import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
        token = await self._credential.get_token(self._AAD_SCOPE)
        return {"Authorization": f"Bearer {token.token}"}

    async def chat(self, messages: list[LLMMessage], tools: list[dict] | None = None, **kwargs: Any) -> dict:
        import httpx

        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
        body: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.1),
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = kwargs.get("tool_choice", "auto")
        # Force strictly-valid JSON output when the caller asks for it, so agent
        # parsers don't choke on Markdown/code-fence wrapping from the model.
        response_format = kwargs.get("response_format")
        if response_format:
            body["response_format"] = response_format

        headers = {"content-type": "application/json", **(await self._auth_headers())}
        params = {"api-version": self.api_version}

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, params=params, json=body)
            r.raise_for_status()
            data = r.json()
        choice = data["choices"][0]["message"]
        return {
            "content": choice.get("content") or "",
            "tool_calls": choice.get("tool_calls") or [],
            "model": data.get("model", self.deployment),
        }


def build_llm(mock: bool | None = None) -> BaseLLM:
    if mock is None:
        mock = os.getenv("MOCK_LLM", "false").lower() == "true"
    if mock:
        return MockLLM()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
    use_aad = os.getenv("AZURE_OPENAI_USE_AAD", "false").lower() == "true"
    if not endpoint or not (api_key or use_aad):
        # Degrade gracefully — never crash the service on missing creds.
        return MockLLM()
    return AzureOpenAILLM(endpoint, api_key, deployment, api_version, use_aad=use_aad)
