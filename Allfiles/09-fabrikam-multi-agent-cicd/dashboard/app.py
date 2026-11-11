from __future__ import annotations

import html
import json
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from src.responses_client import invoke_responses_endpoint

app = FastAPI(title="Fabrikam release dashboard")


def release_channel(host: str) -> str:
    prefix = host.split(".", 1)[0].lower()
    # Azure serves label routes as <app>---<label>.<environment-domain>.
    if prefix.startswith("stable---") or prefix.endswith("---stable"):
        return "stable"
    if prefix.startswith("candidate---") or prefix.endswith("---candidate"):
        return "candidate"
    return "weighted"


def release_metadata(host: str = "") -> dict[str, str]:
    return {
        "release_set_id": os.environ["RELEASE_SET_ID"],
        "release_channel": release_channel(host),
        "container_app_revision": os.getenv("CONTAINER_APP_REVISION", "assigned-by-platform"),
        "orchestrator_name": os.environ["ORCHESTRATOR_AGENT_NAME"],
        "orchestrator_version": os.environ["ORCHESTRATOR_AGENT_VERSION"],
        "orchestrator_responses_endpoint": os.environ["ORCHESTRATOR_RESPONSES_ENDPOINT"],
    }


def render_page(result: str | None = None, *, host: str = "") -> str:
    metadata = release_metadata(host)
    color = "#0f6cbd" if metadata["release_channel"] == "stable" else "#ca5010"
    rows = "".join(
        f"<tr><th>{html.escape(key.replace('_', ' ').title())}</th><td><code>{html.escape(value)}</code></td></tr>"
        for key, value in metadata.items()
    )
    result_html = f"<h2>Orchestrator response</h2><pre>{html.escape(result)}</pre>" if result else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Fabrikam release dashboard</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
    .channel {{ display: inline-block; color: white; background: {color}; padding: .4rem .8rem; border-radius: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #d1d1d1; padding: .6rem; text-align: left; }}
    th {{ width: 30%; background: #f5f5f5; }}
    input {{ width: 100%; padding: .5rem; margin: .2rem 0 .8rem; box-sizing: border-box; }}
    button {{ padding: .6rem 1rem; }}
    pre {{ white-space: pre-wrap; background: #f5f5f5; padding: 1rem; }}
  </style>
</head>
<body>
  <h1>Fabrikam progressive-release dashboard</h1>
  <p class="channel">{html.escape(metadata["release_channel"].upper())} dashboard revision</p>
  <p>Refresh the weighted application URL to observe 75/25 stable/candidate routing.
     Use the stable and candidate label URLs for deterministic verification.</p>
  <table>{rows}</table>
  <h2>Invoke this revision's immutable orchestrator</h2>
  <form method="post" action="/invoke">
    <label>Repository<input name="repository" value="fabrikam/payments-api"></label>
    <label>Commit<input name="commit" value="0123456789abcdef"></label>
    <label>Change summary<input name="change_summary" value="Validate a payment amount before processing."></label>
    <button type="submit">Request release recommendation</button>
  </form>
  {result_html}
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> str:
    return render_page(host=request.headers.get("x-forwarded-host", request.url.hostname or ""))


@app.get("/metadata")
def metadata(request: Request) -> dict[str, str]:
    return release_metadata(request.headers.get("x-forwarded-host", request.url.hostname or ""))


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    return {
        "status": "healthy",
        **release_metadata(request.headers.get("x-forwarded-host", request.url.hostname or "")),
    }


@app.post("/invoke", response_class=HTMLResponse)
async def invoke(
    request: Request,
    repository: str = Form(...),
    commit: str = Form(...),
    change_summary: str = Form(...),
) -> str:
    prompt = json.dumps(
        {"repository": repository, "commit": commit, "change_summary": change_summary},
        separators=(",", ":"),
    )
    evidence = await invoke_responses_endpoint(
        os.environ["ORCHESTRATOR_RESPONSES_ENDPOINT"],
        os.environ["ORCHESTRATOR_AGENT_NAME"],
        os.environ["ORCHESTRATOR_AGENT_VERSION"],
        prompt,
    )
    host = request.headers.get("x-forwarded-host", request.url.hostname or "")
    return render_page(json.dumps(evidence.to_dict(), indent=2), host=host)


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
