# Lab 05 - Task 7 design review

**Which attacks need more than lexical detection?**
Paraphrased, obfuscated (homoglyphs, spacing, encoding/base64, other languages), multi-turn "slow" injections
split across turns, role-play/social-engineering requests, and indirect injections embedded in tool/retrieved
content that never use the trigger phrases. The investigation showed that dropping a single regex let
`indirect-01` and a new paraphrased attack reach the model. These need semantic classifiers (e.g. prompt-shield
style detection), strict trust boundaries/delimiting, least-privilege tools, and output validation as backstops.

**Which guardrail should own a malicious tool response?**
The tool-response guardrail (`guard_tool_response`): it runs before tool data is reinjected into the
conversation, enforces the field allowlist, the clinician-review flag, injection scanning and redaction. The
output guardrail is a second line of defence, not the owner.

**What metric can improve while clinical safety regresses?**
`pass_rate` (or format/schema compliance, latency, cost, helpfulness scores). A prompt can produce more
valid four-field JSON while its content becomes more diagnostic or omits escalation, or `blocked_count`
can drop because attacks slipped past input checks. Track safety-specific metrics (unsafe-language
rejections, escalation recall, attack block rate, clinician-review flags) alongside pass rate.

**What evidence would justify fine-tuning instead of another prompt or retrieval change?**
A sufficient, representative set of deidentified, clinician-reviewed target conversations with provenance
(the manifest currently shows 0), plus regression evidence that well-versioned prompt and retrieval changes
have plateaued on a persistent, style/format/domain-behaviour gap (not a knowledge-freshness gap, which is
retrieval's job), and an evaluation harness that can show the tuned model improves the target metric without
regressing safety and attack-block results.
