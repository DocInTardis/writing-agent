use wa_core::{Block, Document, Inline};
use std::sync::Arc;

#[global_allocator]
static ALLOC: dhat::Alloc = dhat::Alloc;

fn main() {
    let _profiler = dhat::Profiler::new_heap();
    let mut doc = Document::new();
    for i in 0..2000 {
        let text = format!("段落 {}: {}", i, "测试".repeat(10));
        doc.blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: vec![Inline::Text { value: Arc::from(text) }],
            dirty: false,
        });
    }
    let _ = serde_json::to_string(&doc).unwrap();
}
