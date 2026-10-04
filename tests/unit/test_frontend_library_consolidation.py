from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "writing_agent" / "web" / "frontend_svelte" / "src"


def _read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_library_uses_persisted_items_instead_of_synthetic_product_cards() -> None:
    app = _read("AppWorkbench.svelte")
    cards = _read("lib/workbench/libraryCards.ts")

    assert "fetch('/api/library/items?status=all')" in app
    assert "fetch('/api/library/upload'" in app
    assert "libraryCardFromApi" in app
    assert "路由与上下文策略" not in cards
    assert "版本归档" not in cards
    assert "上传新素材" not in cards


def test_material_lifecycle_is_explicit_and_does_not_use_document_upload_classifier() -> None:
    app = _read("AppWorkbench.svelte")
    stage = _read("lib/workbench/LibraryModeStage.svelte")

    for action in ("approve", "trash", "restore"):
        assert f"updateLibraryStatus(id, '{action}')" in app
    assert "method: 'DELETE'" in app
    assert "只有“已用于 AI”的资料会参与检索" in stage
    assert "启用给 AI" in stage
    assert "`/api/doc/${$docId}/upload`" not in app


def test_settings_are_semantic_and_assistant_does_not_claim_to_show_chain_of_thought() -> None:
    settings = _read("lib/components/Settings.svelte")
    chat = _read("lib/components/Chat.svelte")

    assert "formattingJson" not in settings
    assert "prefsJson" not in settings
    assert "target_length_mode" in settings
    assert "extra_requirements" in settings
    assert "思考链" not in chat
    assert "运行记录" in chat


def test_inline_images_use_persistent_document_data_not_a_bare_filename() -> None:
    app = _read("AppWorkbench.svelte")

    assert "readFileAsDataUrl(file)" in app
    assert "source: dataUrl" in app
    assert "source: String(data.url || data.path || data.asset_url || file.name)" not in app
