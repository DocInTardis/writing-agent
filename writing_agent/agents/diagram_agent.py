from __future__ import annotations

import json
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
from writing_agent.llm import OllamaClient, OllamaError, get_ollama_settings


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

        system = (
            "你是一个图表生成助手。你需要把用户描述转换为结构化 JSON。"
            "只输出 JSON，不要解释，不要代码块。\n"
            "当 type=flowchart 时输出："
            "{type,title,caption,flowchart:{nodes:[{id,text}],edges:[{src,dst,label}]}}\n"
            "当 type=er 时输出："
            "{type,title,caption,er:{entities:[{name,attributes:[...] }],relations:[{left,right,label,cardinality}]}}\n"
            "约束：nodes 2-8 个；entities 2-6 个；字段尽量短；缺失信息用 [待补充]。"
        )
        user = f"type={req.type}\n用户描述：{req.instruction}\n"
        try:
            raw = client.chat(system=system, user=user, temperature=0.2).strip()
            data = json.loads(raw)
            return self._from_json(data)
        except Exception:
            return self._fallback(req)

    def _fallback(self, req: DiagramRequest) -> DiagramSpec:
        if req.type == "er":
            entities = [
                ErEntity(name="User", attributes=["id(PK)", "name", "email"]),
                ErEntity(name="Order", attributes=["id(PK)", "user_id(FK)", "total", "created_at"]),
            ]
            relations = [ErRelation(left="User", right="Order", label="places", cardinality="1..N")]
            return DiagramSpec(type="er", title="ER Diagram", caption="ER图（示例，占位）", er=ErSpec(entities=entities, relations=relations))

        nodes = [
            FlowNode(id="start", text="开始"),
            FlowNode(id="input", text="接收用户需求"),
            FlowNode(id="plan", text="生成/更新文档内容"),
            FlowNode(id="review", text="用户编辑与确认"),
            FlowNode(id="export", text="导出 docx"),
        ]
        edges = [
            FlowEdge(src="start", dst="input"),
            FlowEdge(src="input", dst="plan"),
            FlowEdge(src="plan", dst="review"),
            FlowEdge(src="review", dst="export"),
        ]
        return DiagramSpec(type="flowchart", title="Flowchart", caption="流程图（示例，占位）", flowchart=FlowchartSpec(nodes=nodes, edges=edges))

    def _from_json(self, data: dict) -> DiagramSpec:
        t = str(data.get("type") or "").strip() or "flowchart"
        title = str(data.get("title") or "").strip() or ("ER Diagram" if t == "er" else "Flowchart")
        caption = str(data.get("caption") or "").strip() or title

        if t == "er":
            er = data.get("er") or {}
            entities = []
            for e in (er.get("entities") or [])[:8]:
                name = str(e.get("name") or "").strip()
                if not name:
                    continue
                attrs = [str(a) for a in (e.get("attributes") or [])[:12]]
                entities.append(ErEntity(name=name, attributes=attrs))
            relations = []
            for r in (er.get("relations") or [])[:12]:
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
            return DiagramSpec(type="er", title=title, caption=caption, er=ErSpec(entities=entities, relations=relations))

        fc = data.get("flowchart") or {}
        nodes = []
        for n in (fc.get("nodes") or [])[:12]:
            nid = str(n.get("id") or "").strip()
            text = str(n.get("text") or "").strip()
            if not nid or not text:
                continue
            nodes.append(FlowNode(id=nid, text=text))
        edges = []
        for e in (fc.get("edges") or [])[:24]:
            src = str(e.get("src") or "").strip()
            dst = str(e.get("dst") or "").strip()
            if not src or not dst:
                continue
            edges.append(FlowEdge(src=src, dst=dst, label=str(e.get("label") or "").strip()))
        return DiagramSpec(type="flowchart", title=title, caption=caption, flowchart=FlowchartSpec(nodes=nodes, edges=edges))

