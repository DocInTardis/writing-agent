//! Repeatable 20/100/300-page layout baseline without a browser or network.

use std::sync::Arc;
use std::time::Instant;
use wa_core::{Block, Document, Inline};
use wa_engine::{LayoutCache, LayoutConfig, LayoutEngine};

fn document_for_pages(pages: usize) -> Document {
    let mut document = Document::new();
    // Ten thesis-like paragraphs per target page. The actual result is reported
    // rather than assumed, so font or layout changes remain visible.
    for index in 0..pages * 10 {
        document.blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: vec![Inline::Text {
                value: Arc::from(format!(
                    "第{}段。本文用于测量中文长文档在分页、缓存复用和局部修改后的布局成本。{}",
                    index + 1,
                    "研究方法、实验结果与讨论内容。".repeat(12)
                )),
            }],
            dirty: false,
        });
    }
    document
}

fn main() {
    for requested_pages in [20usize, 100, 300] {
        let mut document = document_for_pages(requested_pages);
        let mut engine = LayoutEngine::new();
        let mut cache = LayoutCache::new();
        let config = LayoutConfig::default();

        let cold_started = Instant::now();
        let cold = engine.layout_cached(&document, &config, &mut cache);
        let cold_ms = cold_started.elapsed().as_secs_f64() * 1000.0;

        let warm_started = Instant::now();
        let warm = engine.layout_cached(&document, &config, &mut cache);
        let warm_ms = warm_started.elapsed().as_secs_f64() * 1000.0;

        let middle = document.blocks.len() / 2;
        if let Some(Block::Paragraph { content, dirty, .. }) = document.blocks.get_mut(middle) {
            content.push(Inline::Text { value: Arc::from("局部修改") });
            *dirty = true;
        }
        let incremental_started = Instant::now();
        let incremental = engine.layout_cached(&document, &config, &mut cache);
        let incremental_ms = incremental_started.elapsed().as_secs_f64() * 1000.0;

        println!(
            "{{\"requestedPages\":{},\"actualPages\":{},\"blocks\":{},\"coldMs\":{:.3},\"warmMs\":{:.3},\"incrementalMs\":{:.3},\"stablePageCount\":{}}}",
            requested_pages,
            cold.pages.len(),
            document.blocks.len(),
            cold_ms,
            warm_ms,
            incremental_ms,
            warm.pages.len() == incremental.pages.len()
        );
    }
}
