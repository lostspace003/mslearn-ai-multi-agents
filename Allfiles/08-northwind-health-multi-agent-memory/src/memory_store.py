from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from azure.cosmos import ConsistencyLevel
from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from .embeddings import EmbeddingService


class PatientMemoryStore:
    def __init__(
        self,
        endpoint: str,
        database_name: str,
        memory_container: str,
        audit_container: str,
        session_patient_id: str,
        embedding_service: EmbeddingService,
    ) -> None:
        self._credential = DefaultAzureCredential()
        self._client = CosmosClient(endpoint, credential=self._credential, consistency_level=ConsistencyLevel.Session)
        database = self._client.get_database_client(database_name)
        self._memories = database.get_container_client(memory_container)
        self._audit = database.get_container_client(audit_container)
        self._session_patient_id = session_patient_id
        self._embeddings = embedding_service

    def _authorize(self, patient_id: str) -> None:
        if patient_id != self._session_patient_id:
            raise PermissionError(f"Session is not authorized for patient {patient_id}")

    async def upsert_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        """Persist one memory and return request diagnostics including session token."""
        # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
        patient_id = str(memory["patientId"])
        self._authorize(patient_id)
        item = {
            **memory,
            "embedding": self._embeddings.embed(str(memory["content"])),
        }
        response = await self._memories.upsert_item(item)
        headers = response.get_response_headers()
        return {
            "id": response["id"],
            "patientId": response["patientId"],
            "request_charge": float(headers.get("x-ms-request-charge", 0)),
            "session_token": headers.get("x-ms-session-token"),
        }

    async def vector_recall(self, patient_id: str, query_text: str, top_k: int) -> list[dict[str, Any]]:
        """Run a partition-scoped vector query ordered by VectorDistance."""
        # LAB PLACEHOLDER 2: Replace this line with the Task 2 sample.
        self._authorize(patient_id)
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
            raise ValueError("top_k must be an integer from 1 through 20")
        embedding = self._embeddings.embed(query_text)
        query = f"""
            SELECT TOP {top_k}
                c.id, c.patientId, c.content, c.importance, c.memoryType,
                c.critical, c.timestamp, c.ttl,
                VectorDistance(c.embedding, @embedding) AS vector_distance
            FROM c
            WHERE c.patientId = @patientId
            ORDER BY VectorDistance(c.embedding, @embedding)
        """
        response_headers: dict[str, str] = {}
        iterator = self._memories.query_items(
            query=query,
            parameters=[
                {"name": "@patientId", "value": patient_id},
                {"name": "@embedding", "value": embedding},
            ],
            partition_key=patient_id,
            response_hook=lambda headers, _: response_headers.update(headers),
        )
        results = [item async for item in iterator]
        request_charge = float(response_headers.get("x-ms-request-charge", 0))
        for item in results:
            item["request_charge"] = request_charge
        return results

    async def write_audit(
        self,
        patient_id: str,
        operation: str,
        memory_ids: list[str],
        reason: str,
        event_id: str | None = None,
        event_timestamp: str | None = None,
    ) -> None:
        """Write content-free audit metadata for a memory operation."""
        # LAB PLACEHOLDER 3: Replace this line with the Task 3 sample.
        self._authorize(patient_id)
        await self._audit.upsert_item(
            {
                "id": event_id or str(uuid4()),
                "patientId": patient_id,
                "operation": operation,
                "memoryIds": sorted(set(memory_ids)),
                "reason": reason,
                "timestamp": event_timestamp or datetime.now(UTC).isoformat(),
            }
        )

    async def consolidate_episodic_memories(
        self,
        patient_id: str,
        source_ids: list[str],
        semantic_content: str,
        reviewer_id: str,
        dry_run: bool,
        min_confidence: float | None = None,
    ) -> dict[str, Any]:
        """Consolidate reviewed episodic records into one persisted semantic pattern."""
        self._authorize(patient_id)
        unique_ids = sorted(set(source_ids))
        if len(unique_ids) < 2:
            raise ValueError("Consolidation requires at least two distinct episodic memories")
        if len(unique_ids) > 99:
            raise ValueError("Consolidation supports at most 99 sources in one transactional batch")
        if not semantic_content.strip() or len(semantic_content) > 1000:
            raise ValueError("Semantic content must contain 1-1000 characters")
        if not reviewer_id.strip():
            raise ValueError("A reviewer ID is required")

        sources = [
            await self._memories.read_item(item=memory_id, partition_key=patient_id)
            for memory_id in unique_ids
        ]
        if any(source.get("memoryType") != "episodic" for source in sources):
            raise ValueError("Every consolidation source must be episodic")
        # Optional challenge: confidence gate. Sources below the documented threshold stay
        # untouched in source history and are excluded from the consolidated pattern.
        rejected_ids: list[str] = []
        if min_confidence is not None:
            if not 0.0 <= min_confidence <= 1.0:
                raise ValueError("min_confidence must be between 0.0 and 1.0")
            rejected_ids = [
                str(source["id"])
                for source in sources
                if float(source.get("confidence", 0.0)) < min_confidence
            ]
            sources = [source for source in sources if str(source["id"]) not in rejected_ids]
            unique_ids = [str(source["id"]) for source in sources]
            if len(unique_ids) < 2:
                raise ValueError("Fewer than two sources meet the confidence threshold")
        digest = hashlib.sha256(f"{patient_id}:{':'.join(unique_ids)}".encode()).hexdigest()[:16]
        semantic_id = f"semantic-{digest}"
        consolidation_targets = {
            str(source["consolidatedInto"])
            for source in sources
            if source.get("consolidatedInto")
        }
        if all(
            source.get("consolidatedInto") == semantic_id
            for source in sources
        ):
            semantic = await self._memories.read_item(
                item=semantic_id,
                partition_key=patient_id,
            )
            if semantic.get("sourceMemoryIds") != unique_ids:
                raise RuntimeError("Existing semantic memory has inconsistent source lineage")
            if (
                semantic.get("content") != semantic_content.strip()
                or semantic.get("reviewerId") != reviewer_id
            ):
                raise ValueError(
                    "Retry input does not match the completed semantic consolidation"
                )
            await self.write_audit(
                patient_id,
                "consolidate_episodic_to_semantic",
                [*unique_ids, semantic_id],
                f"reviewed pattern consolidation by {reviewer_id}",
                event_id=f"audit-{semantic_id}",
                event_timestamp=str(semantic["timestamp"]),
            )
            return {
                "status": "already_consolidated",
                "semantic_memory_id": semantic_id,
                "source_memory_ids": unique_ids,
                "rejected_source_ids": rejected_ids,
                "source_records_retained": True,
                "ttl": int(semantic["ttl"]),
            }
        if consolidation_targets:
            raise ValueError("A source memory has already been consolidated")

        critical = any(bool(source.get("critical")) for source in sources)
        positive_ttls = [int(source["ttl"]) for source in sources if int(source.get("ttl", 0)) > 0]
        ttl = -1 if critical else max(positive_ttls, default=2592000)
        semantic = {
            "id": semantic_id,
            "patientId": patient_id,
            "content": semantic_content.strip(),
            "importance": round(sum(float(source.get("importance", 0)) for source in sources) / len(sources), 2),
            "memoryType": "semantic_pattern",
            "critical": critical,
            "timestamp": datetime.now(UTC).isoformat(),
            "ttl": ttl,
            "schemaVersion": "1.0",
            "sourceMemoryIds": unique_ids,
            "reviewerId": reviewer_id,
            "retentionPolicy": "preserve-source-lineage",
        }
        if min_confidence is not None:
            semantic["confidenceThreshold"] = min_confidence
            semantic["rejectedSourceIds"] = rejected_ids
        if dry_run:
            return {"status": "dry_run", "semantic_memory": semantic, "source_count": len(sources)}

        semantic["embedding"] = self._embeddings.embed(str(semantic["content"]))
        batch_operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
            ("create", (semantic,), {}),
        ]
        for source in sources:
            batch_operations.append(
                (
                    "patch",
                    (
                        source["id"],
                        [
                            {"op": "add", "path": "/consolidatedInto", "value": semantic_id},
                            {"op": "add", "path": "/consolidatedAt", "value": semantic["timestamp"]},
                        ],
                    ),
                    {"if_match_etag": source["_etag"]},
                )
            )
        batch_results = await self._memories.execute_item_batch(
            batch_operations=batch_operations,
            partition_key=patient_id,
        )
        await self.write_audit(
            patient_id,
            "consolidate_episodic_to_semantic",
            [*unique_ids, semantic_id],
            f"reviewed pattern consolidation by {reviewer_id}",
            event_id=f"audit-{semantic_id}",
            event_timestamp=str(semantic["timestamp"]),
        )
        return {
            "status": "consolidated",
            "semantic_memory_id": semantic_id,
            "source_memory_ids": unique_ids,
            "rejected_source_ids": rejected_ids,
            "source_records_retained": True,
            "ttl": ttl,
            "write_diagnostics": {
                "transactional_batch": True,
                "operation_count": len(batch_results),
            },
        }

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()