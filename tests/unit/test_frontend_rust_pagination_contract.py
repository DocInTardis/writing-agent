from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_document_v3_is_converted_to_versioned_rust_layout_protocol() -> None:
    engine = (FRONTEND / "engine/documentEngine.ts").read_text(encoding="utf-8")
    bridge = (ROOT / "engine/bridge/src/lib.rs").read_text(encoding="utf-8")

    assert "documentV3LayoutInput" in engine
    assert "stableUuid" in engine
    assert "forcePageBreakBefore" in engine
    assert "sourceIds" in engine and "sectionIds" in engine
    assert "layoutProtocol" in engine
    for field in ("protocolVersion", "layoutVersion", "pageCount", "blockPage"):
        assert f'"{field}"' in bridge
    for field in ("startOffset", "endOffset", "overflow", "sectionId"):
        assert f'"{field}"' in bridge


def test_single_prosemirror_document_uses_pagination_decorations() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "RustPagination" in kernel
    assert "DecorationSet.create" in kernel
    assert "applyPaginationLayout" in kernel
    assert "paginateDocumentV3(activeDocument" in editor
    assert "wa-page-boundary" in editor
    assert "data-pagination-state" in editor
    assert "one-editor-per-page" not in kernel


def test_page_setup_writes_section_layout_and_header_footer_model() -> None:
    panel = (FRONTEND / "workbench/PageSetupPanel.svelte").read_text(encoding="utf-8")

    assert "documentV3.update" in panel
    assert "section.layout =" in panel
    assert "headerFooter.pageNumber" in panel
    for option in ("首页不同", "奇偶页不同", "页眉链接前一节", "页脚链接前一节", "起始页码"):
        assert option in panel


def test_full_document_load_invalidates_stale_rust_layout_cache() -> None:
    bridge = (ROOT / "engine/bridge/src/lib.rs").read_text(encoding="utf-8")
    load_json = bridge.split("pub fn load_json", 1)[1].split("pub fn export_json", 1)[0]

    assert "self.layout_cache = LayoutCache::new()" in load_json
