#!/usr/bin/env python3
"""MarsAI MCP Server — exposes MarsAI pipeline as MCP tools for CodeAct.

Runs as a stdio MCP server. CodeAct calls these tools to:
1. Run the full MarsAI pipeline (CEO → departments → deliverable)
2. Check pipeline status
3. List available departments and capabilities

Requires: MARSAI_API_URL environment variable (e.g., http://marsai:8000)
Optional: MARSAI_API_KEY for authenticated access
"""

from __future__ import annotations

import json
import os
import re
import time

import httpx
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MARSAI_API_URL = os.environ.get("MARSAI_API_URL", "http://localhost:8000").rstrip("/")
MARSAI_API_KEY = os.environ.get("MARSAI_API_KEY", "")
MARSAI_ASSISTANT_ID = os.environ.get("MARSAI_ASSISTANT_ID", "marsai-ceo")
PIPELINE_TIMEOUT = int(os.environ.get("MARSAI_PIPELINE_TIMEOUT", "300"))  # 5 min

mcp = FastMCP("marsai-pipeline")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "text/event-stream"}
    if MARSAI_API_KEY:
        h["X-API-Key"] = MARSAI_API_KEY
    return h


def _extract_code_blocks(text: str) -> list[dict[str, str]]:
    """Extract markdown code blocks with optional filename."""
    if not text or not isinstance(text, str):
        return []
    pattern = r'```(\w+)(?:\s+filename="([^"]+)")?\s*\n(.*?)```'
    blocks = re.findall(pattern, text, re.DOTALL)
    if not blocks:
        pattern = r"```(\w+)\s*\n(.*?)```"
        simple = re.findall(pattern, text, re.DOTALL)
        ext_map = {
            "html": "index.html", "css": "styles.css",
            "js": "script.js", "javascript": "script.js",
            "jsx": "src/App.jsx", "tsx": "src/App.tsx",
            "json": "package.json", "python": "main.py",
        }
        blocks = [(lang, ext_map.get(lang, f"output.{lang}"), code) for lang, code in simple]
    return [{"language": lang, "filename": fname, "code": code.strip()} for lang, fname, code in blocks if code.strip()]


