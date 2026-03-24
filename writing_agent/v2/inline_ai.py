"""
Inline AI Operations Module

Provides context-aware inline AI operations for document editing:
- Continue writing from cursor position
- Improve selected text
- Summarize paragraphs
- Expand bullet points
- Change tone/style
"""

# Prompt-contract markers retained for inline AI guarded chat calls:
# <task>inline_ai_operation</task>
# <constraints>

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging
import json
import re

from writing_agent.llm import OllamaClient, get_ollama_settings
from writing_agent.v2.inline_ai_guard_domain import (
    _build_guarded_prompt as _inline_build_guarded_prompt,
    _chat_guarded as _inline_chat_guarded,
    _chat_proxy as _inline_chat_proxy,
    _clamp_int as _inline_clamp_int,
    _dynamic_window_chars as _inline_dynamic_window_chars,
    _extract_output_text as _inline_extract_output_text,
    _head_chars as _inline_head_chars,
    _strip_fences as _inline_strip_fences,
    _tail_chars as _inline_tail_chars,
    _xml_escape as _inline_xml_escape,
)
from writing_agent.v2.inline_ai_ops_domain import (
    _ask_ai as _inline_ask_ai,
    _build_continue_prompt as _inline_build_continue_prompt,
    _build_operation_prompt as _inline_build_operation_prompt,
    _change_tone as _inline_change_tone,
    _continue_writing as _inline_continue_writing,
    _elaborate_text as _inline_elaborate_text,
    _explain_text as _inline_explain_text,
    _expand_text as _inline_expand_text,
    _get_improvement_focus_desc as _inline_get_improvement_focus_desc,
    _get_system_prompt as _inline_get_system_prompt,
    _get_temperature as _inline_get_temperature,
    _get_tone_description as _inline_get_tone_description,
    _improve_text as _inline_improve_text,
    _rephrase_text as _inline_rephrase_text,
    _simplify_text as _inline_simplify_text,
    _summarize_text as _inline_summarize_text,
    _translate_text as _inline_translate_text,
)

logger = logging.getLogger(__name__)


class InlineOperation(str, Enum):
    """Types of inline AI operations"""
    CONTINUE = "continue"
    IMPROVE = "improve"
    SUMMARIZE = "summarize"
    EXPAND = "expand"
    CHANGE_TONE = "change_tone"
    SIMPLIFY = "simplify"
    ELABORATE = "elaborate"
    REPHRASE = "rephrase"
    ASK_AI = "ask_ai"  # New: Ask AI about selected text
    EXPLAIN = "explain"  # New: Explain selected text
    TRANSLATE = "translate"  # New: Translate text


class ToneStyle(str, Enum):
    """Writing tone styles"""
    FORMAL = "formal"
    CASUAL = "casual"
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    CREATIVE = "creative"
    PROFESSIONAL = "professional"


@dataclass
class InlineContext:
    """Context for inline AI operations"""
    selected_text: str
    before_text: str  # Text before selection
    after_text: str   # Text after selection
    document_title: str
    section_title: Optional[str] = None
    document_type: Optional[str] = None  # "research", "report", "article", etc.
    pretrimmed: bool = False


@dataclass
class InlineResult:
    """Result of inline AI operation"""
    success: bool
    generated_text: str
    operation: InlineOperation
    error: Optional[str] = None


