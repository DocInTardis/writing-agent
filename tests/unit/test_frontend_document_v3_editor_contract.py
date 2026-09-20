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


def test_export_flushes_current_editor_state_before_preflight() -> None:
    app = (ROOT / "writing_agent/web/frontend_svelte/src/AppWorkbench.svelte").read_text(encoding="utf-8")

    assert "if (!(await saveDoc({ quiet: true }))) return false" in app
    assert "lastSavedText = txt" not in app[app.index("function handleBlockEdit"):app.index("function handleToolbarState")]


def test_context_toolbar_requires_a_real_selection() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "const exposedBlocks = empty ? [] : blocks" in editor
    assert "blocks: exposedBlocks.map" in editor
    assert "instanceof CellSelection" in editor


def test_tables_use_the_editable_tiptap_table_model() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")

    assert "import { Table, TableCell, TableHeader, TableRow, TableView } from '@tiptap/extension-table'" in kernel
    assert "Table.configure({ resizable: true, View: DocumentTableView })" in kernel
    assert "StyledTableCell" in kernel
    assert "StyledTableHeader" in kernel
    assert "class DocumentTableView extends TableView" in kernel
    assert "Table.configure({ resizable: true, View: DocumentTableView })" in kernel
    assert "tableBlockToJson" in kernel
    assert "tableFromJson" in kernel
    assert "rowspan: Math.max" in kernel
    assert "backgroundColor: cell.attrs?.backgroundColor" in kernel
    assert "} else {\n    if (columns.length)" in kernel
    assert ".insertTable({" in commands


def test_table_context_actions_share_the_document_command_pipeline() -> None:
    app = (ROOT / "writing_agent/web/frontend_svelte/src/AppWorkbench.svelte").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    command_bar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")

    assert "inTable: editor.isActive('table')" in editor
    assert "canMergeCells: editor.isActive('table') && editor.can().mergeCells()" in editor
    assert "inTable: Boolean((detail as any).inTable)" in app
    assert 'aria-label="表格工具"' in command_bar
    for ui_command, document_command in (
        ("table-row-before", "table_add_row_before"),
        ("table-row-after", "table_add_row_after"),
        ("table-row-delete", "table_delete_row"),
        ("table-column-before", "table_add_column_before"),
        ("table-column-after", "table_add_column_after"),
        ("table-column-delete", "table_delete_column"),
        ("table-merge-cells", "table_merge_cells"),
        ("table-split-cell", "table_split_cell"),
        ("table-toggle-header-row", "table_toggle_header_row"),
        ("table-toggle-header-column", "table_toggle_header_column"),
        ("table-toggle-header-cell", "table_toggle_header_cell"),
        ("table-distribute-columns", "table_distribute_columns"),
        ("table-distribute-rows", "table_distribute_rows"),
        ("table-toggle-repeat-header", "table_set_repeat_header"),
        ("table-delete", "table_delete"),
    ):
        assert f"'{ui_command}': '{document_command}'" in editor
        assert f"registerDocumentCommand('{document_command}'" in commands
    assert "params = { alignment: command.slice(18) }" in editor
    for document_command in (
        "table_set_caption",
        "table_set_alignment",
        "table_set_width",
        "table_set_repeat_header",
    ):
        assert f"registerDocumentCommand('{document_command}'" in commands


def test_table_properties_round_trip_through_the_canonical_model() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    command_bar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")

    for property_name in ("repeatHeader", "tableAlignment", "widthPercent"):
        assert property_name in kernel
    assert "tableCellVerticalAlign" in editor
    assert 'aria-label="表格题注"' in command_bar
    assert 'aria-label="表格对齐"' in command_bar
    assert 'aria-label="表格宽度"' in command_bar
