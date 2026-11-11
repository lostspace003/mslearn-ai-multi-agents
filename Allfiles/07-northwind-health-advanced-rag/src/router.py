from __future__ import annotations

from .index_manager import INDEX_NAMES


def route_query(query: str) -> list[str]:
    """Route a query to one or more specialized Azure AI Search indexes."""
    # LAB PLACEHOLDER 4: Replace this line with the Task 4 sample.
    normalized = query.casefold()
    intent_terms = {
        "formulary": {"medication", "drug", "atorvastatin", "contraindication", "therapy"},
        "guidelines": {"guideline", "protocol", "recommendation", "coordinate", "how should"},
        "labs": {"lab", "a1c", "range", "test", "monitoring"},
    }
    matched = [
        category
        for category, terms in intent_terms.items()
        if any(term in normalized for term in terms)
    ]
    if len(matched) != 1:
        return list(INDEX_NAMES.values())
    return [INDEX_NAMES[matched[0]]]
