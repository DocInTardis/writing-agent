"""Section originality hot-sample helpers for runtime drafting."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from writing_agent.v2 import final_validator


@dataclass
class OriginalityTracker:
    rows: dict[str, dict[str, object]] = field(default_factory=dict)
    checked_ids: set[str] = field(default_factory=set)
    failed_ids: set[str] = field(default_factory=set)
    rewrite_ids: set[str] = field(default_factory=set)
    retry_ids: set[str] = field(default_factory=set)
    counts: dict[str, int] = field(default_factory=lambda: {
        "event_count": 0,
        "checked_event_count": 0,
        "passed_event_count": 0,
        "failed_event_count": 0,
        "rewrite_count": 0,
        "retry_count": 0,
        "cache_rejected_count": 0,
        "fast_draft_rejected_count": 0,
    })

    def ensure_row(self, *, section: str, section_id: str, title: str) -> dict[str, object]:
        key = str(section_id or section).strip()
        row = self.rows.get(key)
        if row is None:
            row = {
                "section": section,
                "section_id": key,
                "title": title,
                "phases": [],
                "checked_event_count": 0,
                "failed_event_count": 0,
                "rewrite_count": 0,
                "retry_count": 0,
                "cache_rejected_count": 0,
                "fast_draft_rejected_count": 0,
                "latest_passed": True,
                "max_repeat_sentence_ratio": 0.0,
                "max_formulaic_opening_ratio": 0.0,
                "max_source_overlap_ratio": 0.0,
            }
            self.rows[key] = row
        else:
            row["section"] = section
            row["title"] = title
        return row

    def record_action(self, *, section: str, section_id: str, title: str, action: str) -> None:
        row = self.ensure_row(section=section, section_id=section_id, title=title)
        if action == "rewrite":
            self.counts["rewrite_count"] += 1
            row["rewrite_count"] = int(row.get("rewrite_count") or 0) + 1
            self.rewrite_ids.add(str(row.get("section_id") or "").strip())
        elif action == "retry":
            self.counts["retry_count"] += 1
            row["retry_count"] = int(row.get("retry_count") or 0) + 1
            self.retry_ids.add(str(row.get("section_id") or "").strip())
        elif action == "cache_rejected":
            self.counts["cache_rejected_count"] += 1
            row["cache_rejected_count"] = int(row.get("cache_rejected_count") or 0) + 1
        elif action == "fast_draft_rejected":
            self.counts["fast_draft_rejected_count"] += 1
            row["fast_draft_rejected_count"] = int(row.get("fast_draft_rejected_count") or 0) + 1

    def emit_metrics(self, *, out_queue, section: str, section_id: str, title: str, metrics: dict[str, object], phase: str) -> None:
        enabled = bool(metrics.get("enabled"))
        checked = bool(metrics.get("checked"))
        passed = bool(metrics.get("passed", True))
        repeat_ratio = float(metrics.get("repeat_sentence_ratio") or 0.0)
        formulaic_ratio = float(metrics.get("formulaic_opening_ratio") or 0.0)
        source_overlap_ratio = float(metrics.get("source_overlap_ratio") or 0.0)
        row = self.ensure_row(section=section, section_id=section_id, title=title)
        phases = list(row.get("phases") or [])
        if phase not in phases:
            phases.append(phase)
        row["phases"] = phases
        row["latest_passed"] = passed
        row["max_repeat_sentence_ratio"] = max(float(row.get("max_repeat_sentence_ratio") or 0.0), repeat_ratio)
        row["max_formulaic_opening_ratio"] = max(float(row.get("max_formulaic_opening_ratio") or 0.0), formulaic_ratio)
        row["max_source_overlap_ratio"] = max(float(row.get("max_source_overlap_ratio") or 0.0), source_overlap_ratio)
        self.counts["event_count"] += 1
        if checked:
            row["checked_event_count"] = int(row.get("checked_event_count") or 0) + 1
            self.counts["checked_event_count"] += 1
            self.checked_ids.add(str(row.get("section_id") or "").strip())
            if passed:
                self.counts["passed_event_count"] += 1
            else:
                row["failed_event_count"] = int(row.get("failed_event_count") or 0) + 1
                self.counts["failed_event_count"] += 1
                self.failed_ids.add(str(row.get("section_id") or "").strip())
        out_queue.put({
            "event": "section_originality_hot_sample",
            "section": section,
            "section_id": section_id,
            "title": title,
            "phase": phase,
            "enabled": enabled,
            "checked": checked,
            "passed": passed,
            "sample_chars": int(metrics.get("sample_chars") or 0),
            "sample_sentence_count": int(metrics.get("sample_sentence_count") or 0),
            "repeat_sentence_ratio": repeat_ratio,
            "max_repeat_sentence_ratio": float(metrics.get("max_repeat_sentence_ratio") or 0.0),
            "formulaic_opening_ratio": formulaic_ratio,
            "max_formulaic_opening_ratio": float(metrics.get("max_formulaic_opening_ratio") or 0.0),
            "formulaic_opening_hits": list(metrics.get("formulaic_opening_hits") or []),
            "source_overlap_ratio": source_overlap_ratio,
            "max_source_overlap_ratio": float(metrics.get("max_source_overlap_ratio") or 0.0),
            "source_overlap_hits": list(metrics.get("source_overlap_hits") or []),
            "source_overlap_sentence_count": int(metrics.get("source_overlap_sentence_count") or 0),
        })

    def summary(self) -> dict[str, object]:
        checked_section_count = len(self.checked_ids)
        failed_section_count = len(self.failed_ids)
        failed_event_count = int(self.counts.get("failed_event_count") or 0)
        rewrite_section_count = len(self.rewrite_ids)
        retry_section_count = len(self.retry_ids)
        rows = list(self.rows.values())
        rows.sort(key=lambda row: (str(row.get("title") or ""), str(row.get("section_id") or "")))
        return {
            "enabled": hot_sample_enabled(),
            "event_count": int(self.counts.get("event_count") or 0),
            "checked_event_count": int(self.counts.get("checked_event_count") or 0),
            "passed_event_count": int(self.counts.get("passed_event_count") or 0),
            "failed_event_count": failed_event_count,
            "checked_section_count": checked_section_count,
            "failed_section_count": failed_section_count,
            "failed_section_ratio": round((failed_section_count / checked_section_count), 4) if checked_section_count else 0.0,
            "rewrite_count": int(self.counts.get("rewrite_count") or 0),
            "rewrite_section_count": rewrite_section_count,
            "rewrite_rate_vs_failed_sections": round((rewrite_section_count / failed_section_count), 4) if failed_section_count else 0.0,
            "retry_count": int(self.counts.get("retry_count") or 0),
            "retry_section_count": retry_section_count,
            "retry_rate_vs_failed_sections": round((retry_section_count / failed_section_count), 4) if failed_section_count else 0.0,
            "cache_rejected_count": int(self.counts.get("cache_rejected_count") or 0),
            "fast_draft_rejected_count": int(self.counts.get("fast_draft_rejected_count") or 0),
            "rows": rows[:20],
        }


def hot_sample_enabled() -> bool:
    return str(os.environ.get("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)) or default)
    except Exception:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)) or default)
    except Exception:
        return default


def has_structured_media_markers(text: str) -> bool:
    return bool(re.search(r"\[\[(?:FIGURE|TABLE)\s*:", str(text or ""), flags=re.IGNORECASE))


def collect_source_rows(*, evidence_pack: dict | None = None, reference_sources: list[dict] | None = None) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    candidates = [x for x in ((evidence_pack or {}).get("sources") or []) if isinstance(x, dict)] + [x for x in (reference_sources or []) if isinstance(x, dict)]
    for row in candidates:
        key = "|".join([str(row.get("title") or "").strip(), str(row.get("url") or "").strip(), str(row.get("summary") or row.get("abstract") or row.get("snippet") or row.get("text") or "").strip()])
        if (not key.strip()) or key in seen:
            continue
        seen.add(key)
        rows.append(dict(row))
    return rows


def evaluate_hot_sample(*, text: str, source_rows: list[dict] | None = None) -> dict[str, object]:
    enabled = hot_sample_enabled()
    sample_count = max(3, min(8, _int_env("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_SENTENCES", 5)))
    min_chars = max(120, _int_env("WRITING_AGENT_SECTION_ORIGINALITY_HOT_SAMPLE_MIN_CHARS", 220))
    sample_text = str(text or "").strip()
    if (not enabled) or (not sample_text):
        return {"enabled": enabled, "checked": False, "passed": True, "sample_text": "", "sample_chars": 0, "sample_sentence_count": 0}
    sentences = final_validator._collect_sentences(sample_text)
    excerpt = ""
    if sentences:
        excerpt_sentences = [
            str(sent or "").strip().rstrip(".!?。！？")
            for sent in sentences[:sample_count]
            if str(sent or "").strip()
        ]
        if excerpt_sentences:
            has_cjk = bool(re.search(r"[一-鿿]", "".join(excerpt_sentences)))
            delimiter = "。 " if has_cjk else ". "
            excerpt = delimiter.join(excerpt_sentences).strip()
            if excerpt:
                excerpt += "。" if has_cjk else "."
    if len(excerpt) < min_chars:
        paragraphs = [str(x).strip() for x in re.split(r"\n\s*\n+", sample_text) if str(x).strip()]
        excerpt = "\n\n".join(paragraphs[:2]).strip() if paragraphs else excerpt
    if len(excerpt) < min_chars:
        return {"enabled": True, "checked": False, "passed": True, "sample_text": excerpt, "sample_chars": len(excerpt), "sample_sentence_count": len(sentences[:sample_count])}
    repeat_ratio = final_validator._repeat_sentence_ratio(excerpt)
    formulaic_ratio, formulaic_hits = final_validator._formulaic_opening_ratio(excerpt)
    source_overlap_ratio, source_overlap_hits, overlap_sentence_count = final_validator._source_overlap_metrics(excerpt, source_rows)
    max_repeat = max(0.0, min(1.0, _float_env("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_REPEAT_RATIO", 0.12)))
    max_formulaic = max(0.0, min(1.0, _float_env("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_FORMULAIC_OPENING_RATIO", 0.34)))
    max_source_overlap = max(0.0, min(1.0, _float_env("WRITING_AGENT_SECTION_HOT_SAMPLE_MAX_SOURCE_OVERLAP_RATIO", 0.18)))
    passed = (repeat_ratio <= max_repeat) and (formulaic_ratio <= max_formulaic) and (source_overlap_ratio <= max_source_overlap)
    return {"enabled": True, "checked": True, "passed": passed, "sample_text": excerpt, "sample_chars": len(excerpt), "sample_sentence_count": len(final_validator._collect_sentences(excerpt)), "repeat_sentence_ratio": float(repeat_ratio), "max_repeat_sentence_ratio": float(max_repeat), "formulaic_opening_ratio": float(formulaic_ratio), "max_formulaic_opening_ratio": float(max_formulaic), "formulaic_opening_hits": list(formulaic_hits[:6]), "source_overlap_ratio": float(source_overlap_ratio), "max_source_overlap_ratio": float(max_source_overlap), "source_overlap_hits": list(source_overlap_hits[:6]), "source_overlap_sentence_count": int(overlap_sentence_count)}


def build_feedback(metrics: dict[str, object]) -> str:
    lines = ["Originality correction:", "- Rewrite prose in original wording while preserving facts, citations, numbers, and section meaning."]
    if float(metrics.get("source_overlap_ratio") or 0.0) > float(metrics.get("max_source_overlap_ratio") or 0.0):
        lines.append("- Paraphrase evidence instead of copying source wording verbatim.")
    if float(metrics.get("formulaic_opening_ratio") or 0.0) > float(metrics.get("max_formulaic_opening_ratio") or 0.0):
        lines.append("- Vary sentence openings; do not reuse the same opening phrase across neighboring sentences.")
    if float(metrics.get("repeat_sentence_ratio") or 0.0) > float(metrics.get("max_repeat_sentence_ratio") or 0.0):
        lines.append("- Remove repeated or near-duplicate sentences from the opening paragraphs.")
    fragments = list(metrics.get("formulaic_opening_hits") or []) + list(metrics.get("source_overlap_hits") or [])
    if fragments:
        sample = " | ".join(str(x).strip() for x in fragments[:2] if str(x).strip())
        if sample:
            lines.append(f"- Avoid repeating fragments like: {sample}")
    return "\n".join(lines).strip()


def deterministic_rewrite(text: str, metrics: dict[str, object]) -> str:
    original = str(text or "").strip()
    sentences = [str(x).strip() for x in final_validator._collect_sentences(original) if str(x).strip()]
    if not sentences:
        return original
    updated = list(sentences)
    if float(metrics.get("repeat_sentence_ratio") or 0.0) > float(metrics.get("max_repeat_sentence_ratio") or 0.0):
        seen: set[str] = set()
        deduped: list[str] = []
        for sentence in updated:
            key = final_validator._normalize_sentence(sentence)
            if (not key) or key in seen:
                continue
            seen.add(key)
            deduped.append(sentence)
        if deduped:
            updated = deduped
    if updated == sentences:
        return original
    rebuilt = ". ".join(sentence.rstrip(";:.!? ") for sentence in updated if sentence.strip()).strip()
    if rebuilt and not rebuilt.endswith((".", "!", "?", "。", "！", "？")):
        rebuilt += "."
    return rebuilt or original


def rewrite_for_originality(runtime_api, *, section_key: str, section_id: str, section_title: str, model: str, draft_text: str, metrics: dict[str, object], source_rows: list[dict] | None = None, out_queue=None) -> tuple[str, bool]:
    original = str(draft_text or "").strip()
    if (not original) or (not bool(metrics.get("checked"))) or bool(metrics.get("passed", True)) or has_structured_media_markers(original):
        return original, False
    if not str(os.environ.get("WRITING_AGENT_SECTION_ORIGINALITY_REWRITE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}:
        return original, False
    deterministic = deterministic_rewrite(original, metrics)
    if deterministic and deterministic.strip() != original:
        return deterministic.strip(), True
    hit_fragments = list(metrics.get("formulaic_opening_hits") or []) + list(metrics.get("source_overlap_hits") or [])
    source_excerpt_lines = [f"- {str((row.get('summary') or row.get('abstract') or row.get('snippet') or row.get('text') or '')).strip()[:240]}" for row in (source_rows or [])[:4] if isinstance(row, dict) and str((row.get('summary') or row.get('abstract') or row.get('snippet') or row.get('text') or '')).strip()]
    issues: list[str] = []
    if float(metrics.get("source_overlap_ratio") or 0.0) > float(metrics.get("max_source_overlap_ratio") or 0.0):
        issues.append("high source overlap")
    if float(metrics.get("formulaic_opening_ratio") or 0.0) > float(metrics.get("max_formulaic_opening_ratio") or 0.0):
        issues.append("formulaic sentence openings")
    if float(metrics.get("repeat_sentence_ratio") or 0.0) > float(metrics.get("max_repeat_sentence_ratio") or 0.0):
        issues.append("repeated sentences")
    system = "You are a constrained academic rewriting assistant. Rewrite the draft into original academic prose. Preserve factual meaning, bracket citations like [1], numbers, URLs, and any structured markers exactly. Do not invent facts, sources, experiments, or claims. Output plain text only."
    user = "<task>rewrite_for_originality</task>\n" + f"<section_title>{runtime_api._runtime_escape_prompt_text(section_title)}</section_title>\n" + f"<issues>{runtime_api._runtime_escape_prompt_text('; '.join(issues) or 'originality_hot_sample_failed')}</issues>\n" + "<constraints>\n- Keep the same section purpose and evidence boundary.\n- Keep citations, URLs, and numeric facts unchanged unless a sentence must be rephrased.\n- Vary sentence openings and remove formulaic transitions.\n- Paraphrase any source-like wording into fresh prose.\n</constraints>\n" + "<problem_fragments>\n" + ("\n".join(f"- {runtime_api._runtime_escape_prompt_text(str(x)[:200])}" for x in hit_fragments[:6]) if hit_fragments else "- none") + "\n</problem_fragments>\n" + "<source_fragments>\n" + ("\n".join(runtime_api._runtime_escape_prompt_text(line) for line in source_excerpt_lines) if source_excerpt_lines else "- none") + "\n</source_fragments>\n" + "<draft>\n" + runtime_api._runtime_escape_prompt_text(original) + "\n</draft>\nReturn the rewritten section text now."
    try:
        refiner = runtime_api.get_default_provider(model=model, timeout_s=max(20.0, runtime_api._section_timeout_s()), route_key=f"v2.refiner.rewrite_for_originality:{section_key}")
        rewritten = runtime_api._call_with_generation_slot(provider_name=runtime_api.get_provider_name(), model=model, out_queue=out_queue, section=section_key, section_id=section_id, stage="refiner", fn=lambda: refiner.chat(system=system, user=user, temperature=0.2, options={"max_tokens": 2200}))
        cleaned = str(rewritten or "").strip()
        if cleaned:
            return cleaned, True
    except Exception:
        pass
    return original, False


__all__ = [name for name in globals() if not name.startswith("__")]
