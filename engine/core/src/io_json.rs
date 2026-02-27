use crate::{Block, Document};
use serde_json::Value;

pub fn export_json(doc: &Document) -> serde_json::Result<String> {
    serde_json::to_string_pretty(doc)
}

pub fn export_json_into(doc: &Document, buf: &mut Vec<u8>) -> serde_json::Result<()> {
    buf.clear();
    let target = doc.blocks.len().saturating_mul(128) + 256;
    if buf.capacity() < target {
        buf.reserve(target - buf.capacity());
    }
    serde_json::to_writer(buf, doc)?;
    Ok(())
}

pub fn export_json_fast(doc: &Document) -> serde_json::Result<String> {
    let mut buf = Vec::with_capacity(doc.blocks.len().saturating_mul(128) + 256);
    export_json_into(doc, &mut buf)?;
    Ok(unsafe { String::from_utf8_unchecked(buf) })
}

pub fn export_json_to_file(doc: &Document, path: &std::path::Path) -> serde_json::Result<()> {
    let file = std::fs::File::create(path)
        .map_err(serde_json::Error::io)?;
    let mut writer = std::io::BufWriter::new(file);
    serde_json::to_writer(&mut writer, doc)?;
    Ok(())
}

pub fn import_json(raw: &str) -> serde_json::Result<Document> {
    serde_json::from_str(raw)
}

pub fn upgrade_unknown_fields(raw: &Value) -> Value {
    raw.clone()
}

pub fn sanitize_doc(mut doc: Document) -> Document {
    for block in doc.blocks.iter_mut() {
        match block {
            Block::Heading { dirty, .. }
            | Block::Paragraph { dirty, .. }
            | Block::List { dirty, .. }
            | Block::Quote { dirty, .. }
            | Block::Code { dirty, .. }
            | Block::Table { dirty, .. }
            | Block::Figure { dirty, .. } => {
                *dirty = false;
            }
        }
    }
    doc
}
