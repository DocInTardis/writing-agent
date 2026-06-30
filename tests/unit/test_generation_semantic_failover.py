from dataclasses import dataclass
from types import SimpleNamespace

from writing_agent.web.services.generation_service import GenerationService


@dataclass
class _Session:
    template_required_h2: list[str]
    template_outline: list
    generation_prefs: dict


def test_semantic_failure_does_not_trigger_single_pass_fallback(monkeypatch) -> None:
    service = GenerationService()
    called = {"single_pass": 0}

    class _FakeOS:
        environ = {
            "WRITING_AGENT_USE_ROUTE_GRAPH": "1",
            "WRITING_AGENT_WORKERS": "2",
        }

    class _FakeApp:
        os = _FakeOS()

        @staticmethod
        def run_generate_graph_dual_engine(**_kwargs):
            return {
                "text": "",
                "problems": ["analysis_needs_clarification"],
                "terminal_status": "failed",
                "failure_reason": "analysis_needs_clarification",
                "quality_snapshot": {
                    "status": "failed",
                    "reason": "analysis_needs_clarification",
                },
            }

        @staticmethod
        def _single_pass_generate(*_args, **_kwargs):
            called["single_pass"] += 1
            return "fallback-text"

    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={})
    final_text, problems, graph_meta = service._run_graph_with_fallback(
        app_v2=_FakeApp(),
        session=session,
        instruction="请写论文",
        raw_instruction="请写论文",
        compose_mode="auto",
        resume_sections=[],
        base_text="",
        cfg=object(),
        target_chars=1200,
        plan_confirm={},
    )
    assert called["single_pass"] == 0
    assert final_text == ""
    assert "analysis_needs_clarification" in problems
    assert graph_meta["terminal_status"] == "failed"
    assert graph_meta["failure_reason"] == "analysis_needs_clarification"


def test_should_prefer_single_pass_provider_mode_only_for_openai_responses(monkeypatch) -> None:
    service = GenerationService()
    session = _Session(template_required_h2=[], template_outline=[], generation_prefs={"quality_profile": "academic_cnki_default"})

    monkeypatch.setenv("WRITING_AGENT_PREFER_SINGLE_PASS_RESPONSES", "1")
    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.get_provider_snapshot",
        lambda: {"provider": "openai", "wire_api": "responses"},
    )

    assert service._should_prefer_single_pass_provider_mode(
        session=session,
        compose_mode="auto",
        resume_sections=[],
        base_text="",
    ) is True
    assert service._should_prefer_single_pass_provider_mode(
        session=session,
        compose_mode="continue",
        resume_sections=[],
        base_text="",
    ) is False
    assert service._should_prefer_single_pass_provider_mode(
        session=session,
        compose_mode="auto",
        resume_sections=["引言"],
        base_text="",
    ) is False
    assert service._should_prefer_single_pass_provider_mode(
        session=session,
        compose_mode="auto",
        resume_sections=[],
        base_text="# existing",
    ) is False


def test_run_single_pass_provider_mode_returns_direct_result_with_graph_meta(monkeypatch) -> None:
    service = GenerationService()
    session = SimpleNamespace(
        formatting={},
        generation_prefs={},
        template_required_h2=["Intro"],
        template_outline=[],
        title="Title",
    )
    stored = {"text": ""}

    class _Store:
        @staticmethod
        def put(_session) -> None:
            return None

    class _FakeApp:
        store = _Store()

        @staticmethod
        def _augment_instruction(instruction, **_kwargs):
            return instruction + "\naugmented"

        @staticmethod
        def _resolve_target_chars(*_args, **_kwargs):
            return 1800

        @staticmethod
        def _extract_target_chars_from_instruction(_instruction):
            return 0

        @staticmethod
        def _single_pass_generate(_session, **_kwargs):
            return "# Title\n\n## Intro\nprovider mode text with citation [1]"

        @staticmethod
        def _looks_like_prompt_echo(_text, _instruction):
            return False

        @staticmethod
        def _postprocess_output_text(_session, text, _instruction, **_kwargs):
            return text

        @staticmethod
        def _set_doc_text(_session, text):
            stored["text"] = text

        @staticmethod
        def _auto_commit_version(_session, _message):
            return None

        @staticmethod
        def _safe_doc_ir_payload(text):
            return {"text": text}

        @staticmethod
        def _check_generation_quality(_text, _target_chars):
            return []

        @staticmethod
        def _extract_title(_text):
            return "Title"

    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.get_provider_snapshot",
        lambda: {"provider": "openai", "wire_api": "responses", "base_url": "https://aixj.vip/v1"},
    )
    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.final_validator.validate_final_document",
        lambda **_kwargs: {"passed": True},
    )

    result = service._run_single_pass_provider_mode(
        app_v2=_FakeApp(),
        session=session,
        compose_instruction="write document",
        raw_instruction="write document",
        base_text="",
    )

    assert result is not None
    assert result["ok"] == 1
    assert result["status"] == "success"
    assert result["text"] == stored["text"]
    assert result["problems"] == []
    assert result["graph_meta"]["path"] == "single_pass_provider_mode"
    assert result["graph_meta"]["engine"] == "single_pass"
    assert result["graph_meta"]["quality_snapshot"]["single_pass_provider_mode"] is True
    assert result["graph_meta"]["quality_snapshot"]["final_validator"]["passed"] is True


