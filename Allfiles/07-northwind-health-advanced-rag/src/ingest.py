from __future__ import annotations

from typing import Any

from azure.core.credentials import TokenCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI

from .embeddings import embed_texts
from .experiment import embedding_text
from .index_manager import INDEX_NAMES


def upload_documents(
    endpoint: str,
    credential: TokenCredential,
    embedding_client: AzureOpenAI,
    embedding_deployment: str,
    documents: list[dict[str, Any]],
) -> dict[str, int]:
    """Embed and upload both generated chunk strategies to category indexes."""
    # LAB PLACEHOLDER 3: Replace this line with the Task 3 sample.
    baseline_vectors = embed_texts(
        embedding_client,
        embedding_deployment,
        [embedding_text(document, "baseline") for document in documents],
    )
    optimized_vectors = embed_texts(
        embedding_client,
        embedding_deployment,
        [embedding_text(document, "content-aware") for document in documents],
    )
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for document, baseline, optimized in zip(
        documents, baseline_vectors, optimized_vectors, strict=True
    ):
        upload_document = {
            **document,
            "content_vector": baseline,
            "optimized_vector": optimized,
        }
        key = (str(document["category"]), str(document["chunk_strategy"]))
        groups.setdefault(key, []).append(upload_document)

    counts: dict[str, int] = {}
    for (category, strategy), group in groups.items():
        client = SearchClient(endpoint, INDEX_NAMES[category], credential)
        results = client.upload_documents(group)
        failed = [result.key for result in results if not result.succeeded]
        if failed:
            raise RuntimeError(f"Index upload failed for document keys: {failed}")
        counts[f"{strategy}:{category}"] = len(results)
    return counts
