from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent" / "web" / "frontend_svelte" / "src"


def _read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_citation_ui_keeps_user_workflow_and_hides_diagnostics() -> None:
    panel = _read("lib/components/CitationManager.svelte")

    assert "识别链接" in panel
    assert "复制标记" in panel
    assert "核验全部" in panel
    assert "debug: false" in panel
    assert "缓存命中" not in panel
    assert "诊断 JSON" not in panel


def test_diagram_canvas_is_language_driven_and_has_no_raw_json_editor() -> None:
    canvas = _read("lib/components/DiagramCanvas.svelte")

    assert "生成后可继续用自然语言修改" in canvas
    assert "AI 二次优化" in canvas
    assert "JSON结构" not in canvas
    assert "spec-editor" not in canvas
    assert "????" not in canvas


def test_workbench_does_not_bundle_retired_admin_and_duplicate_document_panels() -> None:
    app = _read("AppWorkbench.svelte")

    assert "PerformanceMetrics" not in app
    assert "DocList" not in app
    assert not (FRONTEND / "lib/components/PerformanceMetrics.svelte").exists()
    assert not (FRONTEND / "lib/components/DocList.svelte").exists()


def test_quality_and_version_panels_use_product_language() -> None:
    quality = _read("lib/workbench/QualityPanels.svelte")
    versions = _read("lib/workbench/VersionPanel.svelte")

    assert "结果不能判断文字由谁创作" in quality
    assert "与资料库比较" in quality
    assert "下载 JSON" not in quality
    assert "版本记录" in versions
    assert "自动保存" in versions
    assert ">恢复</button>" in versions
