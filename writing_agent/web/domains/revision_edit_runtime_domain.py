"""Revision Edit Runtime Domain module.

Compatibility wrapper that re-exports the split revision edit domains.
"""

# Revision-edit prompt markers retained in compatibility wrapper:
# <task>plan_edit_operations</task>
# <task>rewrite_selected_text</task>
# <task>revise_full_document</task>
# <revised_document>

from __future__ import annotations

from writing_agent.web.domains import (
    revision_edit_common_domain as _common_domain,
    revision_edit_ops_domain as _ops_domain,
    revision_edit_plan_domain as _plan_domain,
    revision_selected_edit_domain as _selected_domain,
)

_EXPORT_MODULES = (
    _common_domain,
    _ops_domain,
    _plan_domain,
    _selected_domain,
)

_PUBLIC_EXPORTS = {
    name: getattr(module, name)
    for module in _EXPORT_MODULES
    for name in getattr(module, "__all__", ())
}
globals().update(_PUBLIC_EXPORTS)

__all__ = list(_PUBLIC_EXPORTS)