def test_run_single_pass_provider_mode_returns_none_when_validation_fails(monkeypatch) -> None:
    service = GenerationService()
    session = SimpleNamespace(
        formatting={},
        generation_prefs={},
        template_required_h2=["摘要", "关键词", "引言"],
        template_outline=[],
        title="区块链赋能乡村社会化服务的组织协同机制研究",
    )

    class _Store:
        @staticmethod
        def put(_session) -> None:
            return None

    class _FakeApp:
        store = _Store()

        @staticmethod
        def _augment_instruction(instruction, **_kwargs):
            return instruction

        @staticmethod
        def _resolve_target_chars(*_args, **_kwargs):
            return 1800

        @staticmethod
        def _extract_target_chars_from_instruction(_instruction):
            return 0

        @staticmethod
        def _single_pass_generate(_session, **_kwargs):
            return "# 自动生成文档\n\n## 背景\n偏题内容"

        @staticmethod
        def _looks_like_prompt_echo(_text, _instruction):
            return False

        @staticmethod
        def _postprocess_output_text(_session, text, _instruction, **_kwargs):
            return text

        @staticmethod
        def _check_generation_quality(_text, _target_chars):
            return []

        @staticmethod
        def _extract_title(text):
            return "自动生成文档" if text else ""

    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.final_validator.validate_final_document",
        lambda **_kwargs: {"passed": False, "missing_sections": ["摘要"], "unexpected_sections": ["背景"]},
    )

    result = service._run_single_pass_provider_mode(
        app_v2=_FakeApp(),
        session=session,
        compose_instruction="write document",
        raw_instruction="write document",
        base_text="",
    )

    assert result is None