def _find_best_deliverable(events: list[dict]) -> str:
    """Find the message with the most code blocks from accumulated events."""
    best = ""
    best_count = 0
    all_content = ""

    for evt in events:
        data = evt.get("data", {})
        if not isinstance(data, dict):
            continue

        # Accumulate token content
        if evt.get("event") == "token" and data.get("content"):
            all_content += str(data["content"])

        # Check message events
        if evt.get("event") == "message" and data.get("role") == "ai":
            content = data.get("content", "") or ""
            if isinstance(content, list):
                content = "\n".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                )
            if not isinstance(content, str):
                content = str(content)
            count = content.count("```")
            if count > best_count:
                best_count = count
                best = content

    # Also check accumulated content
    if all_content.count("```") > best_count:
        best = all_content

    return best


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def marsai_run_pipeline(
    task: str,
    context: str = "",
    priority: str = "medium",
) -> str:
    """Run a task through the MarsAI pipeline.

    The MarsAI pipeline routes your task through a CEO agent who analyzes it,
    assigns it to the right department (CTO for code, CMO for marketing, etc.),
    and returns a professional deliverable.

    Args:
        task: The task description. Be specific about what you want built.
              Include technical requirements, design preferences, and scope.
              Example: "Build a SaaS dashboard with dark theme, analytics charts,
              user authentication, and responsive design using Next.js and Tailwind."
        context: Additional context like architectural decisions, constraints,
                 or reference materials. Optional but improves output quality.
        priority: Task priority — "low", "medium", or "high".

    Returns:
        JSON string with pipeline result including deliverable content,
        department that handled it, quality score, and any code files.
    """
    # Create thread
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{MARSAI_API_URL}/api/v1/threads",
            json={},
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()
        thread_id = data.get("thread_id") or data.get("id")

    # Build task with context
    full_task = task
    if context:
        full_task += f"\n\nAdditional context:\n{context}"

    # Start streaming run
    payload = {
        "assistant_id": MARSAI_ASSISTANT_ID,
        "thread_id": thread_id,
        "task": full_task,
        "input": {
            "messages": [{"type": "human", "content": full_task}],
        },
        "stream_mode": ["updates", "messages"],
        "stream_subgraphs": True,
        "runtime_overrides": {
            "auto_approve": True,
            "priority": priority,
        },
    }

    events: list[dict] = []
    last_node = ""
    department = ""
    status = "running"
    error_msg = ""

    start_time = time.time()

    try:
        async with (
            httpx.AsyncClient(timeout=float(PIPELINE_TIMEOUT)) as stream_client,
            stream_client.stream(
                "POST",
                f"{MARSAI_API_URL}/api/v1/runs/stream",
                json=payload,
                headers=_headers(),
            ) as response,
        ):
            if response.status_code >= 400:
                body = await response.aread()
                return json.dumps({
                    "status": "error",
                    "error": f"Pipeline API error {response.status_code}: {body.decode('utf-8', errors='replace')[:500]}",
                })

            buffer = b""
            event_name: str | None = None

            async for chunk in response.aiter_bytes():
                # Timeout check
                if time.time() - start_time > PIPELINE_TIMEOUT:
                    status = "timeout"
                    error_msg = f"Pipeline timed out after {PIPELINE_TIMEOUT}s"
                    break

                buffer += chunk
                while b"\n\n" in buffer:
                    part, _, buffer = buffer.partition(b"\n\n")
                    for line in part.split(b"\n"):
                        raw = line
                        if raw.startswith(b"data: "):
                            raw = raw[6:]

                        if raw.startswith(b"event:"):
                            event_name = raw[6:].strip().decode("utf-8")
                        elif raw.startswith(b"data:") or raw.startswith(b"{"):
                            data_bytes = raw[5:] if raw.startswith(b"data:") else raw
                            try:
                                data = json.loads(data_bytes.decode("utf-8"))
                                evt = {"event": event_name or "message", "data": data}
                                events.append(evt)

                                # Track progress
                                if isinstance(data, dict):
                                    node = data.get("node", "") or data.get("name", "")
                                    if node:
                                        last_node = node
                                    routing = data.get("routing_decision")
                                    if isinstance(routing, dict) and routing.get("target_department"):
                                        department = routing["target_department"]

                                    # Detect completion/error
                                    if event_name == "error":
                                        status = "error"
                                        error_msg = data.get("message", "") or data.get("content", "Unknown error")
                                    elif event_name == "done":
                                        done_status = data.get("status", "completed")
                                        status = done_status
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pass
                        event_name = None
    except httpx.TimeoutException:
        status = "timeout"
        error_msg = f"Pipeline timed out after {PIPELINE_TIMEOUT}s"
    except Exception as e:
        status = "error"
        error_msg = str(e)

    elapsed = round(time.time() - start_time, 1)

    # Extract deliverable
    deliverable = ""

    # Try getting final state
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{MARSAI_API_URL}/api/v1/threads/{thread_id}/state",
                headers=_headers(),
            )
            if r.status_code < 300:
                state = r.json()
                vals = state.get("values", state)

                # Priority: final_deliverable > department_results > messages
                deliverable = vals.get("final_deliverable", "")

                if not deliverable:
                    for dr in reversed(vals.get("department_results", [])):
                        if isinstance(dr, dict):
                            d = dr.get("deliverable", "") or dr.get("output", "")
                            if d and len(d) > 50:
                                deliverable = d
                                break

                if not deliverable:
                    # Search messages for code blocks
                    messages = vals.get("messages", [])
                    best_count = 0
                    for msg in reversed(messages):
                        content = ""
                        if isinstance(msg, dict):
                            content = msg.get("content", "")
                        elif hasattr(msg, "content"):
                            content = msg.content
                        if isinstance(content, list):
                            content = "\n".join(
                                p.get("text", "") if isinstance(p, dict) else str(p)
                                for p in content
                            )
                        if not content:
                            continue
                        count = content.count("```")
                        if count > best_count:
                            best_count = count
                            deliverable = content
    except Exception:
        pass

    # Fallback to stream events
    if not deliverable:
        deliverable = _find_best_deliverable(events)

    # Extract code files from deliverable
    code_files = _extract_code_blocks(deliverable) if deliverable else []

    # Determine quality score from events
    quality_score = 0.0
    for evt in reversed(events):
        data = evt.get("data", {})
        if isinstance(data, dict):
            qs = data.get("quality_score")
            if isinstance(qs, (int, float)) and qs > 0:
                quality_score = float(qs)
                break

    result = {
        "status": status if status != "running" else "completed",
        "thread_id": thread_id,
        "department": department,
        "last_node": last_node,
        "quality_score": quality_score,
        "elapsed_seconds": elapsed,
        "deliverable": deliverable,
        "code_files": code_files,
        "code_file_count": len(code_files),
    }

    if error_msg:
        result["error"] = error_msg

    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def marsai_get_status(thread_id: str) -> str:
    """Check the status of a MarsAI pipeline run.

    Args:
        thread_id: The thread ID returned by marsai_run_pipeline.

    Returns:
        JSON string with current pipeline status, department, and routing info.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{MARSAI_API_URL}/api/v1/threads/{thread_id}/state",
                headers=_headers(),
            )
            r.raise_for_status()
            state = r.json()
            vals = state.get("values", state)

            routing = vals.get("routing_decision") or {}
            results = vals.get("department_results", [])
            latest = results[-1] if results else {}

            return json.dumps({
                "status": latest.get("status", "in_progress") if latest else "in_progress",
                "department": routing.get("target_department", ""),
                "priority": routing.get("priority", "medium"),
                "quality_score": latest.get("quality_score", 0.0) if isinstance(latest, dict) else 0.0,
                "has_deliverable": bool(vals.get("final_deliverable")),
                "requires_approval": bool(vals.get("requires_human_approval")),
            }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


@mcp.tool()
async def marsai_list_departments() -> str:
    """List all MarsAI departments and their capabilities.

    Returns:
        JSON string with department information including code, name,
        and what each department can produce.
    """
    departments = [
        {
            "code": "cto",
            "name": "Engineering (CTO)",
            "head": "CTO Agent",
            "capabilities": [
                "Web & full-stack development (Next.js, React, Node.js, Python)",
                "Mobile apps (iOS, Android, Flutter)",
                "Blockchain & smart contracts",
                "Cloud architecture & DevOps",
                "Code review & QA testing",
            ],
            "teams": ["web", "mobile", "blockchain", "cloud"],
            "produces": "Working code, APIs, applications, technical documentation",
        },
        {
            "code": "cmo",
            "name": "Marketing (CMO)",
            "head": "CMO Agent",
            "capabilities": [
                "Social media strategy & content",
                "SEO optimization",
                "PPC campaign management",
                "Brand positioning",
                "Community management",
            ],
            "teams": ["social", "seo"],
            "produces": "Marketing strategies, content plans, SEO reports, campaign specs",
        },
        {
            "code": "coo",
            "name": "Operations (COO)",
            "head": "COO Agent",
            "capabilities": [
                "UI/UX design",
                "Creative direction & visual assets",
                "Project management",
                "Customer success",
            ],
            "teams": ["studio", "operations"],
            "produces": "Design specs, wireframes, project plans, visual assets",
        },
        {
            "code": "cpo",
            "name": "Product (CPO)",
            "head": "CPO Agent",
            "capabilities": [
                "Product strategy & roadmap",
                "User story creation",
                "Business analysis",
                "Feature prioritization",
            ],
            "teams": [],
            "produces": "Product specs, user stories, roadmaps, feature briefs",
        },
        {
            "code": "cro",
            "name": "Revenue (CRO)",
            "head": "CRO Agent",
            "capabilities": [
                "Sales proposals & pricing",
                "Business development",
                "Partnership management",
                "Growth analysis",
            ],
            "teams": ["sales", "bizdev"],
            "produces": "Sales proposals, pricing models, partnership plans",
        },
        {
            "code": "cfo",
            "name": "Finance (CFO)",
            "head": "CFO Agent",
            "capabilities": [
                "Cost analysis & budgeting",
                "FinOps monitoring",
                "Financial reporting",
            ],
            "teams": [],
            "produces": "Budget reports, cost analysis, financial plans",
        },
        {
            "code": "clo",
            "name": "Legal (CLO)",
            "head": "CLO Agent",
            "capabilities": [
                "Contract review",
                "KVKK/GDPR compliance",
                "IP protection",
            ],
            "teams": [],
            "produces": "Legal reviews, compliance reports, contract templates",
        },
        {
            "code": "chro",
            "name": "Agent HR (CHRO)",
            "head": "CHRO Agent",
            "capabilities": [
                "Agent performance optimization",
                "Prompt engineering",
                "Agent operations",
            ],
            "teams": [],
            "produces": "Performance reports, prompt improvements, agent configs",
        },
        {
            "code": "cdo",
            "name": "Data & Analytics (CDO)",
            "head": "CDO Agent",
            "capabilities": [
                "Data analysis & insights",
                "BI dashboard creation",
                "Reporting automation",
            ],
            "teams": [],
            "produces": "Data reports, analytics dashboards, insights",
        },
        {
            "code": "dpo",
            "name": "Data Protection (DPO)",
            "head": "DPO Agent",
            "capabilities": [
                "Privacy impact assessments",
                "Data protection audits",
                "Compliance monitoring",
            ],
            "teams": [],
            "produces": "DPIA reports, compliance audits, privacy recommendations",
        },
    ]

    return json.dumps({"departments": departments, "total": len(departments)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
