from __future__ import annotations

from azure.core.credentials import TokenCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

INDEX_NAMES = {
    "formulary": "northwind-formulary-v1",
    "guidelines": "northwind-guidelines-v1",
    "labs": "northwind-labs-v1",
}


def create_or_update_indexes(
    endpoint: str,
    credential: TokenCredential,
    vector_dimensions: int,
    semantic_configuration: str,
) -> list[str]:
    """Create the three indexes needed by the routed retrieval pipeline."""
    # LAB PLACEHOLDER 1: Replace this line with the Task 1 sample.
    client = SearchIndexClient(endpoint=endpoint, credential=credential)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SimpleField(name="category", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="parent_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="chunk_order", type=SearchFieldDataType.Int32, sortable=True),
        SimpleField(name="chunk_strategy", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="boundary_start", type=SearchFieldDataType.Int32),
        SimpleField(name="boundary_end", type=SearchFieldDataType.Int32),
        SearchableField(name="section_heading", type=SearchFieldDataType.String),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=vector_dimensions,
            vector_search_profile_name="clinical-vector-profile",
        ),
        SearchField(
            name="optimized_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=vector_dimensions,
            vector_search_profile_name="clinical-vector-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="clinical-hnsw")],
        profiles=[
            VectorSearchProfile(
                name="clinical-vector-profile",
                algorithm_configuration_name="clinical-hnsw",
            )
        ],
    )
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=semantic_configuration,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="section_heading")],
                ),
            )
        ]
    )
    created = []
    for index_name in INDEX_NAMES.values():
        index = SearchIndex(
            name=index_name,
            fields=fields,
            vector_search=vector_search,
            semantic_search=semantic_search,
        )
        created.append(client.create_or_update_index(index).name)
    return created
