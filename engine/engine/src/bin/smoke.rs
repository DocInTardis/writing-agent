use wa_core::{Block, Document, Inline};
use std::sync::Arc;
use wa_engine::{LayoutConfig, LayoutEngine};

fn main() {
    let mut doc = Document::new();
    doc.blocks.push(Block::Paragraph {
        id: uuid::Uuid::new_v4(),
        content: vec![Inline::Text { value: Arc::from("smoke test") }],
        dirty: true,
    });
    let mut engine = LayoutEngine::new();
    let config = LayoutConfig::default();
    let _layout = engine.layout(&doc, &config);
}
