"""Init module.

This module belongs to `writing_agent.quality` in the writing-agent codebase.
"""

from .plagiarism import compare_against_references, compare_text_pair
from .ai_rate import estimate_ai_rate

__all__ = ["compare_against_references", "compare_text_pair", "estimate_ai_rate"]
