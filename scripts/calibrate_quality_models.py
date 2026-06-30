#!/usr/bin/env python3
"""Fit local quality estimators to labeled target scores.

This script can tune the local plagiarism / AI-risk estimators against
externally observed scores, but it cannot prove equivalence to any external
detector. It only minimizes error on the supplied samples.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from writing_agent.quality.ai_rate import AiRateConfig, AiRateWeights, estimate_ai_rate
from writing_agent.quality.plagiarism import (
    PlagiarismConfig,
    PlagiarismWeights,
    compare_against_references,
)


def _clamp01(value: Any) -> float:
    return max(0.0, min(1.0, float(value)))


def _read_text(payload: dict[str, Any], text_key: str, path_key: str) -> str:
    text = str(payload.get(text_key) or "")
    if text.strip():
        return text
    path = str(payload.get(path_key) or "").strip()
    if path:
        return Path(path).read_text(encoding="utf-8")
    return ""


def _read_reference_list(payload: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    raw_refs = payload.get("references")
    if isinstance(raw_refs, list):
        for idx, item in enumerate(raw_refs):
            if not isinstance(item, dict):
                continue
            text = _read_text(item, "text", "path")
            if not text.strip():
                continue
            refs.append(
                {
                    "id": str(item.get("id") or f"ref_{idx + 1}"),
                    "title": str(item.get("title") or item.get("id") or f"ref_{idx + 1}"),
                    "text": text,
                }
            )
    raw_texts = payload.get("reference_texts")
    if isinstance(raw_texts, list):
        for idx, item in enumerate(raw_texts):
            text = str(item or "")
            if text.strip():
                refs.append({"id": f"reference_text_{idx + 1}", "title": f"reference_text_{idx + 1}", "text": text})
    raw_paths = payload.get("reference_paths")
    if isinstance(raw_paths, list):
        for idx, item in enumerate(raw_paths):
            path = str(item or "").strip()
            if path:
                refs.append(
                    {
                        "id": f"reference_path_{idx + 1}",
                        "title": Path(path).name or f"reference_path_{idx + 1}",
                        "text": Path(path).read_text(encoding="utf-8"),
                    }
                )
    return refs


def _dicts_to_plagiarism_weights(candidates: Iterable[dict[str, Any]] | None) -> list[PlagiarismWeights]:
    items: list[PlagiarismWeights] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        items.append(PlagiarismWeights(**item).normalized())
    return items


def _dicts_to_ai_weights(candidates: Iterable[dict[str, Any]] | None) -> list[AiRateWeights]:
    items: list[AiRateWeights] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        items.append(AiRateWeights(**item).normalized())
    return items


def _random_simplex_vectors(names: list[str], *, count: int, seed: int) -> list[dict[str, float]]:
    rng = random.Random(seed)
    rows: list[dict[str, float]] = []
    for _ in range(max(0, int(count))):
        raw = [rng.random() for _ in names]
        total = sum(raw) or 1.0
        rows.append({name: raw[idx] / total for idx, name in enumerate(names)})
    return rows


def default_plagiarism_weight_candidates(*, seed: int, extra_random: int = 96) -> list[PlagiarismWeights]:
    base = [
        PlagiarismWeights(),
        PlagiarismWeights(containment=0.55, jaccard=0.15, winnowing_overlap=0.15, simhash_similarity=0.10, sequence_ratio=0.05),
        PlagiarismWeights(containment=0.20, jaccard=0.20, winnowing_overlap=0.40, simhash_similarity=0.10, sequence_ratio=0.10),
        PlagiarismWeights(containment=0.15, jaccard=0.20, winnowing_overlap=0.10, simhash_similarity=0.10, sequence_ratio=0.45),
    ]
    random_rows = _random_simplex_vectors(
        ["containment", "jaccard", "winnowing_overlap", "simhash_similarity", "sequence_ratio"],
        count=extra_random,
        seed=seed,
    )
    return base + [PlagiarismWeights(**row).normalized() for row in random_rows]


def default_ai_weight_candidates(*, seed: int, extra_random: int = 96) -> list[AiRateWeights]:
    base = [
        AiRateWeights(),
        AiRateWeights(burstiness_low=0.10, repetition_high=0.35, connector_high=0.20, punctuation_uniform=0.10, entropy_low=0.10, lexical_diversity_low=0.10, template_density_high=0.05),
        AiRateWeights(burstiness_low=0.10, repetition_high=0.10, connector_high=0.10, punctuation_uniform=0.10, entropy_low=0.30, lexical_diversity_low=0.25, template_density_high=0.05),
    ]
    random_rows = _random_simplex_vectors(
        [
            "burstiness_low",
            "repetition_high",
            "connector_high",
            "punctuation_uniform",
            "entropy_low",
            "lexical_diversity_low",
            "template_density_high",
        ],
        count=extra_random,
        seed=seed,
    )
    return base + [AiRateWeights(**row).normalized() for row in random_rows]


@dataclass
class CalibrationResult:
    objective: str
    sample_count: int
    mae: float
    rmse: float
    best_params: dict[str, Any]
    predictions: list[dict[str, Any]]


def _error_summary(predictions: list[dict[str, Any]]) -> tuple[float, float]:
    if not predictions:
        return 0.0, 0.0
    abs_errors = [float(item["abs_error"]) for item in predictions]
    sq_errors = [float(item["abs_error"]) ** 2 for item in predictions]
    mae = sum(abs_errors) / len(abs_errors)
    rmse = (sum(sq_errors) / len(sq_errors)) ** 0.5
    return round(mae, 6), round(rmse, 6)


def fit_plagiarism_model(payload: dict[str, Any], *, seed: int = 7) -> CalibrationResult:
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("plagiarism.samples must be a non-empty list")

    samples: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_samples):
        if not isinstance(item, dict):
            continue
        source_text = _read_text(item, "source_text", "source_path")
        references = _read_reference_list(item)
        if not source_text.strip() or not references:
            continue
        samples.append(
            {
                "id": str(item.get("id") or f"sample_{idx + 1}"),
                "target_score": _clamp01(item.get("target_score")),
                "source_text": source_text,
                "references": references,
                "threshold": float(item.get("threshold") or payload.get("threshold") or 0.35),
            }
        )
    if not samples:
        raise ValueError("plagiarism.samples did not contain any valid sample")

    search = payload.get("search") if isinstance(payload.get("search"), dict) else {}
    ngram_sizes = [int(x) for x in (search.get("ngram_sizes") or [5, 7, 9])]
    winnowing_ks = [int(x) for x in (search.get("winnowing_ks") or [9, 13, 17])]
    winnowing_windows = [int(x) for x in (search.get("winnowing_windows") or [13, 17, 21])]
    min_match_chars = [int(x) for x in (search.get("min_match_chars") or [16, 24, 32])]
    explicit_weight_candidates = _dicts_to_plagiarism_weights(search.get("weight_candidates"))
    weight_candidates = explicit_weight_candidates or default_plagiarism_weight_candidates(
        seed=int(search.get("seed") or seed),
        extra_random=int(search.get("random_weight_count") or 96),
    )

    best: CalibrationResult | None = None
    for ngram_size in ngram_sizes:
        for winnowing_k in winnowing_ks:
            for winnowing_window in winnowing_windows:
                for min_match in min_match_chars:
                    config = PlagiarismConfig(
                        ngram_size=ngram_size,
                        winnowing_k=winnowing_k,
                        winnowing_window=winnowing_window,
                        min_match_chars=min_match,
                    ).normalized()
                    for weights in weight_candidates:
                        predictions: list[dict[str, Any]] = []
                        for sample in samples:
                            result = compare_against_references(
                                sample["source_text"],
                                sample["references"],
                                threshold=float(sample["threshold"]),
                                top_k=max(1, len(sample["references"])),
                                config=config,
                                weights=weights,
                            )
                            predicted = float(result.get("max_score") or 0.0)
                            target = float(sample["target_score"])
                            predictions.append(
                                {
                                    "id": sample["id"],
                                    "target_score": round(target, 6),
                                    "predicted_score": round(predicted, 6),
                                    "abs_error": round(abs(target - predicted), 6),
                                }
                            )
                        mae, rmse = _error_summary(predictions)
                        candidate = CalibrationResult(
                            objective="plagiarism",
                            sample_count=len(samples),
                            mae=mae,
                            rmse=rmse,
                            best_params={
                                "config": asdict(config),
                                "weights": weights.as_dict(),
                            },
                            predictions=predictions,
                        )
                        if best is None or (candidate.mae, candidate.rmse) < (best.mae, best.rmse):
                            best = candidate
    if best is None:
        raise RuntimeError("failed to evaluate plagiarism candidates")
    return best


def fit_ai_rate_model(payload: dict[str, Any], *, seed: int = 7) -> CalibrationResult:
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("ai_rate.samples must be a non-empty list")

    samples: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_samples):
        if not isinstance(item, dict):
            continue
        text = _read_text(item, "text", "path")
        if not text.strip():
            continue
        samples.append(
            {
                "id": str(item.get("id") or f"sample_{idx + 1}"),
                "target_score": _clamp01(item.get("target_score")),
                "text": text,
                "threshold": float(item.get("threshold") or payload.get("threshold") or 0.65),
            }
        )
    if not samples:
        raise ValueError("ai_rate.samples did not contain any valid sample")

    search = payload.get("search") if isinstance(payload.get("search"), dict) else {}
    priors = [float(x) for x in (search.get("priors") or [0.35, 0.45, 0.55])]
    confidence_starts = [int(x) for x in (search.get("confidence_start_tokens") or [20, 40, 80])]
    confidence_fulls = [int(x) for x in (search.get("confidence_full_tokens") or [160, 300, 500])]
    explicit_weight_candidates = _dicts_to_ai_weights(search.get("weight_candidates"))
    weight_candidates = explicit_weight_candidates or default_ai_weight_candidates(
        seed=int(search.get("seed") or seed),
        extra_random=int(search.get("random_weight_count") or 96),
    )

    best: CalibrationResult | None = None
    for prior in priors:
        for confidence_start in confidence_starts:
            for confidence_full in confidence_fulls:
                if confidence_full <= confidence_start:
                    continue
                for weights in weight_candidates:
                    predictions: list[dict[str, Any]] = []
                    for sample in samples:
                        config = AiRateConfig(
                            threshold=float(sample["threshold"]),
                            prior=prior,
                            confidence_start_tokens=confidence_start,
                            confidence_full_tokens=confidence_full,
                        )
                        result = estimate_ai_rate(sample["text"], threshold=float(sample["threshold"]), config=config, weights=weights)
                        predicted = float(result.get("ai_rate") or 0.0)
                        target = float(sample["target_score"])
                        predictions.append(
                            {
                                "id": sample["id"],
                                "target_score": round(target, 6),
                                "predicted_score": round(predicted, 6),
                                "abs_error": round(abs(target - predicted), 6),
                            }
                        )
                    mae, rmse = _error_summary(predictions)
                    candidate = CalibrationResult(
                        objective="ai_rate",
                        sample_count=len(samples),
                        mae=mae,
                        rmse=rmse,
                        best_params={
                            "config": {
                                "prior": round(prior, 6),
                                "confidence_start_tokens": confidence_start,
                                "confidence_full_tokens": confidence_full,
                            },
                            "weights": weights.as_dict(),
                        },
                        predictions=predictions,
                    )
                    if best is None or (candidate.mae, candidate.rmse) < (best.mae, best.rmse):
                        best = candidate
    if best is None:
        raise RuntimeError("failed to evaluate ai_rate candidates")
    return best


def run_calibration(payload: dict[str, Any], *, seed: int = 7) -> dict[str, Any]:
    output: dict[str, Any] = {
        "note": (
            "This only fits the local estimator to supplied labels. "
            "It does not prove equivalence to any external detector."
        ),
        "results": {},
    }
    if isinstance(payload.get("plagiarism"), dict):
        output["results"]["plagiarism"] = asdict(fit_plagiarism_model(payload["plagiarism"], seed=seed))
    if isinstance(payload.get("ai_rate"), dict):
        output["results"]["ai_rate"] = asdict(fit_ai_rate_model(payload["ai_rate"], seed=seed))
    if not output["results"]:
        raise ValueError("input must include plagiarism and/or ai_rate sections")
    return output


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calibrate local quality estimators against labeled target scores.")
    parser.add_argument("--input", required=True, help="Path to the calibration JSON payload.")
    parser.add_argument("--output", default="", help="Optional output JSON path.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed used for candidate generation.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = run_calibration(payload, seed=int(args.seed))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if str(args.output or "").strip():
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
