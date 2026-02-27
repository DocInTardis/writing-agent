from __future__ import annotations

from collections import defaultdict

import writing_agent.web.app_v2 as app_v2


def _path_endpoint_modules():
    mapping: dict[str, set[str]] = defaultdict(set)
    for route in app_v2.app.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        module = getattr(endpoint, "__module__", "") if endpoint else ""
        mapping[path].add(module)
    return mapping


def test_generation_and_export_routes_registered_once_from_flow_modules() -> None:
    modules = _path_endpoint_modules()

    expected = {
        "/api/doc/{doc_id}": "writing_agent.web.api.document_flow",
        "/api/text/{block_id}": "writing_agent.web.api.document_flow",
        "/api/docs/list": "writing_agent.web.api.document_flow",
        "/api/doc/{doc_id}/delete": "writing_agent.web.api.document_flow",
        "/api/doc/{doc_id}/generate/stream": "writing_agent.web.api.generation_flow",
        "/api/doc/{doc_id}/generate": "writing_agent.web.api.generation_flow",
        "/api/doc/{doc_id}/generate/section": "writing_agent.web.api.generation_flow",
        "/api/doc/{doc_id}/revise": "writing_agent.web.api.generation_flow",
        "/api/doc/{doc_id}/save": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/import": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/settings": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/analyze": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/extract_prefs": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/template": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/template/clear": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/upload": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/upload/clarify": "writing_agent.web.api.template_flow",
        "/api/doc/{doc_id}/doc_ir/ops": "writing_agent.web.api.editing_flow",
        "/api/doc/{doc_id}/doc_ir/diff": "writing_agent.web.api.editing_flow",
        "/api/figure/render": "writing_agent.web.api.editing_flow",
        "/api/doc/{doc_id}/diagram/generate": "writing_agent.web.api.editing_flow",
        "/api/doc/{doc_id}/inline-ai": "writing_agent.web.api.editing_flow",
        "/api/doc/{doc_id}/inline-ai/stream": "writing_agent.web.api.editing_flow",
        "/api/doc/{doc_id}/block-edit": "writing_agent.web.api.editing_flow",
        "/api/doc/{doc_id}/block-edit/preview": "writing_agent.web.api.editing_flow",
        "/api/doc/{doc_id}/export/check": "writing_agent.web.api.export_flow",
        "/download/{doc_id}.docx": "writing_agent.web.api.export_flow",
        "/download/{doc_id}.pdf": "writing_agent.web.api.export_flow",
        "/export/{doc_id}/{format}": "writing_agent.web.api.export_flow",
        "/api/doc/{doc_id}/chat": "writing_agent.web.api.feedback_flow",
        "/api/doc/{doc_id}/thoughts": "writing_agent.web.api.feedback_flow",
        "/api/doc/{doc_id}/feedback": "writing_agent.web.api.feedback_flow",
        "/api/feedback/low": "writing_agent.web.api.feedback_flow",
        "/api/doc/{doc_id}/plagiarism/check": "writing_agent.web.api.quality_flow",
        "/api/doc/{doc_id}/ai_rate/check": "writing_agent.web.api.quality_flow",
        "/api/doc/{doc_id}/ai_rate/latest": "writing_agent.web.api.quality_flow",
        "/api/doc/{doc_id}/plagiarism/library_scan": "writing_agent.web.api.quality_flow",
        "/api/doc/{doc_id}/plagiarism/library_scan/latest": "writing_agent.web.api.quality_flow",
        "/api/doc/{doc_id}/plagiarism/library_scan/download": "writing_agent.web.api.quality_flow",
        "/api/doc/{doc_id}/citations": "writing_agent.web.api.citation_flow",
        "/api/doc/{doc_id}/citations/verify": "writing_agent.web.api.citation_flow",
        "/api/metrics/citation_verify": "writing_agent.web.api.citation_flow",
        "/api/metrics/citation_verify/alerts/config": "writing_agent.web.api.citation_flow",
        "/api/metrics/citation_verify/alerts/events": "writing_agent.web.api.citation_flow",
        "/api/metrics/citation_verify/alerts/event/{event_id}": "writing_agent.web.api.citation_flow",
        "/api/metrics/citation_verify/trends": "writing_agent.web.api.citation_flow",
        "/api/doc/{doc_id}/version/commit": "writing_agent.web.api.version_flow",
        "/api/doc/{doc_id}/version/log": "writing_agent.web.api.version_flow",
        "/api/doc/{doc_id}/version/tree": "writing_agent.web.api.version_flow",
        "/api/doc/{doc_id}/version/checkout": "writing_agent.web.api.version_flow",
        "/api/doc/{doc_id}/version/branch": "writing_agent.web.api.version_flow",
        "/api/doc/{doc_id}/version/diff": "writing_agent.web.api.version_flow",
        "/api/doc/{doc_id}/version/tag": "writing_agent.web.api.version_flow",
        "/api/rag/arxiv/ingest": "writing_agent.web.api.rag_flow",
        "/api/rag/papers": "writing_agent.web.api.rag_flow",
        "/api/rag/search": "writing_agent.web.api.rag_flow",
        "/api/rag/retrieve": "writing_agent.web.api.rag_flow",
        "/api/rag/index/rebuild": "writing_agent.web.api.rag_flow",
        "/api/rag/search/chunks": "writing_agent.web.api.rag_flow",
        "/api/rag/paper/{paper_id:path}/pdf": "writing_agent.web.api.rag_flow",
        "/api/rag/ingest": "writing_agent.web.api.rag_flow",
        "/api/rag/stats": "writing_agent.web.api.rag_flow",
        "/api/library/upload": "writing_agent.web.api.rag_flow",
        "/api/library/items": "writing_agent.web.api.rag_flow",
        "/api/library/item/{doc_id}": "writing_agent.web.api.rag_flow",
        "/api/library/item/{doc_id}/approve": "writing_agent.web.api.rag_flow",
        "/api/library/item/{doc_id}/restore": "writing_agent.web.api.rag_flow",
        "/api/library/item/{doc_id}/trash": "writing_agent.web.api.rag_flow",
        "/api/library/item/{doc_id}/update": "writing_agent.web.api.rag_flow",
        "/api/library/from_doc": "writing_agent.web.api.rag_flow",
    }

    for path, module in expected.items():
        assert path in modules, f"missing route: {path}"
        assert modules[path] == {module}, f"route {path} is not owned by {module}: {modules[path]}"
