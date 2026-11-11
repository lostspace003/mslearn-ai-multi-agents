# Lab 07 - Design review (Task 7)

## Task 2 chunking observations

All six parent documents are explicitly synthetic and training-only. `size_chars=180` with `overlap_chars=40` gives
16 fixed-overlap chunks with windows like 0-180, 140-320, 280-387. These windows ignore section boundaries and leave out
the title and heading, so a chunk can open mid-sentence or mix two sections. The 40-character overlap reduces lost
context at the cuts, but the overlapping text is indexed and embedded twice. The structural parent-child strategy gives
12 chunks, one per section. Each starts with the parent title and the section heading, so every chunk can be found by
drug or test name and explains itself. The cost is repeated title text, which can inflate lexical matches on the title
alone.

## Questions

**Which query types should disable semantic query rewrite to preserve exact identifiers?**
Turn off rewriting for exact-identifier lookups: drug names (for example "atorvastatin", "clarithromycin"), lab test
codes and units, document and chunk IDs, policy and formulary version labels, and dosage or numeric-range strings. A
rewrite can replace these with synonyms, normalize them, or drop them. Route these queries lexical-first, or hybrid
with rewriting off. Keep rewriting for broad conceptual questions such as "how should diabetes therapy and monitoring
be coordinated?".

**What evidence would justify adding a cross-encoder after semantic ranking?**
You would need a larger, representative set of labeled queries where semantic ranking still leaves the expected parent
outside the top positions. In this lab, MRR is already 1.0 for every strategy, mode, and profile, so there is nothing
to gain here. The evidence would need to show a statistically meaningful MRR or nDCG improvement from the cross-encoder
on held-out queries, with the extra latency and cost per query measured and inside budget. It should also show no
regression on exact-identifier queries.

**How should source health alter routing without changing intent classification?**
Keep intent classification pure: query text in, categories out. Apply source health afterwards, as a separate policy
step on the index list the router returns. That step can:
- skip or deprioritize an index that is unhealthy or stale (failed ingestion, low document count, outage);
- fall back to a replica or the previous index version;
- widen fan-out when the primary source is degraded;
- report the degraded source in the result so the caller knows coverage was reduced.

It should never silently drop a source without recording that it did so.

**Which retrieval fields are safe to include in agent context?**
Include `content`, `title`, `section_heading`, `source`, `parent_id`, the chunk `id`, `chunk_strategy`, the boundary
offsets, and the citation string. These are the grounding text and its lineage. Do not pass in the vector fields
(`content_vector`, `optimized_vector`). They are large, unreadable, and could expose the embedding model. Raw scores
are retrieval diagnostics and belong in evaluation logs rather than the prompt. Captions are optional. They are
extracts of `content`, so the same rules apply to them. Admin metadata, keys, and endpoints never go into agent context.
