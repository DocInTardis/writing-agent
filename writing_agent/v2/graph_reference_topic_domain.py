"""Topic relevance and ranking helpers for reference sources."""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from writing_agent.v2 import graph_reference_plan_domain as reference_plan_domain

_reference_query_tokens = reference_plan_domain._reference_query_tokens
_topic_tokens = reference_plan_domain._topic_tokens
normalize_reference_query = reference_plan_domain.normalize_reference_query


def _expanded_query_tokens(query: str) -> set[str]:
    query = normalize_reference_query(query)
    tokens = _topic_tokens(query)
    expanded: set[str] = set(tokens)
    mapping: dict[str, list[str]] = {
        "区块链": ['blockchain', 'distributed ledger', 'dlp', 'smart contract'],
        "农村": ['rural', 'agricultural', 'village'],
        "社会化服务": ['service', 'public service', 'social service'],
        "数据治理": ['data governance', 'governance', 'data management'],
        "绿色低碳": ['low carbon', 'green transition', 'carbon'],
        "数字化": ['digital', 'digitization', 'digitalization'],
        "供应链": ['supply chain', 'logistics'],
        "智能写作": ['ai writing', 'academic writing', 'writing assistant'],
        "写作代理": ['writing agent', 'agentic writing', 'multi-agent', 'writing assistant'],
        "学术写作": ['academic writing', 'scholarly writing', 'scientific writing'],
        "高校科研": ['higher education', 'academic research', 'university research', 'research workflow'],
        "科研工作流": ['research workflow', 'scholarly workflow'],
        "系统架构": ['system architecture', 'software architecture'],
        "需求分析": ['requirements analysis', 'requirement engineering'],
        "检索增强生成": ['retrieval augmented generation', 'rag'],
        "引文核验": ['citation verification', 'citation checking', 'reference validation'],
        "文献管理": ['reference management', 'citation management'],
        "多代理": ['multi-agent', 'agentic workflow'],
    }
    joined = " ".join(tokens)
    for key, aliases in mapping.items():
        if key in joined:
            for alias in aliases:
                expanded.add(alias.lower())
                for sub in _topic_tokens(alias):
                    expanded.add(sub)
    if "服务" in joined:
        expanded.add("service")
    if "管理" in joined:
        expanded.add("management")
    if "评估" in joined:
        expanded.add("evaluation")
    if "写作" in joined:
        expanded.add("writing")
    if "代理" in joined:
        expanded.add("agent")
    if "检索" in joined:
        expanded.add("retrieval")
    if "学术" in joined:
        expanded.add("academic")
    if "科研" in joined:
        expanded.add("research")
    if "高校" in joined:
        expanded.add("higher education")
    if "引文" in joined or "文献" in joined:
        expanded.add("citation")
        expanded.add("reference")
    return expanded

def _source_text_tokens(source: dict) -> set[str]:
    parts = [
        str(source.get("title") or ""),
        str(source.get("source") or ""),
        str(source.get("kind") or ""),
        str(source.get("url") or ""),
        str(source.get("id") or ""),
    ]
    joined = " ".join(parts).lower()
    tokens = set(_topic_tokens(joined))
    # Preserve phrases used by English literature datasets.
    for phrase in ["data governance", "smart contract", "supply chain", "low carbon", "public service", "rural development"]:
        if phrase in joined:
            tokens.add(phrase)
    return tokens


def _query_mentions_ai(query_tokens: set[str]) -> bool:
    ai_tokens = {
        "ai",
        "llm",
        "gpt",
        "chatgpt",
        "prompt",
        "rag",
        "retrieval",
        "language model",
        "academic writing",
        "writing agent",
        "writing assistant",
        "agentic writing",
        "multi-agent",
        "自动写作",
        "智能写作",
        "写作代理",
        "学术写作",
        "检索增强生成",
        "大模型",
    }
    ai_fragments = (
        "ai",
        "llm",
        "gpt",
        "chatgpt",
        "rag",
        "retrieval",
        "agent",
        "assistant",
        "writing",
        "智能写作",
        "写作代理",
        "学术写作",
        "大模型",
        "语言模型",
        "检索增强",
    )
    for token in query_tokens:
        if token in ai_tokens:
            return True
        if any(fragment in token for fragment in ai_fragments):
            return True
    return False

