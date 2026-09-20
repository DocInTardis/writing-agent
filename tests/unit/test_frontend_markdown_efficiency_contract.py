from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_markdown_is_interchange_not_document_source_of_truth() -> None:
    markdown = (FRONTEND / "editor-v3/markdown.ts").read_text(encoding="utf-8")

    assert "export function markdownToBlocks" in markdown
    assert "export function replaceDocumentContentFromMarkdown" in markdown
    assert "export function documentV3ToMarkdown" in markdown
    assert "const next = structuredClone(document)" in markdown
    assert "Document V3 继续保存页面和样式设置" in markdown
    assert "WRITING_AGENT_MODEL" in markdown
    for block_type in ("heading", "bulletList", "orderedList", "blockquote", "codeBlock", "horizontalRule", "pageBreak"):
        assert block_type in markdown


def test_markdown_export_warns_before_lossy_download() -> None:
    markdown = (FRONTEND / "editor-v3/markdown.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")
    toolbar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")

    for subject in ("页眉页脚", "页码格式", "批注和修订", "结构化引文", "表格", "图片和图形"):
        assert subject in markdown
    assert 'aria-labelledby="markdown-export-title"' in editor
    assert "markdownExportWarnings" in editor
    assert "Document V3 原文档未改变" in editor
    assert "command('markdown-import')" in toolbar
    assert "command('markdown-export')" in toolbar


def test_block_shortcuts_use_registered_document_commands_and_ignore_ime() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "event.isComposing || event.keyCode === 229" in kernel
    assert "event.altKey && event.shiftKey" in kernel
    assert "'move_block_up' : 'move_block_down'" in kernel
    assert "'apply_style', { styleId }" in kernel
    assert "reliableMarkdownRuleUndo" in kernel
    assert "onCommand?.('restore_markdown_trigger', recent)" in kernel
    assert "registerDocumentCommand('restore_markdown_trigger'" in commands
    assert "export function createShortcutCommand" in commands
    assert "source: 'shortcut'" in commands
    assert "executeDocumentCommand(editor, createShortcutCommand(type, params))" in editor
    assert 'aria-label="编辑快捷键"' in editor
    settings = (FRONTEND / "components/Settings.svelte").read_text(encoding="utf-8")
    assert '<summary>编辑快捷键</summary>' in settings
    assert "输入法组合输入期间不会接管" in settings


def test_starterkit_input_rules_and_undo_remain_enabled() -> None:
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    assert "StarterKit.configure" in kernel
    assert "inputRules: false" not in kernel
    assert "restore_markdown_trigger" in kernel
