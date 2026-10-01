from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent/web/frontend_svelte/src/lib"


def test_style_library_has_required_builtin_styles_and_inheritance() -> None:
    model = (FRONTEND / "editor-v3/model.ts").read_text(encoding="utf-8")

    for style_id in ("normal", "title", "subtitle", "quote", "caption", "code"):
        assert f"id: '{style_id}'" in model
    for level in range(1, 7):
        assert "id: `heading-${level}`" in model
    assert "export function resolvedStyleProperties" in model
    assert "visiting.has(styleId)" in model
    # Optional style fields arrive from Pydantic as null.  Null means
    # "inherit", while false and zero are intentional overrides.
    assert "Object.entries(style.properties || {}).filter" in model
    assert "value !== null && value !== undefined" in model
    assert "{ ...inherited, ...own }" in model


def test_character_and_paragraph_formatting_share_command_registry() -> None:
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    assert "registerDocumentCommand('set_character_format'" in commands
    assert "letterSpacing" in commands
    assert "textTransform" in commands
    for attribute in (
        "spaceBeforePt",
        "spaceAfterPt",
        "leftIndentEm",
        "rightIndentEm",
        "borderColor",
        "borderWidthPt",
        "borderStyle",
        "shadingColor",
        "tabStops",
    ):
        assert f"'{attribute}'" in commands
    assert "createUserCommand(type, params)" in editor


def test_advanced_formatting_controls_report_current_editor_state() -> None:
    toolbar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    for label in ("字距", "大小写", "段前", "段后", "左缩进", "右缩进", "首行/悬挂", "制表位", "与下段同页", "段中不分页", "段前分页", "段落边框", "段落底纹"):
        assert label in toolbar
    for state in ("letterSpacing", "textTransform", "spaceBeforePt", "spaceAfterPt", "leftIndentEm", "rightIndentEm", "keepWithNext", "keepLinesTogether", "pageBreakBefore", "tabStops"):
        assert state in editor


def test_reference_ribbon_actions_use_document_v3_commands() -> None:
    toolbar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")
    commands = (FRONTEND / "editor-v3/commands.ts").read_text(encoding="utf-8")
    kernel = (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")

    for command in ("link", "toc", "footnote", "cross-reference", "math-inline"):
        assert f"command('{command}')" in toolbar
    for command in ("set_link", "insert_footnote_reference", "insert_cross_reference", "insert_inline_equation", "update_table_of_contents"):
        assert f"registerDocumentCommand('{command}'" in commands
    for node in ("LinkMark", "FootnoteReferenceNode", "InlineEquationNode", "CrossReferenceNode", "TableOfContentsNode"):
        assert node in kernel


def test_find_replace_outline_zoom_and_selection_toolbar_are_connected() -> None:
    toolbar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")
    editor = (FRONTEND / "components/StructuredEditor.svelte").read_text(encoding="utf-8")

    for command in ("find-replace", "proofread", "view-outline", "zoom-in", "zoom-out", "zoom-100"):
        assert f"command('{command}')" in toolbar
    assert 'aria-label="查找和替换"' in editor
    assert "function replaceAll()" in editor
    assert 'aria-label="文档导航大纲"' in editor
    assert 'aria-label="文字选区操作"' in editor
    assert 'aria-label="基础校对结果"' in editor
    assert "spellcheck: 'true'" in (FRONTEND / "editor-v3/kernel.ts").read_text(encoding="utf-8")
