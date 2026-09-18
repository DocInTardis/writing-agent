from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_editor_uses_one_continuous_editing_host() -> None:
    source = (FRONTEND / "components/EditorWorkbench.svelte").read_text(encoding="utf-8")

    assert 'class="editable"' in source
    assert 'contenteditable="true"' in source
    assert "if (editable) el.removeAttribute('contenteditable')" in source
    assert "editor.setAttribute('contenteditable', readonly ? 'false' : 'true')" in source


def test_editor_keeps_visual_lines_inside_semantic_paragraphs() -> None:
    source = (FRONTEND / "components/EditorWorkbench.svelte").read_text(encoding="utf-8")

    assert "splitTextBlockAtCaret" in source
    assert "type: 'paragraph'" in source
    assert "mountParagraphBeside" in source
    assert "hasUntrackedParagraphStructure" in source
    assert "seenBlockIds.has(blockId)" in source
    assert "insertFromPaste" in source
    assert "Always serialize the latest DOM" in source
    assert "function reconcileEditorDom()" in source
    assert "if (historyTimer || hasUntrackedParagraphStructure())" in source
    assert "if (hasUntrackedParagraphStructure()) reconcileEditorDom()" in source
    assert "Do not rely on inputType" in source

    conversion = (FRONTEND / "editor/htmlConversion.ts").read_text(encoding="utf-8")
    assert "usedBlockIds.has(blockId)" in conversion


def test_page_number_is_calculated_instead_of_hard_coded() -> None:
    editor = (FRONTEND / "components/EditorWorkbench.svelte").read_text(encoding="utf-8")
    docir = (FRONTEND / "utils/markdown_docir.ts").read_text(encoding="utf-8")
    blocks = (FRONTEND / "utils/markdown_blocks.ts").read_text(encoding="utf-8")

    assert "function caretPage(" in editor
    assert "function visualPageHeight(" in editor
    assert "第 {documentMeta.currentPage} 页，共 {documentMeta.pages} 页" in editor
    assert '>Page 1</div>' not in docir
    assert '>Page 1</div>' not in blocks
