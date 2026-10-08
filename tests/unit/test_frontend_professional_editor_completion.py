from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_review_comments_and_revisions_use_document_v3() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    revisions = (FRONTEND / "editor-v3/revisions.ts").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    assert "addDocumentComment" in editor
    assert "settleRevision" in editor
    assert "AI 修改建议" in editor
    assert "buildRevision" in revisions
    assert "wa-ai-command-proposal" in commands


def test_academic_objects_remain_editable_structures() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    for node in ("EndnoteReferenceNode", "CitationReferenceNode", "BibliographyNode"):
        assert node in kernel
    for command in ("insert_endnote_reference", "insert_citation", "update_bibliography", "update_equation"):
        assert f"registerDocumentCommand('{command}'" in commands
    assert "figureSourceSpec" in editor
    assert "regenerateFigureFromInstruction" in editor
    assert "修改 JSON" not in editor
    assert "editableSource" in editor


def test_page_regions_and_multisection_layout_are_editable() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    engine = (FRONTEND / "engine/documentEngine.ts").read_text(encoding="utf-8")
    panel = (FRONTEND / "workbench/PageSetupPanel.svelte").read_text(encoding="utf-8")
    assert "wa-edit-page-region" in kernel
    assert "activeSectionId" in panel
    assert "firstPageHeaderText" in panel and "evenPageFooterText" in panel
    assert "for (const section of document.sections)" in engine
    assert "needsParityPage" in engine
    assert "keepLinesTogether" in engine and "keepWithNext" in engine


def test_rust_layout_baseline_covers_long_documents() -> None:
    source = (ROOT / "engine/engine/src/bin/layout_baseline.rs").read_text(encoding="utf-8")
    assert "[20usize, 100, 300]" in source
    assert "incrementalMs" in source


def test_editor_combines_word_navigation_pageless_view_and_selection_scoped_ai() -> None:
    app = (FRONTEND.parent / "AppWorkbench.svelte").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    ribbon = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")

    assert "wa_editor_view_mode" in app
    assert "页面视图" in ribbon and "连续视图" in ribbon
    assert "navigationSearchResults" in editor
    assert "标题 {outlineHeadings().length}" in editor
    assert "ontextai" in editor
    assert "只修改当前选中的文字" in app
    assert "wa_focus_writing_mode" in app and "wa_typewriter_mode" in app
    assert "专注当前段" in ribbon and "打字机滚动" in ribbon
    assert "wa-focus-active" in editor
    assert "data-focus-active" in kernel and "FocusBlockDecoration" in kernel
    assert "keepCaretInWritingPosition" in editor
