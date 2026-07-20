"""Cosmos DB clients (SQL + Gremlin) with an in-memory mock for tests/demos."""

from __future__ import annotations

import os
from typing import Any

from .state import CaseRecord


class BaseCases:
    async def upsert(self, case: CaseRecord) -> None: ...
    async def get(self, case_id: str) -> CaseRecord | None: ...
    async def list_ids(self) -> list[str]: ...


class InMemoryCases(BaseCases):
    def __init__(self) -> None:
        self._store: dict[str, CaseRecord] = {}

    async def upsert(self, case: CaseRecord) -> None:
        self._store[case.case_id] = case

    async def get(self, case_id: str) -> CaseRecord | None:
        return self._store.get(case_id)

    async def list_ids(self) -> list[str]:
        return list(self._store.keys())


class CosmosCases(BaseCases):  # pragma: no cover — exercised live, not in CI
    def __init__(
        self, endpoint: str, database: str, container: str, key: str | None = None
    ) -> None:
        from azure.cosmos.aio import CosmosClient

        # Prefer a data-plane key when supplied; otherwise fall back to the
        # container's managed identity via Entra ID (the pattern used across
        # this deployment, where Cosmos local auth may be locked down).
        if key:
            credential: object = key
        else:
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
        self._client = CosmosClient(endpoint, credential=credential)
        self._db = self._client.get_database_client(database)
        self._container = self._db.get_container_client(container)

    async def upsert(self, case: CaseRecord) -> None:
        item = case.model_dump(mode="json")
        item["id"] = case.case_id
        await self._container.upsert_item(item)

    async def get(self, case_id: str) -> CaseRecord | None:
        try:
            item = await self._container.read_item(item=case_id, partition_key=case_id)
        except Exception:
            return None
        item.pop("id", None)
        return CaseRecord.model_validate(item)

    async def list_ids(self) -> list[str]:
        ids: list[str] = []
        async for item in self._container.query_items("SELECT c.id FROM c"):
            ids.append(item["id"])
        return ids


class BaseGraph:
    async def two_hop(
        self, *, card_id: str | None, device_id: str | None, merchant_id: str | None
    ) -> dict[str, Any]: ...


class MockGraph(BaseGraph):
    """Deterministic mock for the Cosmos Gremlin API.

    Returns a fabricated 2-hop neighbourhood that resembles a coordinated card
    fraud ring so the demo narrative is meaningful.
    """

    async def two_hop(
        self,
        *,
        card_id: str | None = None,
        device_id: str | None = None,
        merchant_id: str | None = None,
    ) -> dict[str, Any]:
        device = device_id or "device-FP-7731"
        merchant = merchant_id or "merch-9001"
        cards = [card_id or "card-A1", "card-A2", "card-A3", "card-A4", "card-A5"]
        nodes = [
            {"id": device, "label": "device"},
            {"id": merchant, "label": "merchant"},
        ]
        nodes += [{"id": c, "label": "card"} for c in cards]
        edges = [{"from": c, "to": device, "label": "used_on"} for c in cards]
        edges += [
            {"from": c, "to": merchant, "label": "transacted_with"} for c in cards
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "anomaly_score": 0.91,
            "notes": [
                f"{len(cards)} cards share device fingerprint {device}",
                f"All cards transacted with merchant {merchant} within a 90-minute window",
                "Velocity exceeds 6σ baseline for this MCC",
            ],
        }


class GremlinGraph(BaseGraph):  # pragma: no cover
    def __init__(self, endpoint: str, database: str, graph: str, key: str) -> None:
        from gremlin_python.driver import client, serializer

        self._client = client.Client(
            endpoint,
            "g",
            username=f"/dbs/{database}/colls/{graph}",
            password=key,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )

    async def two_hop(
        self, *, card_id=None, device_id=None, merchant_id=None
    ) -> dict[str, Any]:
        anchor = card_id or device_id or merchant_id
        q = (
            f"g.V().has('id','{anchor}').repeat(both().simplePath()).times(2)"
            ".path().by(valueMap(true)).limit(50)"
        )
        result = self._client.submitAsync(q).result().all().result()
        return {
            "nodes": [],
            "edges": [],
            "anomaly_score": 0.0,
            "notes": [str(result)[:500]],
        }


def build_cases(mock: bool | None = None) -> BaseCases:
    if mock is None:
        mock = os.getenv("MOCK_COSMOS", "true").lower() == "true"
    # Degrade gracefully to the in-memory store when not explicitly real or when
    # the Cosmos endpoint is not configured.
    if mock or not os.getenv("COSMOS_ENDPOINT"):
        return InMemoryCases()
    return CosmosCases(
        endpoint=os.environ["COSMOS_ENDPOINT"],
        database=os.environ.get("COSMOS_DATABASE", "fraudintel"),
        container=os.environ.get("COSMOS_CASES_CONTAINER", "cases"),
        key=os.getenv("COSMOS_KEY") or None,
    )


def build_graph(mock: bool | None = None) -> BaseGraph:
    if mock is None:
        mock = os.getenv("MOCK_COSMOS", "true").lower() == "true"
    # The Gremlin graph is optional; when its endpoint is absent (e.g. a SQL-API
    # only account) fall back to the deterministic mock graph rather than crash.
    if mock or not os.getenv("GREMLIN_ENDPOINT"):
        return MockGraph()
    return GremlinGraph(
        endpoint=os.environ["GREMLIN_ENDPOINT"],
        database=os.environ.get("GREMLIN_DATABASE", "fraudintel"),
        graph=os.environ.get("GREMLIN_GRAPH", "fraud-graph"),
        key=os.environ["GREMLIN_KEY"],
    )
