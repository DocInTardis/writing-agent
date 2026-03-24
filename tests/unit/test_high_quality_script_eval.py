from __future__ import annotations

import scripts.run_dual_provider_high_quality_cn as high_quality_script


def test_evaluate_quality_uses_effective_target_chars(monkeypatch):
    monkeypatch.setattr(
        high_quality_script,
        "validate_final_document",
        lambda **_kwargs: {
            "passed": True,
            "template_padding_ratio": 0.0,
            "max_template_padding_ratio": 0.03,
            "repeat_sentence_ratio": 0.0,
            "instruction_mirroring_ratio": 0.0,
        },
    )

    body = []
    for sec in high_quality_script.REQUIRED_H2:
        if sec == "\u53c2\u8003\u6587\u732e":
            refs = [f"[{idx}] Reference Item {idx}" for idx in range(1, 19)]
            body.append(f"## {sec}\n\n" + "\n".join(refs))
            continue
        para = "\u8fd9\u662f\u56f4\u7ed5\u7814\u7a76\u4e3b\u9898\u5c55\u5f00\u7684\u5b9e\u8bc1\u5206\u6790\u5185\u5bb9\uff0c\u5305\u542b\u4e8b\u5b9e\u4f9d\u636e\u3001\u65b9\u6cd5\u8bf4\u660e\u4e0e\u7ed3\u679c\u89e3\u91ca\u3002" * 12
        body.append(f"## {sec}\n\n{para}\n")

    text = "# \u6d4b\u8bd5\u6807\u9898\n\n" + "\n\n".join(body)
    out = high_quality_script.evaluate_quality(text, target_chars=2000, requested_target_chars=9000)
    assert out.passed is True
    assert out.target_chars == 2000
    assert out.requested_target_chars == 9000
    assert out.deficits == []
