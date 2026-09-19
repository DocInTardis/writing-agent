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
    assert "{ ...inherited, ...style.properties }" in model


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

    for label in ("字距", "大小写", "段前", "段后", "左缩进", "右缩进", "段落边框", "段落底纹"):
        assert label in toolbar
    for state in ("letterSpacing", "textTransform", "spaceBeforePt", "spaceAfterPt", "leftIndentEm", "rightIndentEm"):
        assert state in editor


def test_unimplemented_ribbon_actions_are_not_presented_as_working() -> None:
    toolbar = (FRONTEND / "workbench/EditorCommandBar.svelte").read_text(encoding="utf-8")

    for title in (
        "链接编辑将在对象与引用阶段启用",
        "自动目录将在引用阶段启用",
        "脚注将在引用阶段启用",
        "交叉引用将在引用阶段启用",
        "查找替换尚未启用",
        "缩放尚未启用",
    ):
        assert title in toolbar
