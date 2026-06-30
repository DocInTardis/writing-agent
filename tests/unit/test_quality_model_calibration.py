from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from writing_agent.quality.ai_rate import AiRateConfig, AiRateWeights, estimate_ai_rate
from writing_agent.quality.plagiarism import (
    PlagiarismConfig,
    PlagiarismWeights,
    compare_against_references,
    compare_text_pair,
)


def _load_calibration_module():
    path = Path("scripts/calibrate_quality_models.py").resolve()
    spec = importlib.util.spec_from_file_location("calibrate_quality_models", str(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plagiarism_weights_can_change_score():
    source = "治理实施阶段需要定义里程碑、责任边界和复盘机制，并记录阶段风险。"
    reference = "治理实施阶段需要定义里程碑、责任边界和复盘机制。"
    balanced = compare_text_pair(source, reference)
    sequence_heavy = compare_text_pair(
        source,
        reference,
        weights=PlagiarismWeights(containment=0.05, jaccard=0.05, winnowing_overlap=0.10, simhash_similarity=0.10, sequence_ratio=0.70),
    )
    assert float(balanced["score"]) != float(sequence_heavy["score"])
    assert balanced.get("weights")
    assert sequence_heavy.get("weights")


def test_ai_rate_config_and_weights_can_change_score():
    text = (
        "首先，本文从目标、路径和执行三个方面展开。"
        "其次，本文从目标、路径和执行三个方面展开。"
        "再次，本文从目标、路径和执行三个方面展开。"
        "最后，本文从目标、路径和执行三个方面展开。"
    )
    default_result = estimate_ai_rate(text, threshold=0.6)
    tuned_result = estimate_ai_rate(
        text,
        threshold=0.6,
        config=AiRateConfig(threshold=0.6, prior=0.20, confidence_start_tokens=0, confidence_full_tokens=40),
        weights=AiRateWeights(
            burstiness_low=0.05,
            repetition_high=0.40,
            connector_high=0.20,
            punctuation_uniform=0.10,
            entropy_low=0.10,
            lexical_diversity_low=0.10,
            template_density_high=0.05,
        ),
    )
    assert float(default_result["ai_rate"]) != float(tuned_result["ai_rate"])
    assert tuned_result.get("weights")


def test_fit_plagiarism_model_can_match_labeled_sample():
    calibration = _load_calibration_module()
    source = "治理实施阶段需要定义里程碑、责任边界和复盘机制，并记录阶段风险。"
    reference = "治理实施阶段需要定义里程碑、责任边界和复盘机制。"
    target_config = PlagiarismConfig(ngram_size=5, winnowing_k=9, winnowing_window=13, min_match_chars=16)
    target_weights = PlagiarismWeights(
        containment=0.50,
        jaccard=0.10,
        winnowing_overlap=0.20,
        simhash_similarity=0.10,
        sequence_ratio=0.10,
    )
    target = compare_against_references(
        source,
        [{"id": "r1", "title": "r1", "text": reference}],
        config=target_config,
        weights=target_weights,
    )

    result = calibration.fit_plagiarism_model(
        {
            "samples": [
                {
                    "id": "p1",
                    "target_score": float(target["max_score"]),
                    "source_text": source,
                    "reference_texts": [reference],
                }
            ],
            "search": {
                "ngram_sizes": [5, 7],
                "winnowing_ks": [9, 13],
                "winnowing_windows": [13, 17],
                "min_match_chars": [16, 24],
                "weight_candidates": [
                    target_weights.as_dict(),
                    PlagiarismWeights().as_dict(),
                ],
            },
        },
        seed=11,
    )

    assert result.objective == "plagiarism"
    assert result.sample_count == 1
    assert float(result.mae) == 0.0
    assert float(result.predictions[0]["predicted_score"]) == float(target["max_score"])


def test_fit_ai_rate_model_can_match_labeled_sample():
    calibration = _load_calibration_module()
    text = (
        "首先，本文从目标、路径和执行三个方面展开。"
        "其次，本文从目标、路径和执行三个方面展开。"
        "再次，本文从目标、路径和执行三个方面展开。"
        "最后，本文从目标、路径和执行三个方面展开。"
    )
    target_config = AiRateConfig(threshold=0.6, prior=0.20, confidence_start_tokens=0, confidence_full_tokens=40)
    target_weights = AiRateWeights(
        burstiness_low=0.05,
        repetition_high=0.40,
        connector_high=0.20,
        punctuation_uniform=0.10,
        entropy_low=0.10,
        lexical_diversity_low=0.10,
        template_density_high=0.05,
    )
    target = estimate_ai_rate(text, threshold=0.6, config=target_config, weights=target_weights)

    result = calibration.fit_ai_rate_model(
        {
            "samples": [
                {
                    "id": "a1",
                    "target_score": float(target["ai_rate"]),
                    "text": text,
                    "threshold": 0.6,
                }
            ],
            "search": {
                "priors": [0.20, 0.45],
                "confidence_start_tokens": [0, 40],
                "confidence_full_tokens": [40, 300],
                "weight_candidates": [
                    target_weights.as_dict(),
                    AiRateWeights().as_dict(),
                ],
            },
        },
        seed=13,
    )

    assert result.objective == "ai_rate"
    assert result.sample_count == 1
    assert float(result.mae) == 0.0
    assert float(result.predictions[0]["predicted_score"]) == float(target["ai_rate"])
