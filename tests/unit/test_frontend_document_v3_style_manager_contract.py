from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_style_manager_edits_document_v3_definitions_not_dom_css() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert 'aria-label="文档样式管理"' in editor
    assert "const next = structuredClone(activeDocument)" in editor
    assert "next.styles.findIndex" in editor
    assert "styleSheetForDocument(next)" in editor
    assert "documentV3.set(next)" in editor
    assert "docIrDirty.set(true)" in editor
    assert "document.execCommand" not in editor


def test_style_manager_supports_inheritance_next_style_and_global_update() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "managedBasedOn" in editor
    assert "managedNextStyle" in editor
    assert "样式不能继承自身" in editor
    assert "样式继承关系不能形成循环" in editor
    assert "保存并全局更新" in editor
    assert "split_with_next_style" in kernel
    assert "registerDocumentCommand('split_block_with_style'" in commands
    assert "nextStyleId === currentStyleId" in editor


def test_toolbar_lists_document_styles_and_applies_them_through_registry() -> None:
    toolbar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")

    assert "editorToolbarState.styles" in toolbar
    assert "command('style-manager')" in toolbar
    assert "command.startsWith('style:')" in editor
    assert "createUserCommand(type, params)" in editor
    assert "registerDocumentCommand('apply_style'" in commands


def test_text_block_and_page_contexts_are_mutually_exclusive() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    page_setup = (FRONTEND / "workbench/PageSetupPanel.svelte").read_text(encoding="utf-8")

    assert "wa-editor-context" in editor
    assert "contextKind" in editor
    assert "kind !== 'page'" in editor
    assert "selectionToolbarVisible = false" in editor
    assert "blockSelectionActive = false" in editor
    assert "kind: 'page'" in page_setup
    assert "kind !== 'page'" in page_setup
    assert "removeEventListener('wa-editor-context'" in page_setup
