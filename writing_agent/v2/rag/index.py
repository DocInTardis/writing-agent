"""Index module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
from array import array
from dataclasses import dataclass
from pathlib import Path

from writing_agent.llm import OllamaClient, get_ollama_settings
from writing_agent.v2.rag.chunking import chunk_text
from writing_agent.v2.rag.pdf_text import extract_pdf_text
from writing_agent.v2.rag.store import RagPaperRecord, RagStore, safe_paper_key


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    paper_id: str
    title: str
    abs_url: str
    kind: str  # "abstract" | "pdf"
    text: str
    embedding_b64: str = ""
    dim: int = 0


@dataclass(frozen=True)
class RagChunkHit:
    chunk_id: str
    paper_id: str
    title: str
    abs_url: str
    kind: str
    score: float
    text: str


class RagIndex:
    def __init__(self, rag_dir: Path) -> None:
        self.rag_dir = Path(rag_dir)
        self.index_path = self.rag_dir / "chunks.jsonl"

    def ensure(self) -> None:
        self.rag_dir.mkdir(parents=True, exist_ok=True)

    def upsert_from_paper(
        self,
        paper: RagPaperRecord,
        *,
        embed: bool = True,
        chunk_max_chars: int = 900,
        chunk_overlap: int = 120,
    ) -> list[RagChunk]:
        self.ensure()
        embed_model = _embed_model_name() if embed else ""
        embed_client = _make_embed_client(embed_model) if embed_model else None

        chunks: list[RagChunk] = []
        # Abstract chunks
        base_text = (paper.title or "").strip()
        if paper.summary.strip():
            base_text = (base_text + "\n\n" + paper.summary.strip()).strip()
        for i, c in enumerate(chunk_text(text=base_text, max_chars=chunk_max_chars, overlap=chunk_overlap), start=1):
            chunks.append(_make_chunk(paper, kind="abstract", idx=i, text=c, embed_client=embed_client, embed_model=embed_model))

        # Optional PDF chunks
        pdf_path = Path(paper.pdf_path)
        if pdf_path.exists():
            max_pages = int(os.environ.get("WRITING_AGENT_RAG_PDF_MAX_PAGES", "12"))
            pdf_text = extract_pdf_text(pdf_path, max_pages=max_pages)
            if pdf_text:
                for i, c in enumerate(chunk_text(text=pdf_text, max_chars=chunk_max_chars, overlap=chunk_overlap), start=1):
                    chunks.append(_make_chunk(paper, kind="pdf", idx=i, text=c, embed_client=embed_client, embed_model=embed_model))

        # Rewrite index file: remove existing chunks of this paper_id, then append.
        existing = self.load_chunks()
        kept = [x for x in existing if x.paper_id != paper.paper_id]
        all_chunks = kept + chunks
        self._write_chunks(all_chunks)
        return chunks

    def upsert_from_text(
        self,
        *,
        paper_id: str,
        title: str,
        text: str,
        abs_url: str = "",
        embed: bool = True,
        chunk_max_chars: int = 900,
        chunk_overlap: int = 120,
    ) -> list[RagChunk]:
        self.ensure()
        pid = (paper_id or "").strip()
        if not pid:
            return []
        base_text = (text or "").strip()
        if not base_text:
            return []

        embed_model = _embed_model_name() if embed else ""
        embed_client = _make_embed_client(embed_model) if embed_model else None

        chunks: list[RagChunk] = []
        for i, c in enumerate(chunk_text(text=base_text, max_chars=chunk_max_chars, overlap=chunk_overlap), start=1):
            emb_b64 = ""
            dim = 0
            if embed_client and embed_model:
                vec = embed_client.embeddings(prompt=c, model=embed_model)
                emb_b64, dim = _encode_vec(vec)
            chunks.append(
                RagChunk(
                    chunk_id=f"{safe_paper_key(pid)}:text:{i:03d}",
                    paper_id=pid,
                    title=title or "",
                    abs_url=abs_url or "",
                    kind="text",
                    text=c,
                    embedding_b64=emb_b64,
                    dim=dim,
                )
            )

        existing = self.load_chunks()
        kept = [x for x in existing if x.paper_id != pid]
        all_chunks = kept + chunks
        self._write_chunks(all_chunks)
        return chunks

    def delete_by_paper_id(self, paper_id: str) -> int:
        pid = (paper_id or "").strip()
        if not pid:
            return 0
        existing = self.load_chunks()
        kept = [x for x in existing if x.paper_id != pid]
        removed = len(existing) - len(kept)
        if removed:
            self._write_chunks(kept)
        return removed

    def rebuild(self, *, embed: bool = True) -> int:
        rag = RagStore(self.rag_dir)
        papers = rag.list_papers()
        self._write_chunks([])
        total = 0
        for p in papers:
            total += len(self.upsert_from_paper(p, embed=embed))
        return total

    def load_chunks(self) -> list[RagChunk]:
        if not self.index_path.exists():
            return []
        out: list[RagChunk] = []
        for line in self.index_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            out.append(
                RagChunk(
                    chunk_id=str(obj.get("chunk_id") or ""),
                    paper_id=str(obj.get("paper_id") or ""),
                    title=str(obj.get("title") or ""),
                    abs_url=str(obj.get("abs_url") or ""),
                    kind=str(obj.get("kind") or ""),
                    text=str(obj.get("text") or ""),
                    embedding_b64=str(obj.get("embedding_b64") or ""),
                    dim=int(obj.get("dim") or 0),
                )
            )
        return [c for c in out if c.chunk_id and c.paper_id and c.text]

    def search(
        self,
        *,
        query: str,
        top_k: int = 6,
        per_paper: int = 2,
        use_embeddings: bool = True,
        alpha: float = 0.75,
    ) -> list[RagChunkHit]:
        q = (query or "").strip()
        if not q:
            return []
        top_k = int(max(1, min(30, top_k)))
        per_paper = int(max(1, min(6, per_paper)))
        alpha = float(max(0.0, min(1.0, alpha)))

        chunks = self.load_chunks()
        if not chunks:
            return []

        embed_model = _embed_model_name() if use_embeddings else ""
        q_vec: list[float] | None = None
        if embed_model:
            try:
                q_vec = _embed_query(q, embed_model=embed_model)
            except Exception:
                q_vec = None

        scored: list[tuple[float, RagChunk]] = []
        for c in chunks:
            kw = _keyword_score(q, c.text, c.title)
            if q_vec is None:
                score = kw
            else:
                sim = _cosine_sim(q_vec, _decode_vec(c.embedding_b64, c.dim))
                score = alpha * sim + (1.0 - alpha) * kw
            if score <= 0:
                continue
            scored.append((float(score), c))

        scored.sort(key=lambda x: x[0], reverse=True)
        # enforce per-paper cap
        out: list[RagChunkHit] = []
        per: dict[str, int] = {}
        for score, c in scored:
            if len(out) >= top_k:
                break
            n = per.get(c.paper_id, 0)
            if n >= per_paper:
                continue
            per[c.paper_id] = n + 1
            out.append(
                RagChunkHit(
                    chunk_id=c.chunk_id,
                    paper_id=c.paper_id,
                    title=c.title,
                    abs_url=c.abs_url,
                    kind=c.kind,
                    score=score,
                    text=c.text,
                )
            )
        return out

    def _write_chunks(self, chunks: list[RagChunk]) -> None:
        self.ensure()
        lines: list[str] = []
        for c in chunks:
            obj = {
                "chunk_id": c.chunk_id,
                "paper_id": c.paper_id,
                "title": c.title,
                "abs_url": c.abs_url,
                "kind": c.kind,
                "text": c.text,
                "embedding_b64": c.embedding_b64,
                "dim": c.dim,
            }
            lines.append(json.dumps(obj, ensure_ascii=False))
        self.index_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _make_chunk(
    paper: RagPaperRecord,
    *,
    kind: str,
    idx: int,
    text: str,
    embed_client: OllamaClient | None,
    embed_model: str,
) -> RagChunk:
    paper_key = safe_paper_key(paper.paper_id)
    chunk_id = f"{paper_key}:{kind}:{idx:03d}"
    emb_b64 = ""
    dim = 0
    if embed_client and embed_model:
        vec = embed_client.embeddings(prompt=text, model=embed_model)
        emb_b64, dim = _encode_vec(vec)
    return RagChunk(
        chunk_id=chunk_id,
        paper_id=paper.paper_id,
        title=paper.title,
        abs_url=paper.abs_url,
        kind=kind,
        text=text,
        embedding_b64=emb_b64,
        dim=dim,
    )


def _embed_model_name() -> str:
    return (os.environ.get("WRITING_AGENT_EMBED_MODEL", "").strip() or "nomic-embed-text:latest").strip()


def _make_embed_client(embed_model: str) -> OllamaClient | None:
    settings = get_ollama_settings()
    if not settings.enabled:
        return None
    client = OllamaClient(base_url=settings.base_url, model=embed_model, timeout_s=max(60.0, settings.timeout_s))
    if not client.is_running():
        return None
    try:
        if not client.has_model():
            return None
    except Exception:
        return None
    return client


def _embed_query(query: str, *, embed_model: str) -> list[float]:
    settings = get_ollama_settings()
    client = OllamaClient(base_url=settings.base_url, model=embed_model, timeout_s=max(60.0, settings.timeout_s))
    if not client.is_running():
        return []
    try:
        if not client.has_model():
            return []
    except Exception:
        return []
    return client.embeddings(prompt=query, model=embed_model)


def _encode_vec(vec: list[float]) -> tuple[str, int]:
    arr = array("f", [float(x) for x in (vec or [])])
    raw = arr.tobytes()
    return base64.b64encode(raw).decode("ascii"), len(arr)


def _decode_vec(b64: str, dim: int) -> list[float]:
    if not b64 or not dim:
        return []
    try:
        raw = base64.b64decode(b64.encode("ascii"))
        arr = array("f")
        arr.frombytes(raw)
        if dim and len(arr) >= dim:
            return list(arr[:dim])
        return list(arr)
    except Exception:
        return []


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        x = float(a[i])
        y = float(b[i])
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return float(dot / math.sqrt(na * nb))


def _keyword_score(query: str, text: str, title: str) -> float:
    q = (query or "").lower().strip()
    if not q:
        return 0.0
    hay = ((title or "") + "\n" + (text or "")).lower()
    # cheap tokenization: words or characters
    toks = [t for t in re.findall(r"[a-z0-9_]+", q) if t]
    if not toks:
        toks = [ch for ch in q if ch.strip()]
    score = 0.0
    for t in toks[:24]:
        if not t:
            continue
        c = hay.count(t)
        if c:
            score += 1.0 + math.log(1.0 + c)
    return score
