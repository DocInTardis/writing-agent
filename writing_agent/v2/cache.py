"""
本地缓存系统 - 用于复用生成结果和学术模板
支持章节内容、学术表达、引用格式的缓存与快速检索
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    key: str
    value: str
    created_at: float
    hits: int
    metadata: dict[str, Any]


class LocalCache:
    """本地JSON缓存,支持LRU淘汰和TTL过期"""
    
    def __init__(self, cache_dir: Path, max_size: int = 500, ttl_seconds: float = 86400 * 7):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.index_path = self.cache_dir / "index.json"
        self._load_index()
    
    def _load_index(self) -> None:
        if not self.index_path.exists():
            self.index: dict[str, dict] = {}
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            self.index = data if isinstance(data, dict) else {}
        except Exception:
            self.index = {}
    
    def _save_index(self) -> None:
        try:
            self.index_path.write_text(json.dumps(self.index, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _make_key(self, *args: str) -> str:
        """生成缓存键"""
        combined = "|".join([str(a) for a in args if a])
        return hashlib.md5(combined.encode("utf-8")).hexdigest()
    
    def get(self, key: str) -> str | None:
        """获取缓存,自动处理过期"""
        entry = self.index.get(key)
        if not entry:
            return None
        
        created_at = float(entry.get("created_at", 0))
        if time.time() - created_at > self.ttl_seconds:
            # 过期删除
            self.index.pop(key, None)
            cache_file = self.cache_dir / f"{key}.txt"
            try:
                cache_file.unlink(missing_ok=True)
            except Exception:
                pass
            self._save_index()
            return None
        
        cache_file = self.cache_dir / f"{key}.txt"
        if not cache_file.exists():
            self.index.pop(key, None)
            self._save_index()
            return None
        
        try:
            value = cache_file.read_text(encoding="utf-8")
            # 更新命中次数
            entry["hits"] = int(entry.get("hits", 0)) + 1
            entry["last_hit"] = time.time()
            self.index[key] = entry
            self._save_index()
            return value
        except Exception:
            return None
    
    def put(self, key: str, value: str, metadata: dict[str, Any] | None = None) -> None:
        """存入缓存,自动LRU淘汰"""
        # 检查大小,LRU淘汰
        if len(self.index) >= self.max_size:
            self._evict_lru()
        
        cache_file = self.cache_dir / f"{key}.txt"
        try:
            cache_file.write_text(value, encoding="utf-8")
        except Exception:
            return
        
        self.index[key] = {
            "created_at": time.time(),
            "hits": 0,
            "last_hit": time.time(),
            "metadata": metadata or {},
        }
        self._save_index()
    
    def _evict_lru(self) -> None:
        """淘汰最少使用的10%缓存"""
        if not self.index:
            return
        
        # 按(命中次数,最后命中时间)排序,淘汰底部10%
        sorted_keys = sorted(
            self.index.keys(),
            key=lambda k: (self.index[k].get("hits", 0), self.index[k].get("last_hit", 0))
        )
        
        evict_count = max(1, len(sorted_keys) // 10)
        for key in sorted_keys[:evict_count]:
            self.index.pop(key, None)
            cache_file = self.cache_dir / f"{key}.txt"
            try:
                cache_file.unlink(missing_ok=True)
            except Exception:
                pass
        
        self._save_index()
    
    def get_section(self, section_title: str, instruction: str, min_chars: int) -> str | None:
        """获取章节缓存"""
        key = self._make_key("section", section_title, instruction, str(min_chars))
        return self.get(key)
    
    def put_section(self, section_title: str, instruction: str, min_chars: int, content: str) -> None:
        """存入章节缓存"""
        key = self._make_key("section", section_title, instruction, str(min_chars))
        self.put(key, content, metadata={"type": "section", "title": section_title})
    
    def clear_expired(self) -> int:
        """清理过期缓存"""
        now = time.time()
        expired = []
        for key, entry in self.index.items():
            created_at = float(entry.get("created_at", 0))
            if now - created_at > self.ttl_seconds:
                expired.append(key)
        
        for key in expired:
            self.index.pop(key, None)
            cache_file = self.cache_dir / f"{key}.txt"
            try:
                cache_file.unlink(missing_ok=True)
            except Exception:
                pass
        
        if expired:
            self._save_index()
        
        return len(expired)
    
    def stats(self) -> dict:
        """缓存统计"""
        total_hits = sum(e.get("hits", 0) for e in self.index.values())
        return {
            "total_entries": len(self.index),
            "total_hits": total_hits,
            "avg_hits": total_hits / max(1, len(self.index)),
            "cache_dir": str(self.cache_dir),
        }


class AcademicPhraseCache:
    """学术表达模板缓存 - 高频表达快速复用"""
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.phrases_path = self.cache_dir / "academic_phrases.json"
        self._load_phrases()
    
    def _load_phrases(self) -> None:
        if not self.phrases_path.exists():
            self.phrases = self._default_phrases()
            self._save_phrases()
            return
        
        try:
            data = json.loads(self.phrases_path.read_text(encoding="utf-8"))
            self.phrases = data if isinstance(data, dict) else self._default_phrases()
        except Exception:
            self.phrases = self._default_phrases()
    
    def _save_phrases(self) -> None:
        try:
            self.phrases_path.write_text(
                json.dumps(self.phrases, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass
    
    def _default_phrases(self) -> dict:
        """默认学术表达模板"""
        return {
            "引言": [
                "近年来,{主题}领域取得了显著进展。",
                "本研究旨在探讨{主题}的{方面},为{目标}提供理论支持。",
                "在{背景}的推动下,{主题}日益受到学术界和工业界的关注。",
            ],
            "方法": [
                "本研究采用{方法}对{对象}进行分析。",
                "实验设计包括以下步骤:第一,{步骤1};第二,{步骤2};第三,{步骤3}。",
                "数据采集采用{工具},样本量为{数量},采样周期为{周期}。",
            ],
            "结果": [
                "实验结果表明,{结论}。",
                "数据分析显示,{指标}达到{数值},符合预期目标。",
                "对比实验表明,{方案A}相比{方案B}在{指标}上提升了{百分比}。",
            ],
            "结论": [
                "本研究的主要贡献在于:{贡献1};{贡献2};{贡献3}。",
                "研究局限性包括:{局限1};{局限2}。",
                "未来工作方向包括:{方向1};{方向2}。",
            ],
            "背景": [
                "随着{技术}的快速发展,{领域}面临着{挑战}。",
                "现有研究主要关注{方向},但在{方面}仍存在不足。",
            ],
        }
    
    def get_template(self, section_title: str) -> list[str]:
        """获取章节模板"""
        for key in self.phrases.keys():
            if key in section_title:
                return self.phrases.get(key, [])
        return []
    
    def add_phrase(self, section_title: str, phrase: str) -> None:
        """添加新表达"""
        if section_title not in self.phrases:
            self.phrases[section_title] = []
        
        if phrase not in self.phrases[section_title]:
            self.phrases[section_title].append(phrase)
            self._save_phrases()
