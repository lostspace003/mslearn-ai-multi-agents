from __future__ import annotations

from typing import Any

from azure.core.credentials import TokenCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI

from .embeddings import embed_texts


def hybrid_semantic_search(
    endpoint: str,
    index_name: str,
    credential: TokenCredential,
    embedding_client: AzureOpenAI,
    embedding_deployment: str,
    semantic_configuration: str,
    query: str,
    mode: str = "hybrid",
    vector_field: str = "content_vector",
    vector_weight: float = 0.7,
    top: int = 5,
    filter_expression: str | None = None,
) -> list[dict[str, Any]]:
    """Run vector-only, hybrid, or semantic ranking through Azure AI Search."""
    # LAB PLACEHOLDER 5: Replace this line with the Task 5 sample.
    if mode not in {"vector", "hybrid", "semantic"}:
        raise ValueError(f"Unsupported search mode: {mode}")
    if vector_field not in {"content_vector", "optimized_vector"}:
        raise ValueError(f"Unsupported vector field: {vector_field}")

    search_client = SearchClient(endpoint, index_name, credential)
    options: dict[str, Any] = {
        "search_text": None if mode == "vector" else query,
        "filter": filter_expression,
        "top": top,
        "select": [
            "id", "title", "source", "parent_id", "chunk_strategy",
            "boundary_start", "boundary_end", "section_heading", "content",
        ],
    }
    if mode in {"vector", "hybrid"}:
        query_vector = embed_texts(
            embedding_client, embedding_deployment, [query]
        )[0]
        options["vector_queries"] = [
            VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top,
                fields=vector_field,
                weight=vector_weight,
            )
        ]
    if mode in {"hybrid", "semantic"}:
        options.update(
            query_type="semantic",
            semantic_configuration_name=semantic_configuration,
            query_caption="extractive",
        )

    output = []
    for result in search_client.search(**options):
        row = dict(result)
        row["citation"] = f"{result['title']} ({result['source']}#{result['id']})"
        row["captions"] = [
            getattr(caption, "text", str(caption))
            for caption in (result.get("@search.captions") or [])
        ]
        output.append(row)
    return output
