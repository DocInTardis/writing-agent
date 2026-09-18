from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_structured_editor_is_the_default_editor() -> None:
    entry = (FRONTEND / "components/Editor.svelte").read_text(encoding="utf-8")

    assert "import StructuredEditor" in entry
    assert "<StructuredEditor" in entry
    assert "EditorWorkbench" not in entry


def test_structured_editor_uses_document_v3_and_unified_commands() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "createEditorKernel" in editor
    assert "tiptapToDocumentV3" in editor
    assert "executeDocumentCommand" in editor
    assert "documentV3.set(activeDocument)" in editor
    assert "document.execCommand" not in editor


def test_editor_kernel_repairs_split_block_identity_and_style() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "ReliableBlockIdentity" in kernel
    assert "seen.has(currentId)" in kernel
    assert "attrs.styleId = 'normal'" in kernel
    assert "transaction.setNodeMarkup" in kernel


def test_save_payload_includes_canonical_document_v3() -> None:
    app = (ROOT / "writing_agent/web/frontend_svelte/src/AppWorkbench.svelte").read_text(encoding="utf-8")

    assert "if ($documentV3) payload.document_v3 = $documentV3" in app
