"""RAG自动增强模块 - 零成本方案"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)
_AUTO_FETCH_LOCKS: dict[str, threading.Lock] = {}
_AUTO_FETCH_LOCKS_GUARD = threading.Lock()
_AUTO_FETCH_STATE: dict[str, float] = {}
_RELATED_EXPAND_STATE: dict[str, float] = {}


def _lock_for_rag_dir(rag_dir: Path) -> threading.Lock:
    key = str(Path(rag_dir).resolve())
    with _AUTO_FETCH_LOCKS_GUARD:
        lock = _AUTO_FETCH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _AUTO_FETCH_LOCKS[key] = lock
        return lock


def _env_enabled(name: str, *, default: bool = True) -> bool:
    import os

    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def auto_fetch_on_empty(*, rag_dir: Path, query: str, min_papers: int = 5) -> bool:
    if not _env_enabled("WRITING_AGENT_RAG_AUTO_FETCH_ENABLED", default=True):
        return False
    """
    ?RAG???????????arXiv/OpenAlex??????

    Args:
        rag_dir: RAG????
        query: ????
        min_papers: ???????

    Returns:
        ????????
    """
    from writing_agent.v2.rag.store import RagStore
    from writing_agent.v2.rag.arxiv import search_arxiv
    from writing_agent.v2.rag.openalex import search_openalex

    cooldown_s = max(10.0, float(__import__('os').environ.get('WRITING_AGENT_RAG_AUTO_FETCH_COOLDOWN_S', '120') or 120))
    key = str(Path(rag_dir).resolve())
    fetch_lock = _lock_for_rag_dir(rag_dir)
    with fetch_lock:
        now = time.time()
        last_run = float(_AUTO_FETCH_STATE.get(key) or 0.0)
        if now - last_run < cooldown_s:
            return False
        _AUTO_FETCH_STATE[key] = now

        store = RagStore(rag_dir)
        existing = store.list_papers()

        if len(existing) >= min_papers:
            return False

        logger.info(f"[auto-rag] ???RAG??{len(existing)}?????????...")

        # ?????????
        keywords = _extract_keywords(query)

        added = 0
        # ???OpenAlex????????PDF?
        for kw in keywords[:3]:  # ??3????
            try:
                result = search_openalex(query=kw, max_results=5)
                for work in result.works:
                    try:
                        store.put_openalex_work(work, pdf_bytes=None)
                        added += 1
                        if len(existing) + added >= min_papers:
                            break
                    except Exception as e:
                        logger.warning(f"[auto-rag] ????: {e}")
                if len(existing) + added >= min_papers:
                    break
            except Exception as e:
                logger.warning(f"[auto-rag] OpenAlex????: {e}")
                if "429" in str(e) or "Too Many Requests" in str(e):
                    break

        logger.info(f"[auto-rag] ????{added}??????")
        return added > 0



def _extract_keywords(query: str) -> list[str]:
    """从查询中提取关键词"""
    import re
    
    # 移除常见停用词
    stopwords = {
        '的', '了', '是', '在', '和', '与', '或', '等', '有', '为',
        '中', '对', '上', '下', '要', '请', '帮我', '生成', '写',
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
        'to', 'for', 'of', 'with', 'by', 'from', 'about'
    }
    
    # 提取2-15字的词组
    words = re.findall(r'[\w]+', query.lower())
    keywords = [w for w in words if len(w) >= 2 and w not in stopwords]
    
    # 优先级：长词组 > 短词
    keywords.sort(key=lambda x: len(x), reverse=True)
    
    return keywords[:5]


def expand_with_related(*, rag_dir: Path, paper_ids: list[str], max_expand: int = 3) -> int:
    if not _env_enabled("WRITING_AGENT_RAG_EXPAND_ENABLED", default=True):
        return 0
    """
    ??????????????????/??????

    Args:
        rag_dir: RAG????
        paper_ids: ????ID??
        max_expand: ??????????

    Returns:
        ???????
    """
    from writing_agent.v2.rag.store import RagStore
    from writing_agent.v2.rag.openalex import search_openalex

    cooldown_s = max(10.0, float(__import__('os').environ.get('WRITING_AGENT_RAG_EXPAND_COOLDOWN_S', '180') or 180))
    key = str(Path(rag_dir).resolve())
    fetch_lock = _lock_for_rag_dir(rag_dir)
    with fetch_lock:
        last_run = float(_RELATED_EXPAND_STATE.get(key) or 0.0)
        now = time.time()
        if now - last_run < cooldown_s:
            return 0
        _RELATED_EXPAND_STATE[key] = now

        store = RagStore(rag_dir)
        existing = {p.paper_id for p in store.list_papers()}

        added = 0
        for pid in paper_ids[:5]:  # ????5?????
            papers = store.list_papers()
            paper = next((p for p in papers if p.paper_id == pid), None)
            if not paper:
                continue

            title_keywords = _extract_keywords(paper.title)
            if not title_keywords:
                continue

            query = ' '.join(title_keywords[:3])
            try:
                result = search_openalex(query=query, max_results=max_expand)
                for work in result.works:
                    if work.paper_id in existing:
                        continue
                    try:
                        store.put_openalex_work(work, pdf_bytes=None)
                        existing.add(work.paper_id)
                        added += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[auto-rag] ????: {e}")
                if "429" in str(e) or "Too Many Requests" in str(e):
                    break

        if added > 0:
            logger.info(f"[auto-rag] ???????{added}???")

        return added



def use_user_docs_as_seed(*, rag_dir: Path, user_library_dir: Path) -> int:
    """
    将用户已生成的文档作为RAG种子数据
    
    Args:
        rag_dir: RAG数据目录
        user_library_dir: 用户文档库目录
    
    Returns:
        添加的文档数量
    """
    from writing_agent.v2.rag.index import RagIndex
    from writing_agent.v2.rag.user_library import UserLibrary
    
    rag_index = RagIndex(rag_dir)
    user_lib = UserLibrary(user_library_dir, rag_index)
    
    # 获取已审核的用户文档
    approved = user_lib.list_items(status="approved")
    
    added = 0
    for doc in approved:
        if doc.char_count < 500:  # 过短的文档跳过
            continue
        # 用户文档已经在approve时自动索引到rag_index
        added += 1
    
    if added > 0:
        logger.info(f"[auto-rag] 使用{added}篇用户文档作为RAG数据")
    
    return added


def smart_cache_frequent_queries(*, rag_dir: Path, query: str) -> None:
    """
    智能缓存高频查询，下次直接返回
    
    Args:
        rag_dir: RAG数据目录
        query: 查询内容
    """
    cache_file = Path(rag_dir) / "query_cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    import json
    import hashlib
    
    # 读取缓存
    cache = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    
    # 计算查询指纹
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()[:16]
    
    # 更新频次
    if query_hash not in cache:
        cache[query_hash] = {"query": query, "count": 1, "last_used": ""}
    else:
        cache[query_hash]["count"] += 1
    
    from datetime import datetime
    cache[query_hash]["last_used"] = datetime.now().isoformat()
    
    # 保存缓存（限制最多1000条）
    if len(cache) > 1000:
        # 按使用次数排序，保留top 1000
        sorted_cache = dict(sorted(cache.items(), key=lambda x: x[1]["count"], reverse=True)[:1000])
        cache = sorted_cache
    
    try:
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
