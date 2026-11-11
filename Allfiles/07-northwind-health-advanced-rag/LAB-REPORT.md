# Lab 07 report - Implement advanced RAG with Azure AI Search

**Result: PASS**. Every acceptance criterion is met with live Azure evidence. The optional challenge was also completed.

| Item | Value |
|---|---|
| Resource group | `rg-lab07-80fce608` |
| Region | `eastus` (eastus2 had no Azure AI Search capacity, see Deviations) |
| Search service | `srchlab0780fce6qeqiwblx` (Standard, `disableLocalAuth: true`, semantic ranker free tier) |
| Azure OpenAI | `aoailab0780fce6qeqiwblx`, deployment `text-embedding-3-small` (GlobalStandard) |
| Auth | `DefaultAzureCredential` (az CLI user). No keys in `.env`. |

## Per-task work

1. **Prepare:** read the lab and the assets. All assets are synthetic. `assets/documents.json` is only a deprecation marker and was not ingested.
2. **Virtual environment and chunks:** ran `scripts/setup.ps1` to create `.venv`, then `generate-chunks` to write `artifacts-generated-chunks.json` (console output is in `artifacts-generate-chunks-output.txt`). Fixed-overlap produced 16 chunks and structural-parent-child produced 12. Both cover the same six parent IDs. The generated file was not hand-edited.
3. **Deploy:** used the Azure CLI deployment helper in place of azd. The Bicep template assigns Search Service Contributor, Search Index Data Contributor and Cognitive Services OpenAI User to the signed-in user. The helper also adds Azure AI User and Azure AI Developer at resource-group scope. `.env` holds `AZURE_SEARCH_ENDPOINT`, `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, with no keys.
4. **Implement:** filled LAB PLACEHOLDERs 1-5 in `src/index_manager.py`, `src/embeddings.py`, `src/ingest.py`, `src/router.py` and `src/search_pipeline.py`. The snippets were copied unchanged except that their 2-space indentation was converted to the source files' 4-space indentation. The marker comments are kept.
5. **Run:** ran `create-indexes`, `ingest`, the 7 searches one at a time (`artifacts-search-1.txt` to `artifacts-search-7.txt`), and `compare` (`artifacts-retrieval-comparison.json`, 50 trials).
6. **Validate:** results are in the table below. The final checks are in `artifacts-final-checks.txt`.
7. **Design review:** see `design-review.md`.
8. **Cleanup:** not run, as the brief instructed. Resources, `.env` and artifacts are kept.

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| `create-indexes` reports three index names and their semantic configuration | PASS | `artifacts-create-indexes.txt` lists `northwind-formulary-v1`, `northwind-guidelines-v1` and `northwind-labs-v1`, each created with `clinical-semantic-config`. |
| Chunk artifact records both configurations, chunk counts, every boundary, and the same 6 parents | PASS | fixed-overlap (180/40) has 16 chunks; structural-parent-child (`include_parent_title`) has 12. Both cover all 6 parent IDs. Preflight confirms this. |
| `ingest` succeeded for every chunk, separated by strategy and category | PASS | `artifacts-ingest.txt`: fixed 6/5/5 and structural 4/4/4. Live `$count` via REST returns formulary 10, guidelines 9, labs 9, which matches the expected portal counts. |
| The atorvastatin query routes to formulary and returns exact-name and vector candidates | PASS | Searches 1, 2, 5, 6 and 7 route only to `northwind-formulary-v1`. In hybrid mode the atorvastatin chunks rank first (RRF scores about 0.028), followed by vector-only metformin candidates (about 0.011). |
| The A1C query routes to labs and has a reranker score or caption | PASS | `artifacts-search-3.txt`: routed only to `northwind-labs-v1`. Top result `structural-parent-child-labs-a1c-001` has `@search.reranker_score` 2.44 and an extractive caption. |
| The multi-factor query searches all three indexes with source-specific citations | PASS | `artifacts-search-4.txt` covers all three indexes. Example citations: `Metformin synthetic monograph (synthetic-formulary-v2#...)`, `Synthetic diabetes follow-up guideline (synthetic-guidelines-v2#...)`, `Synthetic A1C reference (synthetic-lab-reference-v2#...)`. |
| Vector-only and hybrid rankings compared (same query, strategy and profile) | PASS | Atorvastatin, fixed-overlap, baseline profile. Vector order: atorvastatin-000, -001, metformin-001, metformin-000, metformin-002. Hybrid order: atorvastatin-001, -002, -000, metformin-001, metformin-000. The order changed, and both come from live service calls. |
| Every trial identifies one strategy, query, index, mode and profile; ranking holds child and parent IDs; scores and latency come from the same call | PASS | All 50 trials in `artifacts-retrieval-comparison.json` have these fields, with `ranking[{id, parent_id}]` and `scores[{search_score, reranker_score}]`. |
| `aggregates` reports MRR and average latency by strategy, mode and profile | PASS | 10 aggregate rows, each with MRR 1.00. Structural-parent-child is about 250-800 ms faster on average in every mode, with 12 chunks against 16. |
| Final checks: preflight, py_compile, Bicep build | PASS | `artifacts-final-checks.txt`: `Preflight passed`, every `py_compile` exits 0, and `az bicep build` exits 0. |

**Strategy note.** MRR is 1.0 everywhere, so these three queries cannot tell the two strategies apart on quality. Structural-parent-child uses fewer chunks (12 against 16) and was slightly faster here. That makes it the cheaper choice, but a larger evaluation set is needed before choosing it on quality.

## Optional challenge

`scripts/challenge_disagreement.py` produced `artifacts-challenge-disagreement.json` and `artifacts-challenge-output.txt`. All rankings in it come from live Azure AI Search calls.

- **Disagreement found.** The query "Which medication requires checking how well the kidneys filter blood?" routes to formulary (structural-parent-child chunks). Lexical BM25 ranks atorvastatin first, with the metformin parent's reciprocal rank at 0.33. Vector search (content-aware profile) ranks metformin first: `formulary-metformin-000`, score 0.643, reciprocal rank 1.0. The winning mode is vector. The metric used is the reciprocal rank of the labeled expected parent.
- **Failure investigation.** A disposable index `northwind-challenge-disposable` was created without `section_heading`. Uploading a chunk then failed with: "The property 'section_heading' does not exist on type 'search.documentFields'". This is a schema failure that shows up at ingestion. The whole batch is rejected, so routing and grounding never run.

## Deviations and fixes

- **No shipped lab code was fixed.** Everything ran as provided.
- **Region.** The first deployment attempt in eastus2 failed with `InsufficientResourcesAvailable` for Azure AI Search. It left resource group `rg-lab07-9a78e117` (eastus2) containing one orphaned Azure OpenAI account, `aoailab079a78e15jodzlgc`, with no model deployment. I did not delete it. The lab was then deployed successfully to `eastus` in `rg-lab07-80fce608`.
- **Generated Bicep output.** `az bicep build` (a lab command) wrote `infra/main.json`.
- **Extra Azure resources and files.** The disposable challenge index `northwind-challenge-disposable` is still in the search service. The challenge script `scripts/challenge_disagreement.py` was added to the lab folder.
- **Latency.** Trial latency (about 3.5-5.7 s) includes embedding the query and acquiring a token for each call. Each call builds a new client.

## Left for the user

- Portal check of the index list (Task 5, steps 2-7). It was verified through the REST `$count` instead.
- Cleanup (Task 8), whenever you choose. To remove everything: `az group delete -n rg-lab07-80fce608` and `az group delete -n rg-lab07-9a78e117`, then purge the soft-deleted Azure OpenAI accounts.