def _source_looks_ai_related(source: dict) -> bool:
    text = " ".join(
        [
            str(source.get("title") or ""),
            str(source.get("source") or ""),
            str(source.get("url") or ""),
        ]
    ).lower()
    if not text:
        return False
    return bool(
        re.search(
            r"\b(llm|gpt|chatgpt|prompt|rag|retrieval|copilot|language model|promptware)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def source_relevance_score(*, query: str, source: dict) -> int:
    query_tokens = _expanded_query_tokens(query)
    if not query_tokens:
        return 0
    if (not _query_mentions_ai(query_tokens)) and _source_looks_ai_related(source):
        return 0
    source_tokens = _source_text_tokens(source)
    if not source_tokens:
        return 0
    score = 0
    for token in query_tokens:
        if token in source_tokens:
            score += 2 if len(token) >= 4 else 1
        elif " " in token and token in " ".join(source_tokens):
            score += 1
    return score


def filter_sources_by_topic(
    sources: list[dict],
    *,
    query: str,
    min_score: int = 1,
    allow_unmatched_fallback: bool = False,
) -> list[dict]:
    if not sources:
        return []
    ranked: list[tuple[int, dict]] = []
    for row in sources:
        if not isinstance(row, dict):
            continue
        score = source_relevance_score(query=query, source=row)
        ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    passed = [row for score, row in ranked if score >= int(min_score)]
    if passed:
        return passed
    if not allow_unmatched_fallback:
        return []
    # Keep only top few when no lexical overlap is found, and let downstream quality
    # gate decide pass/fail instead of injecting large irrelevant lists.
    fallback_cap = max(0, min(24, int(os.environ.get("WRITING_AGENT_REFERENCE_FALLBACK_TOPK", "24"))))
    if fallback_cap <= 0:
        return []
    return [row for _, row in ranked[:fallback_cap]]


def sort_reference_sources(
    sources: list[dict],
    *,
    query: str,
    extract_year_fn: Callable[[str], str],
) -> list[dict]:
    if not sources:
        return []
    query_norm = normalize_reference_query(query)

    def _year_value(row: dict) -> int:
        year = extract_year_fn(str(row.get("published") or "")) or extract_year_fn(str(row.get("updated") or ""))
        return int(year) if str(year).isdigit() else 0

    def _method_penalty(row: dict) -> int:
        title = str(row.get("title") or "")
        score = source_relevance_score(query=query_norm, source=row) if query_norm else 0
        if re.search(r"\b(citespace|bibliometric|scientometric|knowledge mapping)\b", title, flags=re.IGNORECASE):
            return 30 if score <= 2 else 10
        return 0

    def _entity_bonus(row: dict) -> int:
        title = str(row.get("title") or "")
        bonus = 0
        if re.search(r"\b(blockchain|distributed ledger)\b", title, flags=re.IGNORECASE):
            bonus += 4
        if re.search(r"\b(rural|agricultural service|socialized service|governance)\b", title, flags=re.IGNORECASE):
            bonus += 2
        if re.search(r"\b(citespace|bibliometric|scientometric)\b", title, flags=re.IGNORECASE):
            bonus += 1
        return bonus

    ranked: list[tuple[tuple[int, int, int, int], dict]] = []
    for idx, row in enumerate(sources or []):
        if not isinstance(row, dict):
            continue
        relevance = source_relevance_score(query=query_norm, source=row) if query_norm else 0
        year_value = _year_value(row)
        penalty = _method_penalty(row)
        entity_bonus = _entity_bonus(row)
        ranked.append(((relevance + entity_bonus, year_value, -penalty, -idx), row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in ranked]



__all__ = [name for name in globals() if not name.startswith("__")]
