"""Optional challenge: find a synthetic query where lexical and vector retrieval disagree.

Every ranking comes from a live Azure AI Search call (no local similarity math).
Writes artifacts-challenge-disagreement.json in the lab folder.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from azure.core.exceptions import HttpResponseError  # noqa: E402
from azure.identity import DefaultAzureCredential  # noqa: E402
from azure.search.documents import SearchClient  # noqa: E402
from azure.search.documents.indexes import SearchIndexClient  # noqa: E402
from azure.search.documents.indexes.models import SearchIndex  # noqa: E402

from src.config import load_settings  # noqa: E402
from src.embeddings import create_embedding_client, embed_texts  # noqa: E402
from src.index_manager import INDEX_NAMES  # noqa: E402
from src.router import route_query  # noqa: E402
from src.search_pipeline import hybrid_semantic_search  # noqa: E402

STRATEGY = "structural-parent-child"
CANDIDATES = [
    # (synthetic query, expected parent judged by a reviewer for the *intent* of the query)
    ("Which drug review applies when a patient reports muscle pain?", "formulary-atorvastatin"),
    ("medication follow-up for kidney function decline", "formulary-metformin"),
    ("drug guidance on clarithromycin", "formulary-atorvastatin"),
    ("Which medication requires checking how well the kidneys filter blood?", "formulary-metformin"),
    ("medication follow-up when adherence questions arise", "formulary-metformin"),
]


def lexical(settings, credential, index_name, query):
    client = SearchClient(settings.search_endpoint, index_name, credential)
    started = time.perf_counter()
    rows = [
        {"id": r["id"], "parent_id": r["parent_id"], "search_score": r["@search.score"]}
        for r in client.search(search_text=query, filter=f"chunk_strategy eq '{STRATEGY}'", top=5,
                               select=["id", "parent_id"])
    ]
    return rows, round((time.perf_counter() - started) * 1000, 2)


def vector(settings, credential, embedding_client, index_name, query):
    started = time.perf_counter()
    rows = hybrid_semantic_search(
        settings.search_endpoint, index_name, credential, embedding_client, settings.embedding_deployment,
        settings.semantic_configuration, query, mode="vector", vector_field="optimized_vector",
        filter_expression=f"chunk_strategy eq '{STRATEGY}'",
    )
    return ([{"id": r["id"], "parent_id": r["parent_id"], "search_score": r["@search.score"]} for r in rows],
            round((time.perf_counter() - started) * 1000, 2))


def rr(rows, expected):
    for rank, row in enumerate(rows, 1):
        if row["parent_id"] == expected:
            return round(1 / rank, 4)
    return 0.0


def failure_investigation(settings, credential, embedding_client):
    """Drop a required field from a disposable index and classify the resulting failure."""
    name = "northwind-challenge-disposable"
    index_client = SearchIndexClient(settings.search_endpoint, credential)
    template = index_client.get_index(INDEX_NAMES["formulary"])
    fields = [f for f in template.fields if f.name != "section_heading"]
    index_client.create_or_update_index(SearchIndex(
        name=name, fields=fields, vector_search=template.vector_search, semantic_search=None))
    chunk = json.loads((ROOT / "artifacts-generated-chunks.json").read_text(encoding="utf-8"))["chunks"][0]
    vec = embed_texts(embedding_client, settings.embedding_deployment, [chunk["content"]])[0]
    document = {**chunk, "content_vector": vec, "optimized_vector": vec}
    try:
        SearchClient(settings.search_endpoint, name, credential).upload_documents([document])
        outcome = {"error": None, "classification": "no failure"}
    except HttpResponseError as error:
        outcome = {"error": str(error.message)[:400], "classification": (
            "schema (surfaced at ingestion): the index definition lacks 'section_heading', so the service rejects "
            "the whole upload batch before indexing; routing and grounding are never reached")}
    return {"disposable_index": name, "removed_field": "section_heading", **outcome}


def main() -> int:
    settings = load_settings()
    credential = DefaultAzureCredential()
    embedding_client = create_embedding_client(settings.openai_endpoint)
    trials = []
    for query, expected in CANDIDATES:
        for index_name in route_query(query):
            if index_name != INDEX_NAMES["formulary"]:
                continue
            lex, lex_ms = lexical(settings, credential, index_name, query)
            vec, vec_ms = vector(settings, credential, embedding_client, index_name, query)
            trials.append({
                "query": query, "routed_indexes": route_query(query), "index": index_name,
                "chunk_strategy": STRATEGY, "expected_parent_id": expected,
                "lexical": {"mode": "lexical-bm25", "top_parent": lex[0]["parent_id"] if lex else None,
                            "reciprocal_rank": rr(lex, expected), "latency_ms": lex_ms, "ranking": lex},
                "vector": {"mode": "vector", "embedding_profile": "content-aware",
                           "top_parent": vec[0]["parent_id"] if vec else None,
                           "reciprocal_rank": rr(vec, expected), "latency_ms": vec_ms, "ranking": vec},
            })
    disagreements = [t for t in trials if t["lexical"]["top_parent"] != t["vector"]["top_parent"]]
    selected = None
    if disagreements:
        t = max(disagreements, key=lambda t: abs(t["lexical"]["reciprocal_rank"] - t["vector"]["reciprocal_rank"]))
        winner = "lexical" if t["lexical"]["reciprocal_rank"] >= t["vector"]["reciprocal_rank"] else "vector"
        selected = {
            "query": t["query"], "selected_route": t["routed_indexes"],
            "winning_mode": winner, "winning_document": t[winner]["ranking"][0],
            "metric": "reciprocal rank of the expected parent (MRR over this single labeled query)",
            "lexical_rr": t["lexical"]["reciprocal_rank"], "vector_rr": t["vector"]["reciprocal_rank"],
        }
    result = {"trials": trials, "disagreement_count": len(disagreements), "selected": selected,
              "failure_investigation": failure_investigation(settings, credential, embedding_client)}
    (ROOT / "artifacts-challenge-disagreement.json").write_text(json.dumps(result, indent=2, default=str) + "\n",
                                                                encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, indent=2, default=str))
    for t in trials:
        print(t["query"], "| lexical:", t["lexical"]["top_parent"], "| vector:", t["vector"]["top_parent"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
