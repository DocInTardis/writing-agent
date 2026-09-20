from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_keyboard_can_enter_navigate_and_leave_block_selection() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "ReliableBlockKeyboard" in kernel
    assert "event.code === 'Space'" in kernel
    assert "NodeSelection.create" in kernel
    assert "event.key === 'ArrowUp' || event.key === 'ArrowDown'" in kernel
    assert "event.key === 'Escape'" in kernel
    assert "TextSelection.near" in kernel


def test_block_commands_support_multi_block_transactions() -> None:
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")

    assert "selectedTopLevelRange" in commands
    assert "Fragment.fromArray(selected.nodes" in commands
    assert "registerDocumentCommand('move_blocks'" in commands
    assert "registerDocumentCommand('insert_block_before'" in commands
    assert "registerDocumentCommand('insert_block_after'" in commands
    assert "registerDocumentCommand('convert_block'" in commands
    assert "createNodeCommand" in commands


def test_dragging_blocks_uses_command_registry_not_dom_reparenting() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "handleBlockPointerDown" in editor
    assert "handleBlockPointerUp" in editor
    assert "updateBlockDropTarget" in editor
    assert "createNodeCommand('move_blocks'" in editor
    assert "block-drop-indicator" in editor
    assert "nearestTopLevelBlock" in editor
    assert "setPointerCapture" in editor
    assert "nearestScrollableAncestor" in editor
    assert "requestAnimationFrame(runBlockAutoScroll)" in editor
    assert "document.elementFromPoint" in editor
    assert "stopBlockAutoScroll()" in editor
    assert "onblockdrag?.(true)" in editor
    assert "onblockdrag?.(false)" in editor
    assert "onblockdrag={handleBlockDrag}" in (ROOT / "writing_agent/web/frontend_svelte/src/AppWorkbench.svelte").read_text(encoding="utf-8")
    assert "createNodeCommand('move_blocks'" in editor
    assert "host.appendChild(" not in editor
    assert "element.appendChild(" not in editor


def test_slash_menu_lists_only_registered_executable_actions() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "const slashCommands" in editor
    assert 'aria-label="插入块"' in editor
    assert "onkeydowncapture={handleShellKeyDown}" in editor
    assert "onSlashQuery: handleSlashQuery" in editor
    assert "onSlashQuery?:" in kernel
    for command in (
        "insert_page_break",
        "insert_figure",
        "insert_table",
        "insert_equation",
    ):
        assert f"registerDocumentCommand('{command}'" in commands


def test_block_menu_exposes_complete_block_workflow() -> None:
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    workbench = (ROOT / "writing_agent/web/frontend_svelte/src/AppWorkbench.svelte").read_text(encoding="utf-8")

    for label in (
        "在前面插入段落",
        "在后面插入段落",
        "上移块",
        "下移块",
        "复制块内容",
        "创建块副本",
        "折叠块",
        "展开块",
        "使用 AI 处理所选块",
        "转换块类型",
        "删除块",
    ):
        assert label in editor
    assert "navigator.clipboard.writeText(text)" in editor
    assert "registerDocumentCommand('toggle_block_collapsed'" in commands
    assert "transaction.setNodeMarkup" in commands
    assert "data-collapsed" in kernel
    assert "editor.state.doc.forEach((node, position)" in kernel
    assert "onblockai={handleBlockAi}" in workbench
    assert "openInlinePopover('assistant', 'down')" in workbench
    assert "document.querySelector('.structured-editor .tiptap, .editable')" in workbench
    assert '`[data-node-id="${escaped}"], [data-block-id="${escaped}"]`' in workbench
