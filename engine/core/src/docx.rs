use crate::{Block, Document, Inline};
use docx_rs::{Docx, Paragraph, Run};

#[derive(thiserror::Error, Debug)]
pub enum DocxError {
    #[error("docx build failed: {0}")]
    Build(String),
}

pub fn export_docx_bytes(doc: &Document) -> Result<Vec<u8>, DocxError> {
    let mut docx = Docx::new();
    for block in &doc.blocks {
        match block {
            Block::Heading { level, content, .. } => {
                let text = inline_text(content);
                let style = match level {
                    1 => "Heading1",
                    2 => "Heading2",
                    3 => "Heading3",
                    _ => "Heading1",
                };
                let para = Paragraph::new().add_run(Run::new().add_text(text)).style(style);
                docx = docx.add_paragraph(para);
            }
            Block::Paragraph { content, .. } => {
                let text = inline_text(content);
                docx = docx.add_paragraph(Paragraph::new().add_run(Run::new().add_text(text)));
            }
            Block::List { ordered, items, .. } => {
                for (idx, item) in items.iter().enumerate() {
                    let text = inline_text(&item.content);
                    let prefix = if *ordered { format!("{}. ", idx + 1) } else { "- ".to_string() };
                    docx = docx.add_paragraph(Paragraph::new().add_run(Run::new().add_text(prefix + &text)));
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
                docx = docx.add_paragraph(Paragraph::new().add_run(Run::new().add_text(text)));
            }
            Block::Code { code, .. } => {
                let text = code.as_ref().to_string();
                docx = docx.add_paragraph(Paragraph::new().add_run(Run::new().add_text(text)));
            }
            Block::Table { rows, .. } => {
                for row in rows {
                    let row_text = row
                        .iter()
                        .map(|c| inline_text(&c.content))
                        .collect::<Vec<_>>()
                        .join(" | ");
                    docx = docx.add_paragraph(Paragraph::new().add_run(Run::new().add_text(row_text)));
                }
            }
            Block::Figure { caption, .. } => {
                let cap = caption.as_ref().map(|c| c.as_ref()).unwrap_or("图片");
                docx = docx.add_paragraph(Paragraph::new().add_run(Run::new().add_text(cap)));
            }
        }
    }
    let mut cursor = std::io::Cursor::new(Vec::new());
    docx.build()
        .pack(&mut cursor)
        .map_err(|e| DocxError::Build(e.to_string()))?;
    Ok(cursor.into_inner())
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
