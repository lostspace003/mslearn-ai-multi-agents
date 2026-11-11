from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from .config import load_settings
from .consistency import validate_read_your_writes
from .context_budget import select_context
from .embeddings import EmbeddingService
from .memory_store import PatientMemoryStore
from .retention import prune_memories


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Northwind Health memory lab")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--file", type=Path, required=True)
    recall = commands.add_parser("recall")
    recall.add_argument("--patient-id", required=True)
    recall.add_argument("--query", required=True)
    recall.add_argument("--top", type=int, default=5)
    recall.add_argument("--budget", type=int, default=500)
    consistency = commands.add_parser("consistency")
    consistency.add_argument("--patient-id", required=True)
    prune = commands.add_parser("prune")
    prune.add_argument("--patient-id", required=True)
    prune.add_argument("--dry-run", action="store_true")
    consolidate = commands.add_parser("consolidate")
    consolidate.add_argument("--patient-id", required=True)
    consolidate.add_argument("--source-id", action="append", required=True)
    consolidate.add_argument("--summary", required=True)
    consolidate.add_argument("--reviewer-id", required=True)
    consolidate.add_argument("--dry-run", action="store_true")
    consolidate.add_argument("--min-confidence", type=float, default=None)
    return parser


async def _run() -> None:
    args = _parser().parse_args()
    settings = load_settings()
    patient_id = getattr(args, "patient_id", "synthetic-patient-100")
    store = PatientMemoryStore(
        settings.cosmos_endpoint,
        settings.database_name,
        settings.memory_container,
        settings.audit_container,
        patient_id,
        EmbeddingService(settings.openai_endpoint, settings.embedding_deployment),
    )
    try:
        if args.command == "ingest":
            output = [await store.upsert_memory(item) for item in json.loads(args.file.read_text(encoding="utf-8")) if item["patientId"] == patient_id]
        elif args.command == "recall":
            memories = await store.vector_recall(patient_id, args.query, args.top)
            output = {
                "retrieved_memories": memories,
                "bounded_context": select_context(memories, args.budget),
            }
        elif args.command == "consistency":
            memory = {
                "id": f"consistency-{datetime.now(UTC).timestamp()}",
                "patientId": patient_id,
                "content": "Synthetic immediate read-your-writes validation record.",
                "importance": 5.0,
                "memoryType": "episodic",
                "critical": False,
                "timestamp": datetime.now(UTC).isoformat(),
                "ttl": 3600,
                "schemaVersion": "1.0",
            }
            output = await validate_read_your_writes(store, memory)
        elif args.command == "prune":
            memories = await store.vector_recall(patient_id, "retention review", 20)
            output = await prune_memories(store, patient_id, memories, args.dry_run)
        else:
            output = await store.consolidate_episodic_memories(
                patient_id,
                args.source_id,
                args.summary,
                args.reviewer_id,
                args.dry_run,
                args.min_confidence,
            )
        print(json.dumps(output, indent=2, default=str))
    finally:
        await store.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()