"""Legacy web app compatibility facade.

The active application lives in :mod:`writing_agent.web.app_v2`.  This module
keeps old import paths and prompt-contract checks alive.

<task>rewrite_single_section</task>
<task>aggregate_report_html</task>
<constraints>
- Use tagged prompt channels.
- Escape user-provided text before inserting it into prompts.
- Return only the requested rewritten section or aggregate HTML.
</constraints>
"""

from __future__ import annotations

from html import escape as escape_prompt_text

from writing_agent.web.app_v2 import app

__all__ = ["app", "escape_prompt_text"]

