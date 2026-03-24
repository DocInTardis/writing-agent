"""Revision Edit Runtime Domain module.

Compatibility wrapper that re-exports the split revision edit domains.
"""

# Revision-edit prompt markers retained in compatibility wrapper:
# <task>plan_edit_operations</task>
# <task>rewrite_selected_text</task>
# <task>revise_full_document</task>
# <revised_document>

from __future__ import annotations

from writing_agent.web.domains.revision_edit_common_domain import *
from writing_agent.web.domains.revision_edit_ops_domain import *
from writing_agent.web.domains.revision_edit_plan_domain import *
from writing_agent.web.domains.revision_selected_edit_domain import *

from writing_agent.web.domains.revision_edit_common_domain import __all__ as _common_all
from writing_agent.web.domains.revision_edit_ops_domain import __all__ as _ops_all
from writing_agent.web.domains.revision_edit_plan_domain import __all__ as _plan_all
from writing_agent.web.domains.revision_selected_edit_domain import __all__ as _selected_all

__all__ = list(dict.fromkeys(list(_common_all) + list(_ops_all) + list(_plan_all) + list(_selected_all)))
