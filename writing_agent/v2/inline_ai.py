"""
Inline AI Operations Module

Provides context-aware inline AI operations for document editing:
- Continue writing from cursor position
- Improve selected text
- Summarize paragraphs
- Expand bullet points
- Change tone/style
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

from writing_agent.llm import OllamaClient, get_ollama_settings

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
                result = self.client.chat(
                    system=system_prompt,
                    user=prompt,
                    temperature=self._get_temperature(operation)
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

    def _build_operation_prompt(
        self,
        operation: InlineOperation,
        context: InlineContext,
        **kwargs
    ) -> str:
        """Build prompt for the given operation"""
        if operation == InlineOperation.ASK_AI:
            question = kwargs.get("question", "请分析这段文本的内容。")
            return f"""请回答关于以下文本的问题。

文本内容：
{context.selected_text}

问题：{question}

请提供详细、准确的回答："""

        elif operation == InlineOperation.EXPLAIN:
            detail_level = kwargs.get("detail_level", "medium")
            detail_desc = {"brief": "简要", "medium": "适中", "detailed": "详细"}.get(detail_level, "适中")
            return f"""请{detail_desc}地解释以下文本的含义：

文本：
{context.selected_text}

解释要求：
1. 说明核心概念
2. 解释关键术语
3. 提供必要的背景信息
4. 使用易懂的语言

解释："""

        elif operation == InlineOperation.IMPROVE:
            focus = kwargs.get("focus", "general")
            focus_desc = self._get_improvement_focus_desc(focus)
            return f"""请改进以下文本，使其更加{focus_desc}。

原文：
{context.selected_text}

要求：
1. 保持原意不变
2. 改进语言表达
3. 增强可读性
4. 保持与文档整体风格一致

改进后的文本："""

        # Add more operation-specific prompts as needed
        else:
            return f"处理文本：{context.selected_text}"

    def _get_system_prompt(self, operation: InlineOperation) -> str:
        """Get system prompt for the given operation"""
        prompts = {
            InlineOperation.ASK_AI: "你是专业的文本分析助手，擅长回答关于文本内容的问题。",
            InlineOperation.EXPLAIN: "你是专业的文本解释专家，擅长用清晰易懂的方式解释复杂内容。",
            InlineOperation.IMPROVE: "你是专业的文本编辑，擅长改进文本质量。",
            InlineOperation.CONTINUE: "你是专业的写作助手，擅长根据上下文继续写作，保持风格和逻辑的连贯性。",
            InlineOperation.SUMMARIZE: "你是专业的内容总结专家，擅长提炼核心要点。",
        }
        return prompts.get(operation, "你是专业的写作助手。")

    def _get_temperature(self, operation: InlineOperation) -> float:
        """Get temperature for the given operation"""
        temperatures = {
            InlineOperation.ASK_AI: 0.5,
            InlineOperation.EXPLAIN: 0.5,
            InlineOperation.IMPROVE: 0.5,
            InlineOperation.CONTINUE: 0.7,
            InlineOperation.SUMMARIZE: 0.3,
            InlineOperation.TRANSLATE: 0.3,
        }
        return temperatures.get(operation, 0.6)

    async def _continue_writing(
        self,
        context: InlineContext,
        target_words: int = 200
    ) -> str:
        """
        Continue writing from the current position

        Args:
            context: Document context
            target_words: Target number of words to generate

        Returns:
            Generated continuation text
        """
        # Build context-aware prompt
        prompt = self._build_continue_prompt(context, target_words)

        # Generate continuation
        result = self.client.chat(
            system="你是专业的写作助手，擅长根据上下文继续写作，保持风格和逻辑的连贯性。",
            user=prompt,
            temperature=0.7,
            options={"num_predict": min(800, target_words * 4)}
        )

        return result.strip()

    async def _improve_text(
        self,
        context: InlineContext,
        focus: str = "general"
    ) -> str:
        """
        Improve selected text

        Args:
            context: Document context
            focus: Improvement focus ("grammar", "clarity", "style", "general")

        Returns:
            Improved text
        """
        prompt = f"""请改进以下文本，使其更加{self._get_improvement_focus_desc(focus)}。

原文：
{context.selected_text}

要求：
1. 保持原意不变
2. 改进语言表达
3. 增强可读性
4. 保持与文档整体风格一致

