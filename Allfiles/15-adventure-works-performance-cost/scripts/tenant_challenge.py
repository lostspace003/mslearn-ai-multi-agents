"""Optional challenge: isolate cache entries by synthetic tenant (no model calls).

Run from the lab folder:  python scripts/tenant_challenge.py
Creates tenant-scoped result/prompt keys for one synthetic request under two tenants, invalidates
tenant A only, verifies tenant B survives, then demonstrates a stale-metadata invalidation miss.
All keys it writes are removed at the end.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure.identity import DefaultAzureCredential  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from src.cache import ResultCache  # noqa: E402


class TenantCache(ResultCache):
    @classmethod
    def result_key(cls, request: dict[str, Any], agent_version: str, policy_version: str) -> str:
        signature = {
            "tenant_id": request["tenant_id"],
            "request": request["message"].strip().lower(),
            "segment": request["segment"],
            "context": request["context"],
            "dependencies": sorted(request["dependencies"]),
            "agent_version": agent_version,
            "policy_version": policy_version,
        }
        return f"aw:{request['tenant_id']}:result:{cls._digest(signature)}"

    @classmethod
    def prompt_key(cls, request, tier, input_budget, agent_version, policy_version) -> str:
        signature = {
            "tenant_id": request["tenant_id"],
            "context": request["context"],
            "dependencies": sorted(request["dependencies"]),
            "tier": tier,
            "input_budget": input_budget,
            "agent_version": agent_version,
            "policy_version": policy_version,
        }
        return f"aw:{request['tenant_id']}:prompt:{cls._digest(signature)}"


def main() -> int:
    lab = Path(__file__).resolve().parents[1]
    load_dotenv(lab / ".env")
    config = json.loads((lab / "assets/optimization-config.json").read_text(encoding="utf-8"))
    base = json.loads((lab / "assets/requests.jsonl").read_text(encoding="utf-8").splitlines()[0])
    av, pv = config["agent_version"], config["policy_version"]
    cache = TenantCache(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        principal_id=os.environ["AZURE_PRINCIPAL_ID"],
        credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
        ttl_seconds=300,
    )
    a = {**base, "tenant_id": "SYN-TENANT-A"}
    b = {**base, "tenant_id": "SYN-TENANT-B"}
    created = []
    for req in (a, b):
        rk = cache.result_key(req, av, pv)
        pk = cache.prompt_key(req, 2, 3000, av, pv)
        cache.put(rk, {"response": {"answer": "synthetic"}}, req["dependencies"], {"tier": 2, "quality_score": 100})
        cache.put_prompt(pk, "{}", req["dependencies"])
        created += [rk, pk]
    report: dict[str, Any] = {
        "tenant_a_result_key": cache.result_key(a, av, pv),
        "tenant_b_result_key": cache.result_key(b, av, pv),
        "result_keys_distinct": cache.result_key(a, av, pv) != cache.result_key(b, av, pv),
        "prompt_keys_distinct": cache.prompt_key(a, 2, 3000, av, pv) != cache.prompt_key(b, 2, 3000, av, pv),
    }
    # Failure investigation: stale invalidation metadata (old agent version) -> wrong key, nothing deleted.
    stale = cache.delete_exact(a, "aw-cip-v2", pv)
    report["stale_invalidation"] = {
        **stale,
        "tenant_a_still_cached": cache.get(report["tenant_a_result_key"]) is not None,
        "diagnosis": "key construction: stale agent_version yields a different digest, so scope was never reached",
    }
    targeted = cache.delete_exact(a, av, pv)
    report["targeted_invalidation"] = {
        **targeted,
        "tenant_a_result_present": cache.get(report["tenant_a_result_key"]) is not None,
        "tenant_b_result_present": cache.get(report["tenant_b_result_key"]) is not None,
    }
    report["passed"] = (
        report["result_keys_distinct"]
        and report["prompt_keys_distinct"]
        and stale["deleted"] == 0
        and targeted["deleted"] == 1
        and not report["targeted_invalidation"]["tenant_a_result_present"]
        and report["targeted_invalidation"]["tenant_b_result_present"]
    )
    report["cleanup_deleted"] = int(cache._client.delete(*created))
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
