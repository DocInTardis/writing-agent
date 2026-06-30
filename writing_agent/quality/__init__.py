"""Init module.

This module belongs to `writing_agent.quality` in the writing-agent codebase.
"""

from .ai_rate import AiRateConfig, AiRateWeights, estimate_ai_rate
from .plagiarism import PlagiarismConfig, PlagiarismWeights, compare_against_references, compare_text_pair

__all__ = [
    "AiRateConfig",
    "AiRateWeights",
    "PlagiarismConfig",
    "PlagiarismWeights",
    "compare_against_references",
    "compare_text_pair",
    "estimate_ai_rate",
]