改进后的文本："""

        result = self.client.chat(
            system="你是专业的文本编辑，擅长改进文本质量。",
            user=prompt,
            temperature=0.5
        )

        return result.strip()

    async def _summarize_text(
        self,
        context: InlineContext,
        max_sentences: int = 3
    ) -> str:
        """
        Summarize selected text

        Args:
            context: Document context
            max_sentences: Maximum number of sentences in summary

        Returns:
            Summary text
        """
        prompt = f"""请用{max_sentences}句话总结以下内容的核心要点：

{context.selected_text}

总结："""

        result = self.client.chat(
            system="你是专业的内容总结专家，擅长提炼核心要点。",
            user=prompt,
            temperature=0.3
        )

        return result.strip()

    async def _expand_text(
        self,
        context: InlineContext,
        expansion_ratio: float = 2.0
    ) -> str:
        """
        Expand selected text with more details

        Args:
            context: Document context
            expansion_ratio: Target expansion ratio (2.0 = double the length)

        Returns:
            Expanded text
        """
        current_words = len(context.selected_text.split())
        target_words = int(current_words * expansion_ratio)

        prompt = f"""请扩展以下内容，添加更多细节、例子和解释，目标字数约{target_words}字：

原文：
{context.selected_text}

扩展要求：
1. 保持核心观点不变
2. 添加具体例子和细节
3. 增强论证深度
4. 保持逻辑连贯

扩展后的文本："""

        result = self.client.chat(
            system="你是专业的内容扩展专家，擅长丰富文本内容。",
            user=prompt,
            temperature=0.6,
            options={"num_predict": target_words * 4}
        )

        return result.strip()

    async def _change_tone(
        self,
        context: InlineContext,
        target_tone: ToneStyle
    ) -> str:
        """
        Change the tone/style of selected text

        Args:
            context: Document context
            target_tone: Target tone style

        Returns:
            Text with changed tone
        """
        tone_desc = self._get_tone_description(target_tone)

        prompt = f"""请将以下文本改写为{tone_desc}风格：

原文：
{context.selected_text}

要求：
1. 保持原意和信息完整
2. 调整语言风格和用词
3. 适应目标语境

改写后的文本："""

        result = self.client.chat(
            system=f"你是专业的文本改写专家，擅长调整文本风格为{tone_desc}。",
            user=prompt,
            temperature=0.6
        )

        return result.strip()

    async def _simplify_text(
        self,
        context: InlineContext
    ) -> str:
        """
        Simplify complex text

        Args:
            context: Document context

        Returns:
            Simplified text
        """
        prompt = f"""请将以下复杂文本简化，使其更易理解：

原文：
{context.selected_text}

简化要求：
1. 使用简单词汇
2. 缩短句子长度
3. 保持核心信息
4. 提高可读性

简化后的文本："""

        result = self.client.chat(
            system="你是专业的文本简化专家，擅长将复杂内容转化为易懂的表达。",
            user=prompt,
            temperature=0.5
        )

        return result.strip()

    async def _elaborate_text(
        self,
        context: InlineContext
    ) -> str:
        """
        Add more detailed explanation

        Args:
            context: Document context

        Returns:
            Elaborated text
        """
        prompt = f"""请对以下内容进行详细阐述，添加更多解释和说明：

原文：
{context.selected_text}

阐述要求：
1. 解释关键概念
2. 提供背景信息
3. 添加具体例子
4. 增强理解深度

阐述后的文本："""

        result = self.client.chat(
            system="你是专业的内容阐述专家，擅长深入解释和说明。",
            user=prompt,
            temperature=0.6
        )

        return result.strip()

    async def _rephrase_text(
        self,
        context: InlineContext
    ) -> str:
        """
        Rephrase text with different wording

        Args:
            context: Document context

        Returns:
            Rephrased text
        """
        prompt = f"""请用不同的表达方式重新表述以下内容：

原文：
{context.selected_text}

改写要求：
1. 保持原意完全一致
2. 使用不同的词汇和句式
3. 保持自然流畅
4. 避免重复原文用词

改写后的文本："""

        result = self.client.chat(
            system="你是专业的文本改写专家，擅长用不同方式表达相同内容。",
            user=prompt,
            temperature=0.7
        )

        return result.strip()

    async def _ask_ai(
        self,
        context: InlineContext,
        question: str = ""
    ) -> str:
        """
        Ask AI a question about selected text

        Args:
            context: Document context
            question: User's question

        Returns:
            AI's answer
        """
        if not question:
            question = "请分析这段文本的内容。"

        prompt = f"""请回答关于以下文本的问题。

