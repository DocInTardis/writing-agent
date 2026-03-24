"""Inline AI operation prompt and handler helpers."""

# Prompt-contract markers retained for inline AI operation builders:
# <task>inline_ai_operation</task>
# <constraints>

from __future__ import annotations


def _inline_ai_module():
    from writing_agent.v2 import inline_ai as _inline_ai

    return _inline_ai


def _build_operation_prompt(self, operation, context, **kwargs) -> str:
    inline_ai = _inline_ai_module()
    if operation == inline_ai.InlineOperation.ASK_AI:
        question = str(kwargs.get("question") or "Analyze the selected text.")
        return (
            "Answer the question about the selected text.\n\n"
            f"Selected text:\n{context.selected_text}\n\n"
            f"Question:\n{question}\n\n"
            "Answer clearly and directly."
        )

    if operation == inline_ai.InlineOperation.EXPLAIN:
        detail_level = str(kwargs.get("detail_level") or "medium")
        detail_desc = {"brief": "brief", "medium": "medium-detail", "detailed": "detailed"}.get(
            detail_level,
            "medium-detail",
        )
        return (
            f"Explain the selected text in a {detail_desc} way.\n\n"
            f"Selected text:\n{context.selected_text}\n\n"
            "Include key ideas, important terms, and practical interpretation."
        )

    if operation == inline_ai.InlineOperation.IMPROVE:
        focus = str(kwargs.get("focus") or "general")
        focus_desc = self._get_improvement_focus_desc(focus)
        return (
            f"Improve the selected text for {focus_desc}.\n\n"
            f"Selected text:\n{context.selected_text}\n\n"
            "Keep original intent and facts."
        )

    return f"Process this selected text:\n{context.selected_text}"


def _get_system_prompt(self, operation) -> str:
    inline_ai = _inline_ai_module()
    prompts = {
        inline_ai.InlineOperation.ASK_AI: "You are a precise text analysis assistant.",
        inline_ai.InlineOperation.EXPLAIN: "You are a clear and educational explainer.",
        inline_ai.InlineOperation.IMPROVE: "You are a professional writing editor.",
        inline_ai.InlineOperation.CONTINUE: "You are a professional writing assistant that continues content coherently.",
        inline_ai.InlineOperation.SUMMARIZE: "You are a concise summarization assistant.",
    }
    return prompts.get(operation, "You are a professional writing assistant.")


def _get_temperature(self, operation) -> float:
    inline_ai = _inline_ai_module()
    temperatures = {
        inline_ai.InlineOperation.ASK_AI: 0.5,
        inline_ai.InlineOperation.EXPLAIN: 0.5,
        inline_ai.InlineOperation.IMPROVE: 0.5,
        inline_ai.InlineOperation.CONTINUE: 0.7,
        inline_ai.InlineOperation.SUMMARIZE: 0.3,
        inline_ai.InlineOperation.TRANSLATE: 0.3,
    }
    return temperatures.get(operation, 0.6)


async def _continue_writing(self, context, target_words: int = 200) -> str:
    prompt = self._build_continue_prompt(context, target_words)
    result = self.client.chat(
        system="You are a writing continuation assistant.",
        user=prompt,
        temperature=0.7,
        options={"num_predict": min(800, target_words * 4)},
    )
    return result.strip()


async def _improve_text(self, context, focus: str = "general") -> str:
    prompt = (
        f"Improve the selected text for {self._get_improvement_focus_desc(focus)}.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        "Keep the same intent and improve readability."
    )
    result = self.client.chat(
        system="You are a professional text editor.",
        user=prompt,
        temperature=0.5,
    )
    return result.strip()


async def _summarize_text(self, context, max_sentences: int = 3) -> str:
    prompt = (
        f"Summarize the selected text in up to {max_sentences} sentences.\n\n"
        f"Selected text:\n{context.selected_text}"
    )
    result = self.client.chat(
        system="You are a concise summarization assistant.",
        user=prompt,
        temperature=0.3,
    )
    return result.strip()


async def _expand_text(self, context, expansion_ratio: float = 2.0) -> str:
    current_words = len(context.selected_text.split())
    target_words = max(50, int(current_words * expansion_ratio))
    prompt = (
        f"Expand the selected text with useful details to about {target_words} words.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        "Keep the same core claims."
    )
    result = self.client.chat(
        system="You are a detail-oriented writing assistant.",
        user=prompt,
        temperature=0.6,
        options={"num_predict": target_words * 4},
    )
    return result.strip()


