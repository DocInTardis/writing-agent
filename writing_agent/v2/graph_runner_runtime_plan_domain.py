"""Section selection and plan fallback helpers for runtime session orchestration."""

from __future__ import annotations

from writing_agent.v2 import graph_runner_runtime_plan_contract_domain as contract_domain
from writing_agent.v2 import graph_runner_runtime_plan_sections_domain as sections_domain

_base = sections_domain._base
resolve_section_plan_state = sections_domain.resolve_section_plan_state
_academic_contract_preferred_order = contract_domain._academic_contract_preferred_order
resolve_plan_contract_state = contract_domain.resolve_plan_contract_state

__all__ = [name for name in globals() if not name.startswith("__")]