class InlineAIEngine:
    """
    Handles context-aware inline AI operations

    This engine provides intelligent text operations that understand
    the document context and maintain consistency with the existing content.
    """

    def __init__(self):
        self.settings = get_ollama_settings()
        self.client = OllamaClient(
            base_url=self.settings.base_url,
            model=self.settings.model,
            timeout_s=self.settings.timeout_s
        )
        self._raw_chat = self.client.chat
        self._active_operation: InlineOperation | None = None
        self._active_context: InlineContext | None = None
        # Route all legacy direct `client.chat(...)` calls through a guarded proxy.
        self.client.chat = self._chat_proxy  # type: ignore[method-assign]

    _JSON_OUTPUT_OPS = {
        InlineOperation.CONTINUE,
        InlineOperation.IMPROVE,
        InlineOperation.SUMMARIZE,
        InlineOperation.EXPAND,
        InlineOperation.CHANGE_TONE,
        InlineOperation.SIMPLIFY,
        InlineOperation.ELABORATE,
        InlineOperation.REPHRASE,
        InlineOperation.ASK_AI,
        InlineOperation.EXPLAIN,
        InlineOperation.TRANSLATE,
    }

    _STRICT_REWRITE_OPS = {
        InlineOperation.IMPROVE,
        InlineOperation.CHANGE_TONE,
        InlineOperation.SIMPLIFY,
        InlineOperation.REPHRASE,
        InlineOperation.TRANSLATE,
    }

    # Guard/prompt helpers are attached from inline_ai_guard_domain below.

    async def execute_operation(
        self,
        operation: InlineOperation,
        context: InlineContext,
        **kwargs
    ) -> InlineResult:
        """
        Execute an inline AI operation

        Args:
            operation: Type of operation to perform
            context: Document context
            **kwargs: Additional operation-specific parameters

        Returns:
            InlineResult with generated text
        """
        try:
            self._active_operation = operation
            self._active_context = context
            try:
                if operation == InlineOperation.CONTINUE:
                    result = await self._continue_writing(context, **kwargs)
                elif operation == InlineOperation.IMPROVE:
                    result = await self._improve_text(context, **kwargs)
                elif operation == InlineOperation.SUMMARIZE:
                    result = await self._summarize_text(context, **kwargs)
                elif operation == InlineOperation.EXPAND:
                    result = await self._expand_text(context, **kwargs)
                elif operation == InlineOperation.CHANGE_TONE:
                    result = await self._change_tone(context, **kwargs)
                elif operation == InlineOperation.SIMPLIFY:
                    result = await self._simplify_text(context, **kwargs)
                elif operation == InlineOperation.ELABORATE:
                    result = await self._elaborate_text(context, **kwargs)
                elif operation == InlineOperation.REPHRASE:
                    result = await self._rephrase_text(context, **kwargs)
                elif operation == InlineOperation.ASK_AI:
                    result = await self._ask_ai(context, **kwargs)
                elif operation == InlineOperation.EXPLAIN:
                    result = await self._explain_text(context, **kwargs)
                elif operation == InlineOperation.TRANSLATE:
                    result = await self._translate_text(context, **kwargs)
                else:
                    return InlineResult(
                        success=False,
                        generated_text="",
                        operation=operation,
                        error=f"Unknown operation: {operation}"
                    )
            finally:
                self._active_operation = None
                self._active_context = None

            return InlineResult(
                success=True,
                generated_text=result,
                operation=operation
            )

        except Exception as e:
            logger.error(f"Inline operation failed: {e}", exc_info=True)
            return InlineResult(
                success=False,
                generated_text="",
                operation=operation,
                error=str(e)
            )

    async def execute_operation_stream(
        self,
        operation: InlineOperation,
        context: InlineContext,
        **kwargs
    ):
        """
        Execute an inline AI operation with streaming output

        Args:
            operation: Type of operation to perform
            context: Document context
            **kwargs: Additional operation-specific parameters

        Yields:
            dict: Streaming events with 'type' and 'content' keys
        """
        try:
            # Build the prompt based on operation
            prompt = self._build_operation_prompt(operation, context, **kwargs)
            system_prompt = self._get_system_prompt(operation)

            # Stream the response
            yield {"type": "start", "operation": operation.value}

            accumulated_text = ""
            chunk_buffer = ""

            # Note: This is a simplified streaming implementation
            # In a real implementation, you would use the LLM's streaming API
            try:
                # For now, we'll simulate streaming by chunking the response
                result = self._chat_guarded(
                    operation=operation,
                    context=context,
                    system=system_prompt,
                    user=prompt,
                    temperature=self._get_temperature(operation),
                )

                # Simulate streaming by yielding chunks
                words = result.split()
                for i, word in enumerate(words):
                    chunk_buffer += word + " "
                    accumulated_text += word + " "

                    # Yield every few words
                    if (i + 1) % 3 == 0 or i == len(words) - 1:
                        yield {
                            "type": "delta",
                            "content": chunk_buffer.strip(),
                            "accumulated": accumulated_text.strip()
                        }
                        chunk_buffer = ""

                yield {
                    "type": "done",
                    "content": accumulated_text.strip(),
                    "operation": operation.value
                }

            except Exception as e:
                yield {
                    "type": "error",
                    "error": str(e),
                    "operation": operation.value
                }

        except Exception as e:
            logger.error(f"Streaming operation failed: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": str(e),
                "operation": operation.value if operation else "unknown"
            }

    # Operation prompts and handlers are attached from inline_ai_ops_domain below.

