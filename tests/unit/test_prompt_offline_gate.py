from pathlib import Path

from writing_agent.v2.prompt_registry import PromptRegistry

from scripts import prompt_offline_gate


def test_prompt_offline_gate_reports_pass(tmp_path: Path) -> None:
    data = tmp_path / "cases.jsonl"
    data.write_text(
        "\n".join(
            [
                '{"structure_ok": true, "zh_rate": 0.95, "hierarchy_ok": true, "citation_ok": true}',
                '{"structure_ok": true, "zh_rate": 0.92, "hierarchy_ok": true, "citation_ok": true}',
            ]
        ),
        encoding="utf-8",
    )
    reg = PromptRegistry(path=tmp_path / "prompts.json")
    summary = prompt_offline_gate.evaluate(
        prompt_offline_gate._load_rows(data),
        registry=reg,
    )
    assert summary.total == 2
    assert summary.pass_gate is True
    assert summary.fail_reasons == []


def test_prompt_offline_gate_reports_failure(tmp_path: Path) -> None:
    data = tmp_path / "cases.jsonl"
    data.write_text(
        "\n".join(
            [
                '{"structure_ok": false, "zh_rate": 0.50, "hierarchy_ok": false, "citation_ok": false}',
                '{"structure_ok": true, "zh_rate": 0.60, "hierarchy_ok": false, "citation_ok": true}',
            ]
        ),
        encoding="utf-8",
    )
    reg = PromptRegistry(path=tmp_path / "prompts.json")
    summary = prompt_offline_gate.evaluate(
        prompt_offline_gate._load_rows(data),
        registry=reg,
    )
    assert summary.total == 2
    assert summary.pass_gate is False
    assert "zh_rate" in summary.fail_reasons
    assert "structure_rate" in summary.fail_reasons