def test_run_single_pass_provider_mode_accepts_structurally_valid_result_under_lenient_gate(monkeypatch) -> None:
    service = GenerationService()
    session = SimpleNamespace(
        formatting={},
        generation_prefs={},
        template_required_h2=["摘要", "关键词", "引言"],
        template_outline=[],
        title="区块链赋能乡村社会化服务的组织协同机制研究",
    )
    stored = {"text": ""}

    class _Store:
        @staticmethod
        def put(_session) -> None:
            return None

    class _FakeApp:
        store = _Store()

        @staticmethod
        def _augment_instruction(instruction, **_kwargs):
            return instruction

        @staticmethod
        def _resolve_target_chars(*_args, **_kwargs):
            return 1800

        @staticmethod
        def _extract_target_chars_from_instruction(_instruction):
            return 0

        @staticmethod
        def _single_pass_generate(_session, **_kwargs):
            return "# 区块链赋能乡村社会化服务的组织协同机制研究\n\n## 摘要\n内容[1]\n\n## 关键词\n区块链；乡村服务\n\n## 引言\n内容[1]"

        @staticmethod
        def _looks_like_prompt_echo(_text, _instruction):
            return False

        @staticmethod
        def _postprocess_output_text(_session, text, _instruction, **_kwargs):
            return text

        @staticmethod
        def _set_doc_text(_session, text):
            stored["text"] = text

        @staticmethod
        def _auto_commit_version(_session, _message):
            return None

        @staticmethod
        def _safe_doc_ir_payload(text):
            return {"text": text}

        @staticmethod
        def _check_generation_quality(_text, _target_chars):
            return []

        @staticmethod
        def _extract_title(_text):
            return "区块链赋能乡村社会化服务的组织协同机制研究"

    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.get_provider_snapshot",
        lambda: {"provider": "openai", "wire_api": "responses", "base_url": "https://aixj.vip/v1"},
    )
    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.final_validator.validate_final_document",
        lambda **_kwargs: {
            "passed": False,
            "structure_passed": True,
            "section_order_passed": True,
            "missing_sections": [],
            "unexpected_sections": [],
            "duplicate_sections": [],
            "empty_sections": [],
            "meta_residue_zero": True,
            "title_body_alignment_score": 0.92,
            "repeat_sentence_ratio": 0.0,
            "instruction_mirroring_ratio": 0.0,
            "placeholder_residue_ratio": 0.0,
        },
    )

    result = service._run_single_pass_provider_mode(
        app_v2=_FakeApp(),
        session=session,
        compose_instruction="write document",
        raw_instruction="write document",
        base_text="",
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["text"] == stored["text"]
    assert result["graph_meta"]["needs_review"] is True
    assert result["graph_meta"]["quality_snapshot"]["provider_mode_lenient_gate"] is True


def test_run_single_pass_provider_mode_retries_after_invalid_attempt(monkeypatch) -> None:
    service = GenerationService()
    session = SimpleNamespace(
        formatting={},
        generation_prefs={},
        template_required_h2=["摘要", "关键词", "引言"],
        template_outline=[],
        title="区块链赋能乡村社会化服务的组织协同机制研究",
    )
    stored = {"text": ""}
    calls = {"count": 0, "instructions": []}

    class _Store:
        @staticmethod
        def put(_session) -> None:
            return None

    class _FakeApp:
        store = _Store()

        @staticmethod
        def _augment_instruction(instruction, **_kwargs):
            calls["instructions"].append(instruction)
            return instruction

        @staticmethod
        def _resolve_target_chars(*_args, **_kwargs):
            return 1800

        @staticmethod
        def _extract_target_chars_from_instruction(_instruction):
            return 0

        @staticmethod
        def _single_pass_generate(_session, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return "# 自动生成文档\n\n## 背景\n偏题内容"
            return "# 区块链赋能乡村社会化服务的组织协同机制研究\n\n## 摘要\n内容[1]\n\n## 关键词\n区块链；乡村服务\n\n## 引言\n内容[1]"

        @staticmethod
        def _looks_like_prompt_echo(_text, _instruction):
            return False

        @staticmethod
        def _postprocess_output_text(_session, text, _instruction, **_kwargs):
            return text

        @staticmethod
        def _set_doc_text(_session, text):
            stored["text"] = text

        @staticmethod
        def _auto_commit_version(_session, _message):
            return None

        @staticmethod
        def _safe_doc_ir_payload(text):
            return {"text": text}

        @staticmethod
        def _check_generation_quality(_text, _target_chars):
            return []

        @staticmethod
        def _extract_title(text):
            return "自动生成文档" if "自动生成文档" in text else "区块链赋能乡村社会化服务的组织协同机制研究"

    monkeypatch.setenv("WRITING_AGENT_PROVIDER_MODE_RETRIES", "2")
    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.get_provider_snapshot",
        lambda: {"provider": "openai", "wire_api": "responses", "base_url": "https://aixj.vip/v1"},
    )
    validations = iter(
        [
            {
                "passed": False,
                "structure_passed": False,
                "section_order_passed": False,
                "missing_sections": ["摘要"],
                "unexpected_sections": ["背景"],
                "duplicate_sections": [],
                "empty_sections": [],
                "meta_residue_zero": True,
                "title_body_alignment_score": 0.1,
                "repeat_sentence_ratio": 0.0,
                "instruction_mirroring_ratio": 0.0,
                "placeholder_residue_ratio": 0.0,
            },
            {
                "passed": True,
                "structure_passed": True,
                "section_order_passed": True,
                "missing_sections": [],
                "unexpected_sections": [],
                "duplicate_sections": [],
                "empty_sections": [],
                "meta_residue_zero": True,
                "title_body_alignment_score": 0.96,
                "repeat_sentence_ratio": 0.0,
                "instruction_mirroring_ratio": 0.0,
                "placeholder_residue_ratio": 0.0,
            },
        ]
    )
    monkeypatch.setattr(
        "writing_agent.web.services.generation_service.final_validator.validate_final_document",
        lambda **_kwargs: next(validations),
    )

    result = service._run_single_pass_provider_mode(
        app_v2=_FakeApp(),
        session=session,
        compose_instruction="write document",
        raw_instruction="write document",
        base_text="",
    )

    assert result is not None
    assert result["status"] == "success"
    assert result["text"] == stored["text"]
    assert calls["count"] == 2
    assert any("Retry from scratch." in instruction for instruction in calls["instructions"][1:])
