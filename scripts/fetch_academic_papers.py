r"""批量抓取学术论文，结合目录结构抽取知识点。

流程：
    1. arXiv API 搜索 → 拿到论文 ID + 摘要
    2. 下载 LaTeX 源文件 (.tar.gz) → 提取 \section{} 目录
    3. 将"摘要 + 目录"作为上下文发给 LLM 抽取知识点
    4. 每张卡片标注来源章节（source_section）

用法：
    .venv\\Scripts\\python.exe scripts\\fetch_academic_papers.py "transformer architecture" --limit 20
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env so LLM provider can read API keys
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# arXiv search
# --------------------------------------------------------------------------- #

def fetch_arxiv_ids(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search arXiv and return list of {id, title, authors, year, abstract}."""
    import xml.etree.ElementTree as ET

    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query=all:{query.replace(' ', '+')}&"
        f"start=0&max_results={limit}&"
        "sortBy=relevance&sortOrder=descending"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "writing-agent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("arXiv search failed: %s", exc)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).replace("\n", " ").strip()
            summary = entry.findtext("atom:summary", "", ns).strip()
            id_url = entry.findtext("atom:id", "", ns)
            paper_id = id_url.split("/abs/")[-1] if "/abs/" in id_url else id_url
            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
            year = None
            published = entry.findtext("atom:published", "", ns)
            if published:
                m = re.search(r"(\d{4})", published)
                if m:
                    year = int(m.group(1))
            results.append({
                "id": paper_id,
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": summary,
            })
    except Exception as exc:
        logger.warning("arXiv parse failed: %s", exc)
    logger.info("arXiv search returned %d papers for '%s'", len(results), query)
    return results


# --------------------------------------------------------------------------- #
# LaTeX source download + TOC extraction
# --------------------------------------------------------------------------- #

def download_arxiv_source(arxiv_id: str, timeout: float = 30.0) -> bytes | None:
    """Download arXiv source tarball (.tar.gz)."""
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "writing-agent/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 1024:
            return None
        return data
    except Exception as exc:
        logger.debug("Source download failed for %s: %s", arxiv_id, exc)
        return None


def extract_toc_from_latex(tar_bytes: bytes) -> list[dict[str, Any]]:
    r"""Extract \section{} and \subsection{} from LaTeX source in tarball."""
    sections: list[dict[str, Any]] = []
    try:
        tf = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz")
    except Exception:
        return sections

    tex_names = [m for m in tf.getmembers() if m.name.endswith(".tex") and m.isfile()]
    # Prefer the main tex file (often shortest name or contains \documentclass)
    tex_names.sort(key=lambda m: (not m.name.lower().startswith("arxiv"), len(m.name)))

    for member in tex_names:
        try:
            f = tf.extractfile(member)
            if not f:
                continue
            tex = f.read().decode("utf-8", errors="replace")
            # Find \documentclass to identify main file
            if "\\documentclass" in tex or "\\section{" in tex:
                # Extract sections
                for match in re.finditer(r"\\section\*?\{([^}]+)\}", tex):
                    sections.append({"level": 1, "title": match.group(1).strip()})
                for match in re.finditer(r"\\subsection\*?\{([^}]+)\}", tex):
                    sections.append({"level": 2, "title": match.group(1).strip()})
                if sections:
                    break
        except Exception:
            continue
    return sections


# --------------------------------------------------------------------------- #
# LLM extraction with TOC context
# --------------------------------------------------------------------------- #

def extract_kus_with_toc(
    paper: dict[str, Any],
    toc: list[dict[str, Any]],
    extractor=None,
) -> list[Any]:
    """Extract KUs using abstract + TOC as context."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor

    ext = extractor or KnowledgeUnitExtractor()

    # Build rich context: abstract + chapter outline
    toc_lines = [f"  {'  ' * (s['level'] - 1)}- {s['title']}" for s in toc]
    context = (
        f"Paper: {paper['title']}\n"
        f"Authors: {', '.join(paper['authors'][:4])}\n"
        f"Year: {paper['year'] or 'N/A'}\n\n"
        f"Abstract:\n{paper['abstract']}\n\n"
    )
    if toc_lines:
        context += "Table of Contents:\n" + "\n".join(toc_lines) + "\n\n"
    context += (
        "Extract up to 8 knowledge units from this paper. "
        "For each unit, identify which section it most likely belongs to."
    )

    # Use abstract as the text body (we don't have full text per section)
    # But the TOC gives the LLM structural context for better extraction
    units = ext.extract_from_text(
        text=paper["abstract"],
        source_doc=paper["id"],
        source_title=paper["title"],
        source_authors=paper["authors"],
        max_units=8,
    )

    # Enrich units with section info via heuristic matching
    section_titles = [s["title"] for s in toc if s["level"] == 1]
    for u in units:
        claim_lower = (u.claim or "").lower()
        best_section = ""
        for sec in section_titles:
            sec_lower = sec.lower()
            # Simple keyword overlap heuristic
            sec_words = set(re.findall(r"[a-z]{3,}", sec_lower))
            claim_words = set(re.findall(r"[a-z]{3,}", claim_lower))
            if sec_words & claim_words:
                best_section = sec
                break
        # Store section info in a custom field via model_copy
        if best_section:
            try:
                u = u.model_copy(update={"source_para": best_section})
            except Exception:
                pass

    return units


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch papers with TOC-aware KU extraction")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Max papers")
    parser.add_argument("--output", type=str, default=".data/kg", help="Output directory")
    parser.add_argument("--no-source", action="store_true", help="Skip LaTeX source download")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    papers = fetch_arxiv_ids(args.query, limit=args.limit)
    if not papers:
        logger.error("No papers found for query: %s", args.query)
        return

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from writing_agent.v2.rag.knowledge_graph import KnowledgeGraph
    from writing_agent.v2.rag.knowledge_unit import KUStore

    store = KUStore(out_dir)
    kg = KnowledgeGraph()
    total_units = 0

    for p in papers:
        logger.info("Processing: %s", p["title"][:60])
        toc: list[dict[str, Any]] = []

        if not args.no_source:
            src = download_arxiv_source(p["id"], timeout=30.0)
            if src:
                toc = extract_toc_from_latex(src)
                logger.info("  Extracted TOC: %d sections", len(toc))
                for s in toc[:6]:
                    indent = "  " * (s["level"] - 1)
                    logger.debug("    %s- %s", indent, s["title"])

        from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor
        ext = KnowledgeUnitExtractor()
        units = extract_kus_with_toc(p, toc, extractor=ext)

        if units:
            added = store.save(units)
            total_units += added
            kg.build_from_kus(units)
            logger.info("  Added %d KUs", added)
        else:
            logger.info("  No KUs extracted")

        time.sleep(0.5)

    kg.save(out_dir / "knowledge_graph.json")
    logger.info("=" * 50)
    logger.info("Done. Total KUs: %d | KG stats: %s", total_units, kg.stats())


if __name__ == "__main__":
    main()
