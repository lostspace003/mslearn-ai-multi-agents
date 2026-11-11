from __future__ import annotations

from typing import Any


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def select_context(memories: list[dict[str, Any]], token_budget: int) -> dict[str, Any]:
    """Select important and recent memories without exceeding a token budget."""
    # LAB PLACEHOLDER 5: Replace this line with the Task 5 sample.
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    recent_count = max(1, (len(memories) * 3 + 9) // 10) if memories else 0
    recent = sorted(memories, key=lambda item: str(item["timestamp"]), reverse=True)[:recent_count]
    ranked = sorted(
        memories,
        key=lambda item: (
            float(item.get("importance", 0)) * 0.5
            + (1.0 / (1.0 + float(item.get("vector_distance", 1)))) * 0.5
        ),
        reverse=True,
    )
    ordered = recent + [item for item in ranked if item not in recent]
    selected: list[dict[str, Any]] = []
    blocks: list[str] = []
    used = estimate_tokens("<patient_memory>\n</patient_memory>")
    for item in ordered:
        block = f"<memory id=\"{item['id']}\">{item['content']}</memory>"
        cost = estimate_tokens(block)
        if used + cost <= token_budget:
            selected.append(item)
            blocks.append(block)
            used += cost
    return {
        "selected_ids": [item["id"] for item in selected],
        "token_count": used,
        "context": "<patient_memory>\n" + "\n".join(blocks) + "\n</patient_memory>",
    }