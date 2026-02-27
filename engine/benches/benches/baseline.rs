use criterion::{criterion_group, criterion_main, Criterion, BatchSize};
use wa_core::{Block, Document, Inline, DiffEngine, Editor, EditorCommand, export_json_into, export_json_to_file};
use std::sync::Arc;
use wa_engine::{FontMetrics, LayoutCache, LayoutConfig, LayoutEngine, RealMeasurer, TextMeasurer};

fn build_large_doc(blocks: usize, lines: usize) -> Document {
    let mut doc = Document::new();
    for i in 0..blocks {
        let mut text = String::new();
        for _ in 0..lines {
            text.push_str("这是一些测试文本，用于布局性能评估。\n");
        }
        doc.blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: vec![Inline::Text { value: Arc::from(format!("{} {}", i, text)) }],
            dirty: false,
        });
    }
    doc
}

fn build_multilang_doc(blocks: usize) -> Document {
    let mut doc = Document::new();
    let sample = "Hello 世界 مرحبا Привет 12345 — テスト입니다.\n";
    for i in 0..blocks {
        doc.blocks.push(Block::Paragraph {
            id: uuid::Uuid::new_v4(),
            content: vec![Inline::Text { value: Arc::from(format!("{} {}", i, sample.repeat(3))) }],
            dirty: false,
        });
    }
    doc
}

fn layout_blocks(c: &mut Criterion) {
    let mut engine = LayoutEngine::new();
    let doc = build_large_doc(200, 5);
    let config = LayoutConfig::default();
    c.bench_function("layout_blocks", |b| b.iter(|| engine.layout(&doc, &config)));
}

fn layout_blocks_cached(c: &mut Criterion) {
    let mut engine = LayoutEngine::new();
    let doc = build_large_doc(200, 5);
    let config = LayoutConfig::default();
    let mut cache = LayoutCache::new();
    c.bench_function("layout_blocks_cached", |b| b.iter(|| engine.layout_cached(&doc, &config, &mut cache)));
}

fn render_frame(c: &mut Criterion) {
    let mut engine = LayoutEngine::new();
    let doc = build_large_doc(100, 3);
    let config = LayoutConfig::default();
    let layout = engine.layout(&doc, &config);
    c.bench_function("render_frame_sim", |b| {
        b.iter(|| {
            let mut count = 0usize;
            for page in &layout.pages {
                for block in &page.blocks {
                    count += block.lines.len();
                }
            }
            count
        })
    });
}

criterion_group!(benches, layout_blocks, layout_blocks_cached, render_frame, render_visible_sim, serialize_json, serialize_json_file, layout_1000_chars, diff_10k_blocks_1_changed, typing_latency, scroll_10k_lines, shape_1000_chars, undo_100_ops, layout_10k_lines_block, measure_10k_words);
criterion_main!(benches);

fn serialize_json(c: &mut Criterion) {
    let doc = build_large_doc(200, 5);
    let mut buf = Vec::with_capacity(64 * 1024);
    c.bench_function("serialize_json", |b| {
        b.iter(|| {
            export_json_into(&doc, &mut buf).unwrap();
        })
    });
}

fn serialize_json_file(c: &mut Criterion) {
    let doc = build_large_doc(200, 5);
    let path = std::path::Path::new("target/tmp_bench.json");
    std::fs::create_dir_all("target").unwrap();
    c.bench_function("serialize_json_file", |b| {
        b.iter(|| {
            export_json_to_file(&doc, path).unwrap();
        })
    });
}

fn layout_1000_chars(c: &mut Criterion) {
    let mut doc = Document::new();
    let text = "字".repeat(1000);
    doc.blocks.push(Block::Paragraph {
        id: uuid::Uuid::new_v4(),
        content: vec![Inline::Text { value: Arc::from(text) }],
        dirty: false,
    });
    let mut engine = LayoutEngine::new();
    let config = LayoutConfig::default();
    c.bench_function("layout_1000_chars", |b| b.iter(|| engine.layout(&doc, &config)));
}