InlineAIEngine._clamp_int = staticmethod(_inline_clamp_int)
InlineAIEngine._dynamic_window_chars = _inline_dynamic_window_chars
InlineAIEngine._tail_chars = staticmethod(_inline_tail_chars)
InlineAIEngine._head_chars = staticmethod(_inline_head_chars)
InlineAIEngine._strip_fences = staticmethod(_inline_strip_fences)
InlineAIEngine._xml_escape = staticmethod(_inline_xml_escape)
InlineAIEngine._extract_output_text = _inline_extract_output_text
InlineAIEngine._build_guarded_prompt = _inline_build_guarded_prompt
InlineAIEngine._chat_guarded = _inline_chat_guarded
InlineAIEngine._chat_proxy = _inline_chat_proxy

InlineAIEngine._build_operation_prompt = _inline_build_operation_prompt
InlineAIEngine._get_system_prompt = _inline_get_system_prompt
InlineAIEngine._get_temperature = _inline_get_temperature
InlineAIEngine._continue_writing = _inline_continue_writing
InlineAIEngine._improve_text = _inline_improve_text
InlineAIEngine._summarize_text = _inline_summarize_text
InlineAIEngine._expand_text = _inline_expand_text
InlineAIEngine._change_tone = _inline_change_tone
InlineAIEngine._simplify_text = _inline_simplify_text
InlineAIEngine._elaborate_text = _inline_elaborate_text
InlineAIEngine._rephrase_text = _inline_rephrase_text
InlineAIEngine._ask_ai = _inline_ask_ai
InlineAIEngine._explain_text = _inline_explain_text
InlineAIEngine._translate_text = _inline_translate_text
InlineAIEngine._build_continue_prompt = _inline_build_continue_prompt
InlineAIEngine._get_improvement_focus_desc = _inline_get_improvement_focus_desc
InlineAIEngine._get_tone_description = _inline_get_tone_description

# Convenience functions for common operations

async def continue_writing(
    selected_text: str,
    before_text: str = "",
    after_text: str = "",
    target_words: int = 200,
    **kwargs
) -> str:
    """
    Convenience function to continue writing

    Args:
        selected_text: Currently selected text (usually empty for continue)
        before_text: Text before cursor
        after_text: Text after cursor
        target_words: Target number of words

    Returns:
        Generated continuation
    """
    engine = InlineAIEngine()
    context = InlineContext(
        selected_text=selected_text,
        before_text=before_text,
        after_text=after_text,
        document_title=kwargs.get("document_title", ""),
        section_title=kwargs.get("section_title"),
        document_type=kwargs.get("document_type")
    )

    result = await engine.execute_operation(
        InlineOperation.CONTINUE,
        context,
        target_words=target_words
    )

    if result.success:
        return result.generated_text
    else:
        raise Exception(result.error or "Continue writing failed")


async def improve_text(
    selected_text: str,
    focus: str = "general",
    **kwargs
) -> str:
    """
    Convenience function to improve text

    Args:
        selected_text: Text to improve
        focus: Improvement focus

    Returns:
        Improved text
    """
    engine = InlineAIEngine()
    context = InlineContext(
        selected_text=selected_text,
        before_text=kwargs.get("before_text", ""),
        after_text=kwargs.get("after_text", ""),
        document_title=kwargs.get("document_title", "")
    )

    result = await engine.execute_operation(
        InlineOperation.IMPROVE,
        context,
        focus=focus
    )

    if result.success:
        return result.generated_text
    else:
        raise Exception(result.error or "Improve text failed")


