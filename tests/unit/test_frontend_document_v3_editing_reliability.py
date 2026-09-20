from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_paste_is_normalized_before_entering_document_v3() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "ReliableClipboard" in kernel
    assert "transformPasted(slice, view)" in kernel
    assert "nodeId: null" in kernel
    assert "if (node.isText) return node" in kernel
    assert "transformPastedText(text)" in kernel
    assert "ReliableClipboard," in kernel


def test_soft_break_is_preserved_in_semantic_text() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "node.type === 'hardBreak'" in kernel
    assert "return '\\n'" in kernel


def test_selection_reports_every_touched_text_block() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "export function selectedBlocks" in kernel
    assert "editor.state.doc.forEach((node, position)" in kernel
    assert "const blocks = selectedBlocks(editor)" in editor
    assert "blockIds," in editor


def test_focus_changes_refresh_toolbar_and_selection_state() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "onFocus:" in kernel
    assert "onBlur:" in kernel


def test_toolbar_clipboard_commands_use_the_structured_editor() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "plainTextToTiptapContent" in kernel
    assert "runClipboardCommand" in editor
    assert "navigator.clipboard.writeText" in editor
    assert "navigator.clipboard.readText" in editor
    assert "deleteSelection" in editor
    assert "document.execCommand" not in editor


def test_block_handle_selects_document_nodes_without_creating_editors() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "export function selectBlock" in kernel
    assert "NodeSelection.create" in kernel
    assert "TextSelection.create" in kernel
    assert 'aria-label="选择当前块"' in editor
    assert "handleBlockHandleClick" in editor
    assert "ProseMirror-selectednode" in editor


def test_block_actions_are_transaction_commands() -> None:
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    for command in ("duplicate_block", "delete_block", "move_block_up", "move_block_down"):
        assert f"registerDocumentCommand('{command}'" in commands
    assert "editor.state.tr" in commands
    assert 'aria-label="块操作"' in editor
    assert "runBlockCommand" in editor
