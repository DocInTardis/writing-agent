"""Diagram Agent module.

This module belongs to `writing_agent.agents` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from writing_agent.diagrams.spec import (
    DiagramSpec,
    ErEntity,
    ErRelation,
    ErSpec,
    FlowEdge,
    FlowNode,
    FlowchartSpec,
)
from writing_agent.llm import OllamaClient, get_ollama_settings


def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _extract_json_dict(raw: object) -> dict | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        payload = json.loads(m.group(0))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


@dataclass(frozen=True)
class DiagramRequest:
    type: str  # "flowchart"|"er"
    instruction: str


class DiagramAgent:
    def generate(self, req: DiagramRequest) -> DiagramSpec:
        settings = get_ollama_settings()
        client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
        if not settings.enabled or not client.is_running():
            return self._fallback(req)

        req_type = str(req.type or "").strip().lower()
        req_type = "er" if req_type == "er" else "flowchart"
        escaped_instruction = _escape_prompt_text(req.instruction)

        system = (
            "You are a constrained diagram spec generator.\n"
            "Return strict JSON only (no markdown fences, no explanations).\n"
            "Schema:\n"
            '{"type":"flowchart|er","title":"...","caption":"...",'
            '"flowchart":{"nodes":[{"id":"...","text":"..."}],"edges":[{"src":"...","dst":"...","label":"..."}]},'
            '"er":{"entities":[{"name":"...","attributes":["..."]}],"relations":[{"left":"...","right":"...","label":"...","cardinality":"..."}]}}\n'
            "Rules:\n"
            "1) Keep output compact and valid JSON.\n"
            "2) flowchart: 2-8 nodes, 1-16 edges.\n"
            "3) er: 2-6 entities, 1-16 relations.\n"
            "4) Use placeholders only when required input is missing.\n"
        )
        user = (
            "<task>diagram_spec_generation</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Return strict JSON only.\n"
            "- Keep keys limited to: type, title, caption, flowchart, er.\n"
            "</constraints>\n"
            f"<requested_type>{req_type}</requested_type>\n"
            f"<user_request>\n{escaped_instruction}\n</user_request>\n"
            "Return strict JSON now."
        )

        for attempt in range(2):
            attempt_user = user
            if attempt > 0:
                attempt_user = (
                    f"{user}\n"
                    "<retry_reason>\n"
                    "Previous output was invalid JSON. Return strict JSON only.\n"
                    "</retry_reason>\n"
                )
            try:
                raw = client.chat(system=system, user=attempt_user, temperature=0.2)
            except Exception:
                continue
            payload = _extract_json_dict(raw)
            if isinstance(payload, dict):
                return self._from_json(payload)
        return self._fallback(req)

    def _fallback(self, req: DiagramRequest) -> DiagramSpec:
        if req.type == "er":
            entities = [
                ErEntity(name="User", attributes=["id(PK)", "name", "email"]),
                ErEntity(name="Order", attributes=["id(PK)", "user_id(FK)", "total", "created_at"]),
            ]
            relations = [ErRelation(left="User", right="Order", label="places", cardinality="1..N")]
            return DiagramSpec(type="er", title="ER Diagram", caption="ER diagram (fallback)", er=ErSpec(entities=entities, relations=relations))

        nodes = [
            FlowNode(id="start", text="Start"),
            FlowNode(id="input", text="Collect requirements"),
            FlowNode(id="plan", text="Generate or revise content"),
            FlowNode(id="review", text="Review and confirm"),
            FlowNode(id="export", text="Export document"),
        ]
        edges = [
            FlowEdge(src="start", dst="input"),
            FlowEdge(src="input", dst="plan"),
            FlowEdge(src="plan", dst="review"),
            FlowEdge(src="review", dst="export"),
        ]
        return DiagramSpec(type="flowchart", title="Flowchart", caption="Flowchart (fallback)", flowchart=FlowchartSpec(nodes=nodes, edges=edges))

    def _from_json(self, data: dict) -> DiagramSpec:
        t = str(data.get("type") or "").strip().lower()
        if t == "flow":
            t = "flowchart"
        if t not in {"flowchart", "er"}:
            t = "flowchart"

        title = str(data.get("title") or "").strip() or ("ER Diagram" if t == "er" else "Flowchart")
        caption = str(data.get("caption") or "").strip() or title

        if t == "er":
            er = data.get("er") if isinstance(data.get("er"), dict) else {}
            entities: list[ErEntity] = []
            for e in (er.get("entities") or [])[:8]:
                if not isinstance(e, dict):
                    continue
                name = str(e.get("name") or "").strip()
                if not name:
                    continue
                attrs = [str(a).strip() for a in (e.get("attributes") or [])[:12] if str(a).strip()]
                entities.append(ErEntity(name=name, attributes=attrs))
            relations: list[ErRelation] = []
            for r in (er.get("relations") or [])[:16]:
                if not isinstance(r, dict):
                    continue
                left = str(r.get("left") or "").strip()
                right = str(r.get("right") or "").strip()
                if not left or not right:
                    continue
                relations.append(
                    ErRelation(
                        left=left,
                        right=right,
                        label=str(r.get("label") or "").strip(),
                        cardinality=str(r.get("cardinality") or "").strip(),
                    )
                )
            if len(entities) < 2:
                return self._fallback(DiagramRequest(type="er", instruction=""))
            if not relations:
                relations.append(ErRelation(left=entities[0].name, right=entities[1].name, label="rel", cardinality=""))
            return DiagramSpec(type="er", title=title, caption=caption, er=ErSpec(entities=entities, relations=relations))

        fc = data.get("flowchart") if isinstance(data.get("flowchart"), dict) else {}
        nodes: list[FlowNode] = []
        for n in (fc.get("nodes") or [])[:12]:
            if not isinstance(n, dict):
                continue
            nid = str(n.get("id") or "").strip()
            text = str(n.get("text") or "").strip()
            if not nid or not text:
                continue
            nodes.append(FlowNode(id=nid, text=text))
        edges: list[FlowEdge] = []
        for e in (fc.get("edges") or [])[:24]:
            if not isinstance(e, dict):
                continue
            src = str(e.get("src") or "").strip()
            dst = str(e.get("dst") or "").strip()
            if not src or not dst:
                continue
            edges.append(FlowEdge(src=src, dst=dst, label=str(e.get("label") or "").strip()))
        if len(nodes) < 2:
            return self._fallback(DiagramRequest(type="flowchart", instruction=""))
        if not edges:
            for idx in range(len(nodes) - 1):
                edges.append(FlowEdge(src=nodes[idx].id, dst=nodes[idx + 1].id))
        return DiagramSpec(type="flowchart", title=title, caption=caption, flowchart=FlowchartSpec(nodes=nodes, edges=edges))

