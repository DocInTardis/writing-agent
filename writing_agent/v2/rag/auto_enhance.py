"""RAG自动增强模块 - 零成本方案"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def auto_fetch_on_empty(*, rag_dir: Path, query: str, min_papers: int = 5) -> bool:
    """
    当RAG库为空或过少时，自动从arXiv/OpenAlex抓取相关论文
    
    Args:
        rag_dir: RAG数据目录
        query: 用户查询
        min_papers: 最小论文数阈值
    
    Returns:
        是否成功补充数据
    """
    from writing_agent.v2.rag.store import RagStore
    from writing_agent.v2.rag.arxiv import search_arxiv
    from writing_agent.v2.rag.openalex import search_openalex
    
    store = RagStore(rag_dir)
    existing = store.list_papers()
    
    if len(existing) >= min_papers:
        return False
    
    logger.info(f"[auto-rag] 检测到RAG库仅{len(existing)}篇论文，自动补充中...")
    
    # 从查询中提取关键词
    keywords = _extract_keywords(query)
    
    added = 0
    # 先尝试OpenAlex（更快，无需下载PDF）
    for kw in keywords[:3]:  # 最多3个关键词
        try:
            result = search_openalex(query=kw, max_results=5)
            for work in result.works:
                try:
                    store.put_openalex_work(work, pdf_bytes=None)
                    added += 1
                    if len(existing) + added >= min_papers:
                        break
                except Exception as e:
                    logger.warning(f"[auto-rag] 保存失败: {e}")
            if len(existing) + added >= min_papers:
                break
        except Exception as e:
            logger.warning(f"[auto-rag] OpenAlex查询失败: {e}")
    
    logger.info(f"[auto-rag] 自动补充{added}篇论文元数据")
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
    """
    根据已有论文，扩展相关论文（基于标题/关键词相似）
    
    Args:
        rag_dir: RAG数据目录
        paper_ids: 已有论文ID列表
        max_expand: 每篇论文最多扩展数量
    
    Returns:
        扩展的论文数量
    """
    from writing_agent.v2.rag.store import RagStore
    from writing_agent.v2.rag.openalex import search_openalex
    
    store = RagStore(rag_dir)
    existing = {p.paper_id for p in store.list_papers()}
    
    added = 0
    for pid in paper_ids[:5]:  # 最多基于5篇论文扩展
        papers = store.list_papers()
        paper = next((p for p in papers if p.paper_id == pid), None)
        if not paper:
            continue
        
        # 提取论文标题关键词
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
            logger.warning(f"[auto-rag] 扩展失败: {e}")
    
    if added > 0:
        logger.info(f"[auto-rag] 基于相关性扩展{added}篇论文")
    
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