文本内容：
{context.selected_text}

问题：{question}

请提供详细、准确的回答："""

        result = self.client.chat(
            system="你是专业的文本分析助手，擅长回答关于文本内容的问题。",
            user=prompt,
            temperature=0.5
        )

        return result.strip()

    async def _explain_text(
        self,
        context: InlineContext,
        detail_level: str = "medium"
    ) -> str:
        """
        Explain selected text

        Args:
            context: Document context
            detail_level: Level of detail ("brief", "medium", "detailed")

        Returns:
            Explanation
        """
        detail_desc = {
            "brief": "简要",
            "medium": "适中",
            "detailed": "详细"
        }.get(detail_level, "适中")

        prompt = f"""请{detail_desc}地解释以下文本的含义：

文本：
{context.selected_text}

解释要求：
1. 说明核心概念
2. 解释关键术语
3. 提供必要的背景信息
4. 使用易懂的语言

解释："""

        result = self.client.chat(
            system="你是专业的文本解释专家，擅长用清晰易懂的方式解释复杂内容。",
            user=prompt,
            temperature=0.5
        )

        return result.strip()

    async def _translate_text(
        self,
        context: InlineContext,
        target_language: str = "en"
    ) -> str:
        """
        Translate selected text

        Args:
            context: Document context
            target_language: Target language code ("en", "zh", "ja", "ko", etc.)

        Returns:
            Translated text
        """
        language_names = {
            "en": "英语",
            "zh": "中文",
            "ja": "日语",
            "ko": "韩语",
            "fr": "法语",
            "de": "德语",
            "es": "西班牙语",
            "ru": "俄语"
        }

        target_lang_name = language_names.get(target_language, target_language)

        prompt = f"""请将以下文本翻译成{target_lang_name}：

原文：
{context.selected_text}

翻译要求：
1. 准确传达原意
2. 符合目标语言习惯
3. 保持专业术语准确性
4. 自然流畅

翻译："""

        result = self.client.chat(
            system=f"你是专业的翻译专家，擅长将文本翻译成{target_lang_name}。",
            user=prompt,
            temperature=0.3
        )

        return result.strip()

    def _build_continue_prompt(
        self,
        context: InlineContext,
        target_words: int
    ) -> str:
        """Build prompt for continue writing operation"""
        prompt_parts = []

        # Add document context
        if context.document_title:
            prompt_parts.append(f"文档标题：{context.document_title}")

        if context.section_title:
            prompt_parts.append(f"当前章节：{context.section_title}")

        # Add before context
        if context.before_text:
            before_preview = context.before_text[-500:] if len(context.before_text) > 500 else context.before_text
            prompt_parts.append(f"\n前文内容：\n{before_preview}")

        # Add instruction
        prompt_parts.append(f"\n请继续写作，生成约{target_words}字的内容。要求：")
        prompt_parts.append("1. 保持与前文风格一致")
        prompt_parts.append("2. 逻辑连贯，自然过渡")
        prompt_parts.append("3. 内容充实，有深度")
        prompt_parts.append("4. 语言流畅，表达清晰")

        if context.after_text:
            after_preview = context.after_text[:200] if len(context.after_text) > 200 else context.after_text
            prompt_parts.append(f"\n后文预览：\n{after_preview}")
            prompt_parts.append("\n注意：生成的内容需要与后文自然衔接。")

        prompt_parts.append("\n继续写作：")

        return "\n".join(prompt_parts)

    def _get_improvement_focus_desc(self, focus: str) -> str:
        """Get description for improvement focus"""
        focus_map = {
            "grammar": "语法正确、规范",
            "clarity": "清晰明了、易懂",
            "style": "文采优美、有风格",
            "general": "整体质量更高"
        }
        return focus_map.get(focus, "更好")

    def _get_tone_description(self, tone: ToneStyle) -> str:
        """Get description for tone style"""
        tone_map = {
            ToneStyle.FORMAL: "正式、庄重",
            ToneStyle.CASUAL: "轻松、随意",
            ToneStyle.ACADEMIC: "学术、严谨",
            ToneStyle.TECHNICAL: "技术、专业",
            ToneStyle.CREATIVE: "创意、生动",
            ToneStyle.PROFESSIONAL: "专业、得体"
        }
        return tone_map.get(tone, "专业")


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
