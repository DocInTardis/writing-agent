use crate::{Block, Document, Inline, ListItem};
use std::sync::Arc;
use uuid::Uuid;

pub fn export_markdown(doc: &Document) -> String {
    let mut out = Vec::new();
    for block in &doc.blocks {
        match block {
            Block::Heading { level, content, .. } => {
                out.push(format!("{} {}", "#".repeat(*level as usize), inline_text(content)));
            }
            Block::Paragraph { content, .. } => {
                out.push(inline_text(content));
            }
            Block::List { ordered, items, .. } => {
                for (idx, item) in items.iter().enumerate() {
                    let prefix = if *ordered { format!("{}. ", idx + 1) } else { "- ".to_string() };
                    out.push(format!("{}{}", prefix, inline_text(&item.content)));
                }
            }
            Block::Quote { content, .. } => {
                let text = content
                    .iter()
                    .map(|b| match b {
                        Block::Paragraph { content, .. } => inline_text(content),
                        _ => String::new(),
                    })
                    .collect::<Vec<_>>()
                    .join(" ");
                out.push(format!("> {}", text));
            }
            Block::Code { lang, code, .. } => {
                out.push(format!("```{}", lang.as_ref()));
                out.push(code.as_ref().to_string());
                out.push("```".to_string());
            }
            Block::Table { rows, .. } => {
                for row in rows {
                    let row_text = row
                        .iter()
                        .map(|c| inline_text(&c.content))
                        .collect::<Vec<_>>()
                        .join(" | ");
                    out.push(format!("| {} |", row_text));
                }
            }
            Block::Figure { url, caption, .. } => {
                let cap = caption.as_ref().map(|c| c.as_ref()).unwrap_or("图");
                out.push(format!("![{}]({})", cap, url.as_ref()));
            }
        }
        out.push(String::new());
    }
    out.join("\n").trim().to_string()
}

pub fn import_markdown(md: &str) -> Document {
    let mut doc = Document::new();
    let mut blocks = Vec::new();
    let mut list_items: Vec<ListItem> = Vec::new();
    let mut list_ordered = false;
    let mut in_code = false;
    let mut code_lang = String::new();
    let mut code_buf = Vec::new();

    for raw in md.lines() {
        let line = raw.trim_end();
        if line.starts_with("```") {
            if in_code {
                blocks.push(Block::Code {
                    id: Uuid::new_v4(),
                    lang: Arc::from(code_lang.clone()),
                    code: Arc::from(code_buf.join("\n")),
                    dirty: false,
                });
                code_buf.clear();
                code_lang.clear();
                in_code = false;
            } else {
                in_code = true;
                code_lang = line.trim_start_matches("```").trim().to_string();
            }
            continue;
        }
        if in_code {
            code_buf.push(line.to_string());
            continue;
        }
        if let Some(h) = parse_heading(line) {
            flush_list(&mut blocks, &mut list_items, list_ordered);
            blocks.push(Block::Heading {
                id: Uuid::new_v4(),
                level: h.0,
                content: vec![Inline::Text { value: Arc::from(h.1) }],
                dirty: false,
            });
            continue;
        }
        if let Some(item) = parse_list(line) {
            list_ordered = item.0;
            list_items.push(ListItem {
                id: Uuid::new_v4(),
                content: vec![Inline::Text { value: Arc::from(item.1) }],
            });
            continue;
        }
        if line.starts_with('>') {
            flush_list(&mut blocks, &mut list_items, list_ordered);
            let text = line.trim_start_matches('>').trim();
            blocks.push(Block::Quote {
                id: Uuid::new_v4(),
                content: vec![Block::Paragraph {
                    id: Uuid::new_v4(),
                    content: vec![Inline::Text { value: Arc::from(text) }],
                    dirty: false,
                }],
                dirty: false,
            });
            continue;
        }
        if line.starts_with("![") && line.contains("](") && line.ends_with(')') {
            flush_list(&mut blocks, &mut list_items, list_ordered);
            if let Some((cap, url)) = parse_image(line) {
                blocks.push(Block::Figure {
                    id: Uuid::new_v4(),
                    url: Arc::from(url),
                    caption: Some(Arc::from(cap)),
                    size: None,
                    dirty: false,
                });
            }
            continue;
        }
        if line.starts_with('|') && line.ends_with('|') {
            flush_list(&mut blocks, &mut list_items, list_ordered);
            let cells = line
                .trim_matches('|')
                .split('|')
                .map(|c| crate::Cell {
                    content: vec![Inline::Text { value: Arc::from(c.trim()) }],
                })
                .collect::<Vec<_>>();
            blocks.push(Block::Table {
                id: Uuid::new_v4(),
                rows: vec![cells],
                dirty: false,
            });
            continue;
        }
        if line.trim().is_empty() {
            flush_list(&mut blocks, &mut list_items, list_ordered);
            continue;
        }
        flush_list(&mut blocks, &mut list_items, list_ordered);
        blocks.push(Block::Paragraph {
            id: Uuid::new_v4(),
            content: vec![Inline::Text { value: Arc::from(line) }],
            dirty: false,
        });
    }
    flush_list(&mut blocks, &mut list_items, list_ordered);
    doc.blocks = blocks;
    doc
}

fn flush_list(blocks: &mut Vec<Block>, items: &mut Vec<ListItem>, ordered: bool) {
    if items.is_empty() {
        return;
    }
    blocks.push(Block::List {
        id: Uuid::new_v4(),
        ordered,
        items: std::mem::take(items),
        dirty: false,
    });
}

fn parse_heading(line: &str) -> Option<(u8, String)> {
    let trimmed = line.trim();
    let level = trimmed.chars().take_while(|c| *c == '#').count();
    if level == 0 || level > 3 {
        return None;
    }
    let text = trimmed.trim_start_matches('#').trim();
    if text.is_empty() {
        return None;
    }
    Some((level as u8, text.to_string()))
}

fn parse_list(line: &str) -> Option<(bool, String)> {
    let trimmed = line.trim();
    if let Some(rest) = trimmed.strip_prefix("- ") {
        return Some((false, rest.to_string()));
    }
    if let Some(pos) = trimmed.find(". ") {
        let (num, rest) = trimmed.split_at(pos);
        if num.chars().all(|c| c.is_ascii_digit()) {
            return Some((true, rest.trim_start_matches(". ").to_string()));
        }
    }
    None
}

fn parse_image(line: &str) -> Option<(String, String)> {
    let cap_start = line.find("![")? + 2;
    let cap_end = line.find("](")?;
    let url_start = cap_end + 2;
    let url_end = line.rfind(')')?;
    let cap = line[cap_start..cap_end].to_string();
    let url = line[url_start..url_end].to_string();
    Some((cap, url))
}

fn inline_text(inlines: &[Inline]) -> String {
    let mut out = String::new();
    for inline in inlines {
        match inline {
            Inline::Text { value } => out.push_str(value.as_ref()),
            Inline::CodeSpan { value } => out.push_str(value.as_ref()),
            Inline::Link { text, .. } => out.push_str(&inline_text(text)),
            Inline::Styled { content, .. } => out.push_str(&inline_text(content)),
        }
    }
    out
}
