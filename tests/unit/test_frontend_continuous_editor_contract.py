from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_editor_uses_one_continuous_editing_host() -> None:
    source = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert source.count('class="structured-editor"') == 1
    assert "createEditorKernel" in source
    assert "editor?.setEditable(!lockEditing)" in source
    assert "new Editor({" in kernel
    assert "one-editor-per-page" not in kernel


def test_editor_keeps_visual_lines_inside_semantic_paragraphs() -> None:
    source = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")

    assert "tiptapToDocumentV3" in source
    assert "ReliableBlockIdentity" in kernel
    assert "ReliableClipboard" in kernel
    assert "splitBlock" in commands
    assert "seen.has(currentId)" in kernel
    assert "nodeId: null" in kernel
    assert "transformPasted" in kernel
    assert "transformPastedText" in kernel


def test_page_number_is_calculated_instead_of_hard_coded() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    docir = (FRONTEND / "utils/markdown_docir.ts").read_text(encoding="utf-8")
    blocks = (FRONTEND / "utils/markdown_blocks.ts").read_text(encoding="utf-8")

    assert "paginateDocumentV3(activeDocument" in editor
    assert "pageCount = Math.max(1, layout?.pageCount || 1)" in editor
    assert "第 ${page.pageNumberText} 页，共 ${pageCount} 页" in kernel
    assert '>Page 1</div>' not in docir
    assert '>Page 1</div>' not in blocks
