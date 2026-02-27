"""User Library module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from writing_agent.v2.rag.index import RagIndex
from writing_agent.v2.rag.pdf_text import extract_pdf_text
from writing_agent.v2.template_parse import prepare_template_file


@dataclass(frozen=True)
class UserDocRecord:
    doc_id: str
    title: str
    source_name: str
    source_path: str
    text_path: str
    status: str
    created_at: str
    updated_at: str
    trash_until: str
    source: str
    source_id: str
    char_count: int


class UserLibrary:
    def __init__(self, base_dir: Path, rag_index: RagIndex) -> None:
        self.base_dir = Path(base_dir)
        self.meta_dir = self.base_dir / "meta"
        self.files_dir = self.base_dir / "files"
        self.text_dir = self.base_dir / "texts"
        self.rag_index = rag_index
        self.trash_days = 7

    def ensure(self) -> None:
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.text_dir.mkdir(parents=True, exist_ok=True)

    def list_items(self, *, status: str | None = None) -> list[UserDocRecord]:
        self.ensure()
        self.cleanup_expired()
        items: list[UserDocRecord] = []
        for meta_path in sorted(self.meta_dir.glob("*.json")):
            meta = _read_json(meta_path)
            if not meta:
                continue
            st = str(meta.get("status") or "")
            if status and st != status:
                continue
            items.append(_record_from_meta(meta))
        return items

    def get_item(self, doc_id: str) -> UserDocRecord | None:
        meta = _read_json(self._meta_path(doc_id))
        if not meta:
            return None
        return _record_from_meta(meta)

    def get_text(self, doc_id: str) -> str:
        rec = self.get_item(doc_id)
        if not rec:
            return ""
        path = Path(rec.text_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def put_upload(self, *, filename: str, file_bytes: bytes) -> UserDocRecord:
        self.ensure()
        doc_id = uuid.uuid4().hex
        safe_name = filename or "upload"
        ext = Path(safe_name).suffix.lower() or ".bin"
        file_path = self.files_dir / f"{doc_id}{ext}"
        file_path.write_bytes(file_bytes)
        text = _extract_text(file_path)
        title = _derive_title(text, Path(safe_name).stem)
        text_path = self.text_dir / f"{doc_id}.txt"
        text_path.write_text(text, encoding="utf-8")
        meta = _make_meta(
            doc_id=doc_id,
            title=title,
            source_name=safe_name,
            source_path=str(file_path),
            text_path=str(text_path),
            status="pending",
            source="upload",
            source_id="",
            char_count=_count_chars(text),
        )
        _write_json(self._meta_path(doc_id), meta)
        return _record_from_meta(meta)

    def put_text(
        self,
        *,
        text: str,
        title: str,
        source: str,
        status: str,
        source_id: str = "",
    ) -> UserDocRecord:
        self.ensure()
        existing = self._find_by_source_id(source_id) if source_id else None
        doc_id = existing["doc_id"] if existing else uuid.uuid4().hex
        text_path = self.text_dir / f"{doc_id}.txt"
        text_path.write_text(text, encoding="utf-8")
        meta = _make_meta(
            doc_id=doc_id,
            title=title or _derive_title(text, "自动生成文档"),
            source_name="",
            source_path="",
            text_path=str(text_path),
            status=status,
            source=source,
            source_id=source_id,
            char_count=_count_chars(text),
            created_at=existing.get("created_at") if existing else "",
        )
        if status == "trashed":
            meta["trash_until"] = _trash_until(self.trash_days)
        _write_json(self._meta_path(doc_id), meta)
        if status == "approved":
            self._index_doc(meta)
        else:
            self.rag_index.delete_by_paper_id(_paper_id(doc_id))
        return _record_from_meta(meta)

    def update_text(self, doc_id: str, *, text: str) -> UserDocRecord | None:
        rec = self.get_item(doc_id)
        if not rec:
            return None
        text_path = Path(rec.text_path)
        text_path.write_text(text, encoding="utf-8")
        meta = _make_meta(
            doc_id=rec.doc_id,
            title=rec.title or _derive_title(text, "自动生成文档"),
            source_name=rec.source_name,
            source_path=rec.source_path,
            text_path=str(text_path),
            status=rec.status,
            source=rec.source,
            source_id=rec.source_id,
            char_count=_count_chars(text),
            created_at=rec.created_at,
        )
        if rec.status == "trashed":
            meta["trash_until"] = rec.trash_until or _trash_until(self.trash_days)
        _write_json(self._meta_path(doc_id), meta)
        if rec.status == "approved":
            self._index_doc(meta)
        return _record_from_meta(meta)

    def approve(self, doc_id: str) -> UserDocRecord | None:
        meta = _read_json(self._meta_path(doc_id))
        if not meta:
            return None
        meta["status"] = "approved"
        meta["updated_at"] = _now_iso()
        meta["trash_until"] = ""
        _write_json(self._meta_path(doc_id), meta)
        self._index_doc(meta)
        return _record_from_meta(meta)

    def restore(self, doc_id: str) -> UserDocRecord | None:
        meta = _read_json(self._meta_path(doc_id))
        if not meta:
            return None
        meta["status"] = "pending"
        meta["updated_at"] = _now_iso()
        meta["trash_until"] = ""
        _write_json(self._meta_path(doc_id), meta)
        self.rag_index.delete_by_paper_id(_paper_id(doc_id))
        return _record_from_meta(meta)

    def trash(self, doc_id: str) -> UserDocRecord | None:
        meta = _read_json(self._meta_path(doc_id))
        if not meta:
            return None
        meta["status"] = "trashed"
        meta["updated_at"] = _now_iso()
        meta["trash_until"] = _trash_until(self.trash_days)
        _write_json(self._meta_path(doc_id), meta)
        self.rag_index.delete_by_paper_id(_paper_id(doc_id))
        return _record_from_meta(meta)

    def delete(self, doc_id: str) -> bool:
        meta_path = self._meta_path(doc_id)
        meta = _read_json(meta_path)
        if not meta:
            return False
        for key in ("source_path", "text_path"):
            path = Path(str(meta.get(key) or ""))
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass
        try:
            meta_path.unlink()
        except Exception:
            pass
        self.rag_index.delete_by_paper_id(_paper_id(doc_id))
        return True

    def cleanup_expired(self) -> None:
        self.ensure()
        now = datetime.now(timezone.utc)
        for meta_path in self.meta_dir.glob("*.json"):
            meta = _read_json(meta_path)
            if not meta:
                continue
            if str(meta.get("status") or "") != "trashed":
                continue
            until = str(meta.get("trash_until") or "")
            if not until:
                continue
            try:
                ts = datetime.fromisoformat(until)
            except Exception:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts <= now:
                doc_id = str(meta.get("doc_id") or "")
                if doc_id:
                    self.delete(doc_id)

    def _index_doc(self, meta: dict) -> None:
        doc_id = str(meta.get("doc_id") or "")
        if not doc_id:
            return
        text_path = Path(str(meta.get("text_path") or ""))
        if not text_path.exists():
            return
        text = text_path.read_text(encoding="utf-8", errors="replace")
        title = str(meta.get("title") or "") or "自动生成文档"
        self.rag_index.upsert_from_text(paper_id=_paper_id(doc_id), title=title, text=text, abs_url="", embed=True)

    def _meta_path(self, doc_id: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", doc_id or "")
        return self.meta_dir / f"{safe}.json"

    def _find_by_source_id(self, source_id: str) -> dict | None:
        if not source_id:
            return None
        for meta_path in self.meta_dir.glob("*.json"):
            meta = _read_json(meta_path)
            if not meta:
                continue
            if str(meta.get("source_id") or "") == source_id:
                return meta
        return None


def _paper_id(doc_id: str) -> str:
    return f"user:{doc_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trash_until(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _make_meta(
    *,
    doc_id: str,
    title: str,
    source_name: str,
    source_path: str,
    text_path: str,
    status: str,
    source: str,
    source_id: str,
    char_count: int,
    created_at: str | None = None,
) -> dict:
    now = _now_iso()
    return {
        "doc_id": doc_id,
        "title": title,
        "source_name": source_name,
        "source_path": source_path,
        "text_path": text_path,
        "status": status,
        "created_at": created_at or now,
        "updated_at": now,
        "trash_until": "",
        "source": source,
        "source_id": source_id,
        "char_count": int(char_count or 0),
    }


def _record_from_meta(meta: dict) -> UserDocRecord:
    return UserDocRecord(
        doc_id=str(meta.get("doc_id") or ""),
        title=str(meta.get("title") or ""),
        source_name=str(meta.get("source_name") or ""),
        source_path=str(meta.get("source_path") or ""),
        text_path=str(meta.get("text_path") or ""),
        status=str(meta.get("status") or ""),
        created_at=str(meta.get("created_at") or ""),
        updated_at=str(meta.get("updated_at") or ""),
        trash_until=str(meta.get("trash_until") or ""),
        source=str(meta.get("source") or ""),
        source_id=str(meta.get("source_id") or ""),
        char_count=int(meta.get("char_count") or 0),
    )


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _count_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _derive_title(text: str, fallback: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return fallback or "自动生成文档"
    first = re.sub(r"^#+\s*", "", lines[0]).strip()
    return first or fallback or "自动生成文档"


def _extract_text(path: Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    if os.environ.get("WA_USE_RUST_ENGINE") == "1":
        try:
            from writing_agent.v2.rust_bridge import try_rust_import
            rust_text = try_rust_import(p)
            if rust_text:
                return rust_text
        except Exception:
            pass
    suffix = p.suffix.lower()
    if suffix in {".doc", ".docx"}:
        p = prepare_template_file(p)
        suffix = p.suffix.lower()
    if suffix == ".docx":
        try:
            return _extract_docx_text(p)
        except Exception:
            from writing_agent.v2.template_parse import _convert_doc_to_docx

            converted = _convert_doc_to_docx(p, force=True)
            if converted and converted.exists():
                try:
                    return _extract_docx_text(converted)
                except Exception:
                    return ""
            return ""
    if suffix in {".odt", ".rtf"}:
        converted = _convert_text_doc_to_docx(p)
        if converted and converted.exists():
            try:
                return _extract_docx_text(converted)
            except Exception:
                return ""
        return ""
    if suffix == ".pdf":
        return extract_pdf_text(p, max_pages=24)
    if suffix in {".txt", ".md"}:
        return p.read_text(encoding="utf-8", errors="replace")
    if suffix in {".html", ".htm"}:
        html = p.read_text(encoding="utf-8", errors="replace")
        txt = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", txt).strip()
    return p.read_text(encoding="utf-8", errors="replace")


def _convert_text_doc_to_docx(path: Path) -> Path | None:
    exe = _find_converter()
    if not exe:
        return None
    fd, final_name = tempfile.mkstemp(prefix="wa_convert_", suffix=".docx")
    os.close(fd)
    Path(final_name).unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="wa_convert_") as tmpdir:
        out_dir = Path(tmpdir)
        out_path = out_dir / f"{path.stem}.docx"
        if _convert_with_soffice(exe, path, out_dir) and out_path.exists():
            shutil.copyfile(out_path, final_name)
            return Path(final_name)
        if _convert_with_pandoc(exe, path, Path(final_name)) and Path(final_name).exists():
            return Path(final_name)
        return None


def _find_converter() -> str | None:
    hardcoded = [
        Path(r"D:\tools\pandoc\pandoc.exe"),
        Path(r"D:\tools\pandoc\pandoc"),
    ]
    for candidate in hardcoded:
        if candidate.exists():
            return str(candidate)
    base = Path(r"D:\tools\pandoc")
    if base.exists():
        for candidate in base.glob("**/pandoc.exe"):
            if candidate.exists():
                return str(candidate)
    for name in ("soffice", "soffice.exe", "libreoffice", "pandoc", "pandoc.exe"):
        exe = shutil.which(name)
        if exe:
            return exe
    return None


def _convert_with_soffice(exe: str, src: Path, out_dir: Path) -> bool:
    if "soffice" not in exe.lower() and "libreoffice" not in exe.lower():
        return False
    try:
        proc = subprocess.run(
            [exe, "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(src)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _convert_with_pandoc(exe: str, src: Path, out_path: Path) -> bool:
    if "pandoc" not in exe.lower():
        return False
    try:
        proc = subprocess.run(
            [exe, "-o", str(out_path), str(src)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _extract_docx_text(path: Path) -> str:
    doc = Document(str(path))
    lines: list[str] = []
    body = doc.element.body  # type: ignore[attr-defined]
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            p = Paragraph(child, doc)
            txt = (p.text or "").strip()
            if txt:
                lines.append(txt)
        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        txt = (p.text or "").strip()
                        if txt:
                            lines.append(txt)
    return "\n".join(lines).strip()
