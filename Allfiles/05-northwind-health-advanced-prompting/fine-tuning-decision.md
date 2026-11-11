# Fine-tuning readiness decision (Lab 05)

## Manifest result (`artifacts-training-candidates.manifest.json`)

| Field | Value |
|---|---|
| Source | `assets/prompt-cases.jsonl`, sha256 `216a66fb7a22d68c6d06bfbfb7f844d6d0cee4212d659f0cada55509e2a35ed6` |
| Source record count | **3** |
| Output | `artifacts-training-candidates.jsonl`, sha256 `7eb70257...61a6` (empty file) |
| Output record count | **0** |
| Filters | reviewed=true, deidentified=true, consent=synthetic, schema-valid |
| Provenance / reviewer IDs (eligible rows) | none |

## Decision: **NO-GO** for supervised fine-tuning

- All three rows are evaluation cases (`patient_text` + `expected` label). None carries a `messages`
  array with a clinician-approved assistant target, so every row fails the system/user/assistant schema filter.
- No training job or fine-tuned deployment was created.

## Next steps

- Collect representative, deidentified, clinician-reviewed target responses (with provenance and reviewer ID)
  before reconsidering SFT.
- Meanwhile continue prompt (v1.1.0 contract), retrieval, and evaluation improvements; prompt 1.1.0 already
  satisfies the output contract that 1.0.0 failed.