fn layout_10k_lines_block(c: &mut Criterion) {
    let mut doc = Document::new();
    let mut text = String::new();
    for _ in 0..10_000 {
        text.push_str("line\n");
    }
    doc.blocks.push(Block::Paragraph {
        id: uuid::Uuid::new_v4(),
        content: vec![Inline::Text { value: Arc::from(text) }],
        dirty: false,
    });
    let mut engine = LayoutEngine::new();
    let config = LayoutConfig::default();
    c.bench_function("layout_10k_lines_block", |b| b.iter(|| engine.layout(&doc, &config)));
}

fn measure_10k_words(c: &mut Criterion) {
    let measurer = RealMeasurer::new();
    let metrics = FontMetrics::default();
    let text = "word ".repeat(10_000);
    c.bench_function("measure_10k_words", |b| b.iter(|| measurer.measure(&text, metrics)));
}

fn diff_10k_blocks_1_changed(c: &mut Criterion) {
    let mut doc = build_large_doc(10000, 1);
    let mut diff = DiffEngine::new();
    let _ = diff.incremental_diff(&doc);
    if let Some(block) = doc.blocks.get_mut(5000) {
        if let Block::Paragraph { content, dirty, .. } = block {
            content.push(Inline::Text { value: Arc::from("x") });
            *dirty = true;
        }
    }
    c.bench_function("diff_10k_blocks_1_changed", |b| b.iter(|| diff.incremental_diff(&doc)));
}

fn typing_latency(c: &mut Criterion) {
    let doc = Document::new();
    let mut editor = Editor::new(doc);
    c.bench_function("typing_latency", |b| {
        b.iter(|| {
            editor.execute(EditorCommand::InsertText("测试".to_string()));
        })
    });
}

fn render_visible_sim(c: &mut Criterion) {
    let mut engine = LayoutEngine::new();
    let doc = build_large_doc(200, 5);
    let config = LayoutConfig::default();
    let layout = engine.layout(&doc, &config);
    c.bench_function("render_visible_sim", |b| {
        b.iter(|| {
            let mut count = 0usize;
            if let Some(page) = layout.pages.first() {
                for block in &page.blocks {
                    count += block.lines.len();
                }
            }
            count
        })
    });
}

fn scroll_10k_lines(c: &mut Criterion) {
    let mut engine = LayoutEngine::new();
    let doc = build_large_doc(10000, 1);
    let mut config = LayoutConfig::default();
    config.paged = false;
    let layout = engine.layout(&doc, &config);
    let total = layout.pages.first().map(|p| p.blocks.len()).unwrap_or(0);
    c.bench_function("scroll_10k_lines", |b| {
        let mut idx = 0usize;
        b.iter(|| {
            if total == 0 {
                return 0usize;
            }
            let start = idx % total;
            let end = (start + 50).min(total);
            let mut count = 0usize;
            for block in &layout.pages[0].blocks[start..end] {
                count += block.lines.len();
            }
            idx = idx.wrapping_add(37);
            count
        })
    });
}

fn shape_1000_chars(c: &mut Criterion) {
    let text = "字".repeat(1000);
    let measurer = RealMeasurer::new();
    let metrics = FontMetrics::default();
    c.bench_function("shape_1000_chars", |b| {
        b.iter(|| measurer.measure(&text, metrics))
    });
}


fn undo_100_ops(c: &mut Criterion) {
    c.bench_function("undo_100_ops", |b| {
        b.iter_batched(
            || {
                let doc = Document::new();
                let mut editor = Editor::new(doc);
                for _ in 0..100 {
                    editor.execute(EditorCommand::InsertText("?".to_string()));
                }
                editor
            },
            |mut editor| {
                for _ in 0..100 {
                    editor.execute(EditorCommand::Undo);
                }
            },
            BatchSize::SmallInput,
        )
    });
}
