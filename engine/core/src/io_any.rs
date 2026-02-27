use crate::{import_markdown, Block, Document, Inline, StringInterner};
#[cfg(feature = "export_docx")]
use crate::{export_docx_bytes as export_docx_native, export_pdf_bytes as export_pdf_native};
use std::sync::Arc;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug)]
pub enum ImportError {
    Io(String),
    Unsupported(String),
}

pub fn import_any(path: &Path) -> Result<Document, ImportError> {
    let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_lowercase();
    match ext.as_str() {
        "md" | "markdown" => {
            let raw = read_text(path)?;
            Ok(import_markdown(&raw))
        }
        "txt" => {
            let raw = read_text(path)?;
            Ok(import_plaintext(&raw))
        }
        "html" | "htm" => {
            let raw = read_text(path)?;
            Ok(import_html(&raw))
        }
        "json" => {
            let raw = read_text(path)?;
            super::import_json(&raw).map_err(|e| ImportError::Io(e.to_string()))
        }
        "docx" | "doc" | "odt" | "rtf" | "pdf" => {
            let text = extract_via_python(path)?;
            Ok(import_plaintext(&text))
        }
        _ => {
            let text = extract_via_python(path).unwrap_or_default();
            if text.trim().is_empty() {
                Err(ImportError::Unsupported(ext))
            } else {
                Ok(import_plaintext(&text))
            }
        }
    }
}

fn extract_via_python(path: &Path) -> Result<String, ImportError> {
    let root = project_root();
    let script = root.join("engine").join("tools").join("extract_text.py");
    let output = Command::new("python")
        .arg(script)
        .arg(path)
        .output()
        .map_err(|e| ImportError::Io(e.to_string()))?;
    if !output.status.success() {
        return Err(ImportError::Io(String::from_utf8_lossy(&output.stderr).to_string()));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn read_text(path: &Path) -> Result<String, ImportError> {
    std::fs::read_to_string(path).map_err(|e| ImportError::Io(e.to_string()))
}

pub fn import_plaintext(raw: &str) -> Document {
    let mut doc = Document::new();
    let mut blocks = Vec::new();
    let mut buf = Vec::new();
    let mut interner = StringInterner::new();

    for line in raw.lines() {
        if line.trim().is_empty() {
            flush_para(&mut blocks, &mut buf, &mut interner);
            continue;
        }
        buf.push(line.to_string());
    }
    flush_para(&mut blocks, &mut buf, &mut interner);

    if blocks.is_empty() {
        blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: vec![Inline::Text { value: interner.intern(raw.trim()) }],
            dirty: false,
        });
    }
    doc.blocks = blocks;
    doc
}

fn flush_para(blocks: &mut Vec<Block>, buf: &mut Vec<String>, interner: &mut StringInterner) {
    if buf.is_empty() {
        return;
    }
    let text = buf.join("\n").trim().to_string();
    if !text.is_empty() {
        blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: vec![Inline::Text { value: interner.intern(&text) }],
            dirty: false,
        });
    }
    buf.clear();
}


pub fn import_html(raw: &str) -> Document {
    let mut doc = Document::new();
    let mut blocks = Vec::new();
    let mut current: Vec<Inline> = Vec::new();
    let mut interner = StringInterner::new();
    for inline in parse_html_inlines(raw) {
        match inline {
            Inline::Text { value } if value.as_ref() == "
" => {
                if !current.is_empty() {
                    blocks.push(Block::Paragraph {
                        id: uuid::Uuid::new_v4(),
                        content: std::mem::take(&mut current),
                        dirty: false,
                    });
                }
            }
            Inline::Text { value } if value.as_ref().contains('\n') => {
                let parts = value.as_ref().split('\n');
                for (idx, part) in parts.enumerate() {
                    if !part.is_empty() {
                        current.push(Inline::Text { value: interner.intern(part) });
                    }
                    if idx != 0 {
                        if !current.is_empty() {
                            blocks.push(Block::Paragraph {
                                id: uuid::Uuid::new_v4(),
                                content: std::mem::take(&mut current),
                                dirty: false,
                            });
                        }
                    }
                }
            }
            other => current.push(other),
        }
    }
    if !current.is_empty() {
        blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: current,
            dirty: false,
        });
    }
    if blocks.is_empty() {
        blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: vec![Inline::Text { value: interner.intern(raw.trim()) }],
            dirty: false,
        });
    }
    doc.blocks = blocks;
    doc
}

// Basic rich HTML import (tables/lists/images). Best-effort.
pub fn import_html_rich(raw: &str) -> Document {
    let lower = raw.to_lowercase();
    if lower.contains("<table") {
        return import_html_table(raw);
    }
    if lower.contains("<ul") || lower.contains("<ol") || lower.contains("<li") {
        return import_html_list(raw);
    }
    if lower.contains("<img") {
        return import_html_image(raw);
    }
    import_html(raw)
}

