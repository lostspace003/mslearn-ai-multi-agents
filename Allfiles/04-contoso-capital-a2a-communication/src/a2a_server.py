"""Minimal A2A agent-card and JSON-RPC service backed by Foundry Agents v2."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
app=FastAPI(title="Contoso A2A risk agent")
CARD={"name":"contoso-risk-agent","description":"Synthetic portfolio risk analysis","url":f"{os.getenv('A2A_BASE_URL','http://127.0.0.1:8000')}/a2a","version":"1.0.0","skills":[{"id":"risk-analysis","name":"risk-analysis","description":"Analyze synthetic risk scenarios","tags":["risk","synthetic"]}]}
@app.get("/")
def status()->dict[str,str]: return {"status":"ready","agent_card":"/.well-known/agent-card.json","message_endpoint":"/a2a"}
@app.get("/.well-known/agent-card.json")
def agent_card()->dict[str,Any]: return CARD
def extract_text(response:Any)->str:return "\n".join(getattr(p,"text","") for i in response.output if getattr(i,"type",None)=="message" for p in getattr(i,"content",[])).strip()
def handle_message(payload:dict[str,Any])->dict[str,Any]:
    """Learner task: validate JSON-RPC/tenant, call Foundry, return result."""
    # LAB PLACEHOLDER 5: Replace this line with the Task 5 sample.
    if payload.get("jsonrpc") != "2.0" or payload.get("method") != "message/send":
        raise ValueError("Expected JSON-RPC 2.0 method message/send")
    if "id" not in payload:
        raise ValueError("JSON-RPC request id is required")

    params = payload.get("params", {})
    tenant_id = params.get("tenantId")
    trusted_tenant = os.getenv("A2A_TENANT_ID", "contoso")
    if tenant_id != trusted_tenant:
        raise ValueError("Tenant is unavailable")

    parts = params.get("message", {}).get("parts", [])
    text = "\n".join(
        str(part.get("text", ""))
        for part in parts
        if part.get("kind") == "text" and part.get("text")
    ).strip()
    if not text:
        raise ValueError("At least one text message part is required")

    project = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )
    agent = project.agents.create_version(
        agent_name=CARD["name"],
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_MODEL_NAME"],
            instructions=(
                "Analyze only synthetic portfolio risk. State assumptions, "
                "identify missing evidence, and do not provide investment advice."
            ),
        ),
    )
    openai = project.get_openai_client(agent_name=agent.name)
    response = openai.responses.create(
        input=text,
    )
    return {
        "jsonrpc": "2.0",
        "id": payload["id"],
        "result": {
            "tenantId": tenant_id,
            "response_id": response.id,
            "text": extract_text(response),
        },
    }
@app.post("/a2a")
def a2a(payload:dict[str,Any])->dict[str,Any]:
    try:return handle_message(payload)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc