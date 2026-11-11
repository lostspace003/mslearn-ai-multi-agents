"""Passwordless Redis prompt and result caches with versioned metadata."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis
from azure.core.credentials import TokenCredential


class ResultCache:
    def __init__(
        self,
        host: str,
        port: int,
        principal_id: str,
        credential: TokenCredential,
        ttl_seconds: int,
    ) -> None:
        token = credential.get_token("https://redis.azure.com/.default").token
        self._client = redis.Redis(
            host=host,
            port=port,
            ssl=True,
            username=principal_id,
            password=token,
            decode_responses=True,
        )
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _digest(signature: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()

    @classmethod
    def result_key(cls, request: dict[str, Any], agent_version: str, policy_version: str) -> str:
        signature = {
            "request": request["message"].strip().lower(),
            "segment": request["segment"],
            "context": request["context"],
            "dependencies": sorted(request["dependencies"]),
            "agent_version": agent_version,
            "policy_version": policy_version,
        }
        return f"aw:result:{cls._digest(signature)}"

    @classmethod
    def prompt_key(
        cls,
        request: dict[str, Any],
        tier: int,
        input_budget: int,
        agent_version: str,
        policy_version: str,
    ) -> str:
        signature = {
            "context": request["context"],
            "dependencies": sorted(request["dependencies"]),
            "tier": tier,
            "input_budget": input_budget,
            "agent_version": agent_version,
            "policy_version": policy_version,
        }
        return f"aw:prompt:{cls._digest(signature)}"

    def get(self, key: str) -> dict[str, Any] | None:
        value = self._client.get(key)
        return json.loads(value) if value else None

    def put(
        self,
        key: str,
        response: dict[str, Any],
        dependencies: list[str],
        metadata: dict[str, Any],
    ) -> None:
        value = {"response": response, "dependencies": dependencies, "metadata": metadata}
        self._client.setex(key, self._ttl_seconds, json.dumps(value))

    def get_prompt(self, key: str) -> str | None:
        value = self.get(key)
        return value["context"] if value else None

    def put_prompt(self, key: str, context: str, dependencies: list[str]) -> None:
        value = {"context": context, "dependencies": dependencies}
        self._client.setex(key, self._ttl_seconds, json.dumps(value))

    def delete_exact(
        self,
        request: dict[str, Any],
        agent_version: str,
        policy_version: str,
    ) -> dict[str, Any]:
        key = self.result_key(request, agent_version, policy_version)
        return {"exact_result_key": key, "deleted": int(self._client.delete(key))}