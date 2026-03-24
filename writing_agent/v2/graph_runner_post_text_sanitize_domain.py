"""Sanitization helpers for graph runner post text processing."""

from __future__ import annotations

import re

from writing_agent.v2 import graph_runner_rag_context_domain, graph_text_sanitize_domain

_has_cjk = graph_runner_rag_context_domain._has_cjk
_is_mostly_ascii_line = graph_runner_rag_context_domain._is_mostly_ascii_line
_META_PHRASES = [
    "下面是",
    "以下是",
    "根据你的要求",
    "根据您的要求",
    "生成结果如下",
    "输出如下",
]


def _sanitize_output_text(text: str) -> str:
    banned = [
        "如果您有任何",
        "如有任何",
        "您有任何",
        "需要进一步的信息",
        "随时回来询问",
        "欢迎随时",
        "祝您",
        "期待未来",
        "继续交流",
        "非常感谢",
        "感谢您",
        "不客气",
        "很高兴能为您提供帮助",
    ]
    return graph_text_sanitize_domain.sanitize_output_text(
        text,
        meta_phrases=_META_PHRASES,
        has_cjk=_has_cjk,
        is_mostly_ascii_line=_is_mostly_ascii_line,
        banned_phrases=banned,
    )


def _strip_markdown_noise(text: str) -> str:
    return graph_text_sanitize_domain.strip_markdown_noise(text)


def _should_merge_tail(prev_line: str, line: str) -> bool:
    return graph_text_sanitize_domain.should_merge_tail(prev_line, line)


def _clean_generated_text(text: str) -> str:
    return graph_text_sanitize_domain.clean_generated_text(text, should_merge_tail_fn=_should_merge_tail)


def _looks_like_heading_text(text: str) -> bool:
    token = (text or "").strip()
    if not token:
        return False
    if re.search(r"[。！？；：]", token):
        return False
    if re.match(r"^第\s*\d+\s*章", token):
        return True
    keywords = [
        "绪论",
        "引言",
        "综述",
        "背景",
        "意义",
        "方法",
        "设计",
        "系统",
        "实现",
        "架构",
        "模块",
        "测试",
        "评估",
        "分析",
        "结果",
        "结论",
        "总结",
        "展望",
        "需求",
        "参考文献",
        "附录",
        "致谢",
    ]
    return any(keyword in token for keyword in keywords)


__all__ = [name for name in globals() if not name.startswith('__')]