fn import_html_table(raw: &str) -> Document {
    let mut doc = Document::new();
    let mut rows = Vec::new();
    for tr in raw.split("<tr").skip(1) {
        let mut row = Vec::new();
        for td in tr.split("<td").skip(1) {
            let inlines = parse_html_inlines(td);
            let content = if inlines.is_empty() {
                vec![Inline::Text { value: Arc::from(strip_html(td)) }]
            } else {
                inlines
            };
            row.push(crate::Cell { content });
        }
        if !row.is_empty() {
            rows.push(row);
        }
    }
    if !rows.is_empty() {
        doc.blocks.push(Block::Table {
            id: uuid::Uuid::new_v4(),
            rows,
            dirty: false,
        });
    } else {
        doc = import_html(raw);
    }
    doc
}

fn import_html_list(raw: &str) -> Document {
    let mut doc = Document::new();
    let mut items = Vec::new();
    for li in raw.split("<li").skip(1) {
        let inlines = parse_html_inlines(li);
        let text = strip_html(li);
        if !text.trim().is_empty() || !inlines.is_empty() {
            items.push(crate::ListItem {
                id: uuid::Uuid::new_v4(),
                content: if inlines.is_empty() {
                    vec![Inline::Text { value: Arc::from(text.trim()) }]
                } else {
                    inlines
                },
            });
        }
    }
    if !items.is_empty() {
        doc.blocks.push(Block::List {
            id: uuid::Uuid::new_v4(),
            ordered: raw.to_lowercase().contains("<ol"),
            items,
            dirty: false,
        });
    } else {
        doc = import_html(raw);
    }
    doc
}

fn import_html_image(raw: &str) -> Document {
    let mut doc = Document::new();
    let lower = raw.to_lowercase();
    let mut url = None;
    if let Some(idx) = lower.find("src=") {
        let tail = &raw[idx + 4..];
        let quote = tail.chars().next().unwrap_or('"');
        let rest = if quote == '"' || quote == '\'' { &tail[1..] } else { tail };
        if let Some(end) = rest.find(quote) {
            url = Some(rest[..end].to_string());
        }
    }
    if let Some(u) = url {
        doc.blocks.push(Block::Figure {
            id: uuid::Uuid::new_v4(),
            url: Arc::from(u),
            caption: Some(Arc::from("图片")),
            size: None,
            dirty: false,
        });
    } else {
        doc = import_html(raw);
    }
    doc
}

fn parse_html_inlines(html: &str) -> Vec<Inline> {
    let mut out = Vec::new();
    let mut bold = false;
    let mut italic = false;
    let mut underline = false;
    let mut strikethrough = false;
    let mut buf = String::new();
    let mut chars = html.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == '<' {
            if !buf.is_empty() {
                push_styled(&mut out, &mut buf, bold, italic, underline, strikethrough);
            }
            let mut tag = String::new();
            while let Some(c) = chars.next() {
                if c == '>' { break; }
                tag.push(c);
            }
            let t = tag.trim().to_lowercase();
            match t.as_str() {
                "b" | "strong" => bold = true,
                "/b" | "/strong" => bold = false,
                "i" | "em" => italic = true,
                "/i" | "/em" => italic = false,
                "u" => underline = true,
                "/u" => underline = false,
                "s" | "strike" | "del" => strikethrough = true,
                "/s" | "/strike" | "/del" => strikethrough = false,
                "br" | "br/" | "/p" | "p" => {
                    if !buf.is_empty() {
                        push_styled(&mut out, &mut buf, bold, italic, underline, strikethrough);
                    }
                    out.push(Inline::Text { value: Arc::from("\n") });
                }
                _ => {}
            }
        } else {
            buf.push(ch);
        }
    }
    if !buf.is_empty() {
        push_styled(&mut out, &mut buf, bold, italic, underline, strikethrough);
    }
    out
}

fn push_styled(out: &mut Vec<Inline>, buf: &mut String, bold: bool, italic: bool, underline: bool, strikethrough: bool) {
    let text = std::mem::take(buf);
    if bold || italic || underline || strikethrough {
        out.push(Inline::Styled {
            style: crate::Style { bold, italic, underline, strikethrough },
            content: vec![Inline::Text { value: Arc::from(text) }],
        });
    } else {
        out.push(Inline::Text { value: Arc::from(text) });
    }
}

#[allow(dead_code)]
fn strip_html(html: &str) -> String {
    let mut out = String::new();
    let mut in_tag = false;
    for ch in html.chars() {
        match ch {
            '<' => in_tag = true,
            '>' => in_tag = false,
            _ => {
                if !in_tag {
                    out.push(ch);
                }
            }
        }
    }
    out.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap_or(Path::new("."))
        .to_path_buf()
}

#[cfg(feature = "export_docx")]
pub fn export_docx(doc: &Document, out_path: &Path) -> Result<(), ImportError> {
    let payload = export_docx_native(doc).map_err(|e| ImportError::Io(e.to_string()))?;
    std::fs::write(out_path, payload).map_err(|e| ImportError::Io(e.to_string()))
}

#[cfg(feature = "export_docx")]
pub fn export_pdf(doc: &Document, out_path: &Path) -> Result<(), ImportError> {
    let payload = export_pdf_native(doc).map_err(|e| ImportError::Io(e.to_string()))?;
    std::fs::write(out_path, payload).map_err(|e| ImportError::Io(e.to_string()))
}
