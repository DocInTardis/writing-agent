use crate::{Block, Document, Inline};
use printpdf::{PdfDocument, Mm, IndirectFontRef};

#[derive(thiserror::Error, Debug)]
pub enum PdfErrorWrapper {
    #[error("pdf build failed: {0}")]
    Build(String),
}

pub fn export_pdf_bytes(doc: &Document) -> Result<Vec<u8>, PdfErrorWrapper> {
    let (mut pdf, page1, layer1) = PdfDocument::new("Writing Agent", Mm(210.0), Mm(297.0), "Layer 1");
    let layer = pdf.get_page(page1).get_layer(layer1);
    let font = load_default_font(&mut pdf)?;
    let mut cursor_y = 280.0f32;
    for block in &doc.blocks {
        let text = block_text(block);
        if text.is_empty() {
            cursor_y -= 6.0;
            continue;
        }
        for line in text.lines() {
            layer.use_text(line, 12.0, Mm(20.0), Mm(cursor_y), &font);
            cursor_y -= 6.0;
            if cursor_y < 20.0 {
                break;
            }
        }
        cursor_y -= 4.0;
        if cursor_y < 20.0 {
            break;
        }
    }
    let mut buf = std::io::BufWriter::new(Vec::new());
    pdf.save(&mut buf).map_err(|e| PdfErrorWrapper::Build(format!("{:?}", e)))?;
    Ok(buf.into_inner().map_err(|e| PdfErrorWrapper::Build(e.to_string()))?)
}

fn load_default_font(pdf: &mut printpdf::PdfDocumentReference) -> Result<IndirectFontRef, PdfErrorWrapper> {
    if let Ok(path) = std::env::var("WA_FONT_PATH") {
        if let Ok(bytes) = std::fs::read(&path) {
            return pdf.add_external_font(std::io::Cursor::new(bytes))
                .map_err(|e| PdfErrorWrapper::Build(format!("{:?}", e)));
        }
    }
    let candidates = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\msyh.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ];
    for path in candidates {
        if let Ok(bytes) = std::fs::read(path) {
            if let Ok(font) = pdf.add_external_font(std::io::Cursor::new(bytes)) {
                return Ok(font);
            }
        }
    }
    Err(PdfErrorWrapper::Build("font not found".to_string()))
}

fn block_text(block: &Block) -> String {
    match block {
        Block::Heading { content, .. } | Block::Paragraph { content, .. } => inline_text(content),
        Block::List { items, .. } => items
            .iter()
            .map(|i| inline_text(&i.content))
            .collect::<Vec<_>>()
            .join("\n"),
        Block::Quote { content, .. } => content
            .iter()
            .map(|b| match b {
                Block::Paragraph { content, .. } => inline_text(content),
                _ => String::new(),
            })
            .collect::<Vec<_>>()
            .join("\n"),
        Block::Code { code, .. } => code.as_ref().to_string(),
        Block::Table { rows, .. } => rows
            .iter()
            .map(|r| r.iter().map(|c| inline_text(&c.content)).collect::<Vec<_>>().join(" | "))
            .collect::<Vec<_>>()
            .join("\n"),
        Block::Figure { caption, .. } => caption.as_ref().map(|c| c.as_ref()).unwrap_or("").to_string(),
    }
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