async def _change_tone(self, context, target_tone) -> str:
    tone_desc = self._get_tone_description(target_tone)
    prompt = (
        f"Rewrite the selected text in a {tone_desc} tone.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        "Keep meaning and key information unchanged."
    )
    result = self.client.chat(
        system=f"You are a style transfer editor specialized in {tone_desc} writing.",
        user=prompt,
        temperature=0.6,
    )
    return result.strip()


async def _simplify_text(self, context) -> str:
    prompt = (
        "Simplify the selected text for readability.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        "Use simpler words and shorter sentences while preserving key facts."
    )
    result = self.client.chat(
        system="You are a plain-language editor.",
        user=prompt,
        temperature=0.5,
    )
    return result.strip()


async def _elaborate_text(self, context) -> str:
    prompt = (
        "Elaborate on the selected text with clearer explanation and examples.\n\n"
        f"Selected text:\n{context.selected_text}"
    )
    result = self.client.chat(
        system="You are an explanatory writing assistant.",
        user=prompt,
        temperature=0.6,
    )
    return result.strip()


async def _rephrase_text(self, context) -> str:
    prompt = (
        "Rephrase the selected text with different wording.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        "Keep the original meaning exactly."
    )
    result = self.client.chat(
        system="You are a paraphrasing assistant.",
        user=prompt,
        temperature=0.7,
    )
    return result.strip()


async def _ask_ai(self, context, question: str = "") -> str:
    if not question:
        question = "Analyze this selected text."

    prompt = (
        "Answer the question about the selected text.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        f"Question:\n{question}"
    )
    result = self.client.chat(
        system="You are a text analysis assistant.",
        user=prompt,
        temperature=0.5,
    )
    return result.strip()


async def _explain_text(self, context, detail_level: str = "medium") -> str:
    detail_desc = {
        "brief": "brief",
        "medium": "medium-detail",
        "detailed": "detailed",
    }.get(detail_level, "medium-detail")

    prompt = (
        f"Explain the selected text in a {detail_desc} way.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        "Cover key ideas, terms, and implications."
    )
    result = self.client.chat(
        system="You are a clear explanation assistant.",
        user=prompt,
        temperature=0.5,
    )
    return result.strip()


async def _translate_text(self, context, target_language: str = "en") -> str:
    language_names = {
        "en": "English",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "ru": "Russian",
    }

    target_lang_name = language_names.get(target_language, target_language)
    prompt = (
        f"Translate the selected text to {target_lang_name}.\n\n"
        f"Selected text:\n{context.selected_text}\n\n"
        "Preserve meaning, terminology, and natural phrasing."
    )
    result = self.client.chat(
        system=f"You are a professional translator to {target_lang_name}.",
        user=prompt,
        temperature=0.3,
    )
    return result.strip()


def _build_continue_prompt(self, context, target_words: int) -> str:
    prompt_parts = []

    if context.document_title:
        prompt_parts.append(f"Document title: {context.document_title}")

    if context.section_title:
        prompt_parts.append(f"Current section: {context.section_title}")

    if context.before_text:
        before_preview = context.before_text[-500:] if len(context.before_text) > 500 else context.before_text
        prompt_parts.append(f"\nPrevious context:\n{before_preview}")

    prompt_parts.append(f"\nContinue writing about {target_words} words. Requirements:")
    prompt_parts.append("1. Keep style consistent with previous context")
    prompt_parts.append("2. Maintain logical continuity")
    prompt_parts.append("3. Provide concrete and useful content")
    prompt_parts.append("4. Keep language clear and fluent")

    if context.after_text:
        after_preview = context.after_text[:200] if len(context.after_text) > 200 else context.after_text
        prompt_parts.append(f"\nUpcoming context preview:\n{after_preview}")
        prompt_parts.append("\nEnsure smooth transition into the upcoming context.")

    prompt_parts.append("\nContinuation:")
    return "\n".join(prompt_parts)


def _get_improvement_focus_desc(self, focus: str) -> str:
    focus_map = {
        "grammar": "grammar and correctness",
        "clarity": "clarity and readability",
        "style": "style and expressiveness",
        "general": "overall quality",
    }
    return focus_map.get(focus, "overall quality")


def _get_tone_description(self, tone) -> str:
    inline_ai = _inline_ai_module()
    tone_map = {
        inline_ai.ToneStyle.FORMAL: "formal",
        inline_ai.ToneStyle.CASUAL: "casual",
        inline_ai.ToneStyle.ACADEMIC: "academic",
        inline_ai.ToneStyle.TECHNICAL: "technical",
        inline_ai.ToneStyle.CREATIVE: "creative",
        inline_ai.ToneStyle.PROFESSIONAL: "professional",
    }
    return tone_map.get(tone, "professional")
