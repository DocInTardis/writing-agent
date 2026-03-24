import io
import os
import re
import zipfile

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _create_session(client: TestClient) -> str:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    location = resp.headers.get("location") or ""
    assert location.startswith("/workbench/")
    return location.split("/workbench/")[-1]


def test_docx_picture_paragraph_overrides_exact_line_spacing() -> None:
    client = TestClient(app_v2.app)
    doc_id = _create_session(client)
    text = "\n".join([
        "# Sample",
        "",
        "## Results",
        "",
        '[[FIGURE:{"type":"flow","caption":"Flow Chart","data":{"nodes":[{"id":"n1","label":"Start"},{"id":"n2","label":"Review"},{"id":"n3","label":"Done"}],"edges":[{"from":"n1","to":"n2","label":"ok"},{"from":"n2","to":"n3","label":"ship"}]}}]]',
    ])
    payload = {
        "text": text,
        "generation_prefs": {
            "include_cover": False,
            "include_toc": False,
            "include_header": False,
            "page_numbers": False,
            "export_gate_policy": "off",
            "strict_doc_format": False,
            "strict_citation_verify": False,
        },
    }
    env_backup = os.environ.copy()
    os.environ["WRITING_AGENT_EXPORT_MIN_FIGURES"] = "0"
    os.environ["WRITING_AGENT_EXPORT_MIN_TABLES"] = "0"
    try:
        resp = client.post(f"/api/doc/{doc_id}/save", json=payload)
        assert resp.status_code == 200
        dl = client.get(f"/download/{doc_id}.docx")
        assert dl.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl.content), "r") as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    finally:
        os.environ.clear()
        os.environ.update(env_backup)
    match = re.search(r'(<w:p[^>]*>.*?<w:drawing>.*?</w:drawing>.*?</w:p>)', xml)
    assert match is not None
    para_xml = match.group(1)
    assert 'w:lineRule="exact"' not in para_xml
    assert 'w:firstLine="0"' in para_xml
    assert 'w:lineRule="auto"' in para_xml
