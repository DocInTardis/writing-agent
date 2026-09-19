use std::sync::Arc;
use wa_core::{Block, Document, Inline};
use wa_engine::{ImageCache, LayoutCache, LayoutConfig, LayoutEngine};

#[test]
fn layout_paged_vs_scroll() {
    let mut doc = Document::new();
    doc.blocks.push(Block::Paragraph {
        id: uuid::Uuid::new_v4(),
        content: vec![Inline::Text {
            value: Arc::from("测试分页与滚动布局"),
        }],
        dirty: false,
    });
    let mut engine = LayoutEngine::new();

    let config_paged = LayoutConfig {
        paged: true,
        ..LayoutConfig::default()
    };
    let config_scroll = LayoutConfig {
        paged: false,
        ..LayoutConfig::default()
    };

    let paged = engine.layout(&doc, &config_paged);
    let scroll = engine.layout(&doc, &config_scroll);

    assert!(!paged.pages.is_empty());
    assert!(!scroll.pages.is_empty());
}

#[test]
fn image_cache_basic() {
    let mut cache = ImageCache::new();
    let a = cache.load("local://a");
    let b = cache.load("local://a");
    assert_eq!(a.key, b.key);
}

#[test]
fn layout_cache_reuse() {
    let mut doc = Document::new();
    doc.blocks.push(Block::Paragraph {
        id: uuid::Uuid::new_v4(),
        content: vec![Inline::Text {
            value: Arc::from("缓存复用测试"),
        }],
        dirty: false,
    });
    let mut engine = LayoutEngine::new();
    let mut cache = LayoutCache::new();
    let config = LayoutConfig::default();
    let first = engine.layout_cached(&doc, &config, &mut cache);
    let second = engine.layout_cached(&doc, &config, &mut cache);
    assert_eq!(first.pages.len(), second.pages.len());
}

#[test]
fn cjk_forbidden_line_start_end() {
    fn is_forbidden_start(ch: char) -> bool {
        matches!(
            ch,
            '，' | '。'
                | '！'
                | '？'
                | '；'
                | '：'
                | '、'
                | '）'
                | '】'
                | '》'
                | '〉'
                | '」'
                | '』'
                | '”'
                | '’'
                | ','
                | '.'
                | '!'
                | '?'
                | ';'
                | ':'
                | ')'
                | ']'
                | '}'
        )
    }
    fn is_forbidden_end(ch: char) -> bool {
        matches!(
            ch,
            '（' | '【'
                | '《'
                | '〈'
                | '「'
                | '『'
                | '“'
                | '‘'
                | '〔'
                | '［'
                | '｛'
                | '('
                | '['
                | '{'
        )
    }

    let mut doc = Document::new();
    doc.blocks.push(Block::Paragraph {
        id: uuid::Uuid::new_v4(),
        content: vec![Inline::Text {
            value: Arc::from("测试（禁则），应该避免行首标点。"),
        }],
        dirty: false,
    });
    let mut engine = LayoutEngine::new();
    let config = LayoutConfig {
        page_width: 180.0,
        page_height: 300.0,
        margin: 10.0,
        ..LayoutConfig::default()
    };
    let layout = engine.layout(&doc, &config);
    for page in layout.pages {
        for block in page.blocks {
            for line in &block.lines {
                let text = line.text.trim();
                if text.is_empty() {
                    continue;
                }
                let first = text.chars().next().unwrap();
                let last = text.chars().last().unwrap();
                assert!(
                    !is_forbidden_start(first),
                    "line starts with forbidden: {}",
                    text
                );
                assert!(
                    !is_forbidden_end(last),
                    "line ends with forbidden: {}",
                    text
                );
            }
        }
    }
}

#[test]
fn long_paragraph_splits_across_pages_without_splitting_the_document() {
    let mut doc = Document::new();
    let block_id = uuid::Uuid::new_v4();
    doc.blocks.push(Block::Paragraph {
        id: block_id,
        content: vec![Inline::Text { value: Arc::from("分页正文".repeat(500)) }],
        dirty: false,
    });
    let mut engine = LayoutEngine::new();
    let config = LayoutConfig {
        page_width: 180.0,
        page_height: 140.0,
        margin: 10.0,
        ..LayoutConfig::default()
    };
    let layout = engine.layout(&doc, &config);
    assert!(layout.pages.len() > 1);
    assert!(layout.pages.iter().all(|page| page.blocks.iter().all(|block| block.block_id == block_id)));
}

#[test]
fn explicit_page_break_starts_target_block_on_new_page() {
    let mut doc = Document::new();
    let first = uuid::Uuid::new_v4();
    let second = uuid::Uuid::new_v4();
    for id in [first, second] {
        doc.blocks.push(Block::Paragraph {
            id,
            content: vec![Inline::Text { value: Arc::from("短段落") }],
            dirty: false,
        });
    }
    let mut config = LayoutConfig::default();
    config.force_page_break_before.insert(second);
    let mut engine = LayoutEngine::new();
    let layout = engine.layout(&doc, &config);
    assert_eq!(layout.pages.len(), 2);
    assert_eq!(layout.pages[1].blocks[0].block_id, second);
}
