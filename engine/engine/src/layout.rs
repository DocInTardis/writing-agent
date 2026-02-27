use crate::{FontMetrics, LineBreaker, SharedMeasurer, RealMeasurer, ImageCache, LayoutCache, FontdueMeasurer};
use wa_core::{Block, Inline, Document};
use uuid::Uuid;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::collections::HashSet;
use std::num::NonZeroUsize;
use lru::LruCache;
use std::collections::HashMap;
#[cfg(feature = "parallel")]
use rayon::prelude::*;
#[derive(Debug, Clone)]
pub struct LayoutConfig {
    pub page_width: f32,
    pub page_height: f32,
    pub margin: f32,
    pub metrics: FontMetrics,
    pub paged: bool,
}

impl Default for LayoutConfig {
    fn default() -> Self {
        Self {
            page_width: 794.0,
            page_height: 1123.0,
            margin: 64.0,
            metrics: FontMetrics::default(),
            paged: true,
        }
    }
}

#[derive(Debug, Clone)]
pub struct LayoutTree {
    pub pages: Vec<Page>,
}

#[derive(Debug, Clone)]
pub struct Page {
    pub number: usize,
    pub blocks: Vec<std::sync::Arc<LayoutBlock>>,
    pub height: f32,
}

#[derive(Debug, Clone)]
pub struct LayoutBlock {
    pub block_id: Uuid,
    pub kind: LayoutKind,
    pub lines: Vec<Line>,
    pub height: f32,
    pub meta: Option<BlockMeta>,
}

#[derive(Debug, Clone)]
pub enum LayoutKind {
    Heading(u8),
    Paragraph,
    List,
    Quote,
    Code,
    Table,
    Figure,
}

#[derive(Debug, Clone)]
pub struct BlockMeta {
    pub width: f32,
    pub height: f32,
}

#[derive(Debug, Clone)]
pub struct Line {
    pub text: String,
    pub width: f32,
}

pub struct LayoutEngine {
    breaker: LineBreaker,
    measurer: SharedMeasurer,
    real: RealMeasurer,
    images: ImageCache,
    break_buf: Vec<usize>,
    scratch: String,
    last_prewarm_version: u64,
    break_cache_long: LruCache<BreakKey, Vec<usize>>,
    break_cache_short: HashMap<BreakKey, Vec<usize>>,
    break_cache_hits: u64,
    break_cache_misses: u64,
}

impl LayoutEngine {
    pub fn new() -> Self {
        let real = RealMeasurer::new();
        let low_spec = std::env::var("WA_LOW_SPEC").ok().as_deref() == Some("1");
        let short_cap = if low_spec { 1024 } else { 4096 };
        let long_cap = if low_spec { 256 } else { 512 };
        Self {
            breaker: LineBreaker,
            measurer: SharedMeasurer(std::sync::Arc::new(real.clone())),
            real,
            images: ImageCache::new(),
            break_buf: Vec::new(),
            scratch: String::new(),
            last_prewarm_version: 0,
            break_cache_long: LruCache::new(NonZeroUsize::new(long_cap).unwrap()),
            break_cache_short: HashMap::with_capacity(short_cap),
            break_cache_hits: 0,
            break_cache_misses: 0,
        }
    }

    pub fn with_font(font: fontdue::Font) -> Self {
        let real = RealMeasurer::Fontdue(FontdueMeasurer::new(font, 8192));
        let low_spec = std::env::var("WA_LOW_SPEC").ok().as_deref() == Some("1");
        let short_cap = if low_spec { 1024 } else { 4096 };
        let long_cap = if low_spec { 256 } else { 512 };
        Self {
            breaker: LineBreaker,
            measurer: SharedMeasurer(std::sync::Arc::new(real.clone())),
            real,
            images: ImageCache::new(),
            break_buf: Vec::new(),
            scratch: String::new(),
            last_prewarm_version: 0,
            break_cache_long: LruCache::new(NonZeroUsize::new(long_cap).unwrap()),
            break_cache_short: HashMap::with_capacity(short_cap),
            break_cache_hits: 0,
            break_cache_misses: 0,
        }
    }

    pub fn layout(&mut self, doc: &Document, config: &LayoutConfig) -> LayoutTree {
        self.prewarm_if_needed(doc, config.metrics);
        #[cfg(feature = "parallel")]
        {
            if std::env::var("WA_LAYOUT_PAR").ok().as_deref() == Some("1") && doc.blocks.len() > 512 {
                return self.layout_parallel(doc, config);
            }
        }
        let mut pages = Vec::new();
        let mut current = Page {
            number: 1,
            blocks: Vec::new(),
            height: 0.0,
        };
        let max_height = config.page_height - config.margin * 2.0;
        for block in &doc.blocks {
            let lb = std::sync::Arc::new(self.layout_block(block, config));
            let needed = lb.height;
            if config.paged && current.height + needed > max_height && !current.blocks.is_empty() {
                pages.push(current);
                current = Page {
                    number: pages.len() + 1,
                    blocks: Vec::new(),
                    height: 0.0,
                };
            }
            current.height += needed;
            current.blocks.push(lb);
        }
        pages.push(current);
        self.maybe_log_stats();
        LayoutTree { pages }
    }

    #[cfg(feature = "parallel")]
    pub fn layout_parallel(&self, doc: &Document, config: &LayoutConfig) -> LayoutTree {
        let blocks: Vec<std::sync::Arc<LayoutBlock>> = doc
            .blocks
            .par_iter()
            .map(|block| {
                let mut worker = LayoutWorker::new(self.measurer.clone(), self.images.clone());
                std::sync::Arc::new(worker.layout_block(block, config))
            })
            .collect();
        paginate_blocks(blocks, config)
    }

    pub fn layout_cached(
        &mut self,
        doc: &Document,
        config: &LayoutConfig,
        cache: &mut LayoutCache,
    ) -> LayoutTree {
        self.prewarm_if_needed(doc, config.metrics);
        #[cfg(feature = "parallel")]
        {
            if std::env::var("WA_LAYOUT_PAR").ok().as_deref() == Some("1") && doc.blocks.len() > 512 {
                return self.layout_cached_parallel(doc, config, cache);
            }
        }
        let mut pages = Vec::new();
        let mut current = Page {
            number: 1,
            blocks: Vec::new(),
            height: 0.0,
        };
        let max_height = config.page_height - config.margin * 2.0;
        for block in &doc.blocks {
            let dirty = is_effectively_dirty(block);
            let sig = hash_block(block);
            let lb = if dirty {
                if let Some(hit) = cache.get(block.id()) {
                    if cache.signature(block.id()) == Some(sig) {
                        hit.clone()
                    } else {
                        let fresh = std::sync::Arc::new(self.layout_block_with_pool(block, config, cache));
                        cache.insert_with_sig(block.id(), fresh.clone(), sig);
                        fresh
                    }
                } else {
                    let fresh = std::sync::Arc::new(self.layout_block_with_pool(block, config, cache));
                    cache.insert_with_sig(block.id(), fresh.clone(), sig);
                    fresh
                }
            } else if let Some(hit) = cache.get(block.id()) {
                hit.clone()
            } else {
                let fresh = std::sync::Arc::new(self.layout_block_with_pool(block, config, cache));
                cache.insert_with_sig(block.id(), fresh.clone(), sig);
                fresh
            };
            let needed = lb.height;
            if config.paged && current.height + needed > max_height && !current.blocks.is_empty() {
                pages.push(current);
                current = Page {
                    number: pages.len() + 1,
                    blocks: Vec::new(),
                    height: 0.0,
                };
            }
            current.height += needed;
            current.blocks.push(lb);
        }
        pages.push(current);
        self.maybe_log_stats();
        LayoutTree { pages }
    }

    #[cfg(feature = "parallel")]
    fn layout_cached_parallel(&mut self, doc: &Document, config: &LayoutConfig, cache: &mut LayoutCache) -> LayoutTree {
        let mut reuse: Vec<Option<std::sync::Arc<LayoutBlock>>> = Vec::with_capacity(doc.blocks.len());
        let mut sigs: Vec<u64> = Vec::with_capacity(doc.blocks.len());
        let mut compute_idx: Vec<usize> = Vec::new();
        for (idx, block) in doc.blocks.iter().enumerate() {
            let dirty = is_effectively_dirty(block);
            let sig = hash_block(block);
            sigs.push(sig);
            let hit = cache.get(block.id()).cloned();
            let reuse_hit = if dirty {
                if let Some(h) = hit {
                    if cache.signature(block.id()) == Some(sig) { Some(h) } else { None }
                } else {
                    None
                }
            } else {
                hit
            };
            if reuse_hit.is_some() {
                reuse.push(reuse_hit);
            } else {
                reuse.push(None);
                compute_idx.push(idx);
            }
        }

        let computed: HashMap<Uuid, std::sync::Arc<LayoutBlock>> = compute_idx
            .par_iter()
            .map(|idx| {
                let block = &doc.blocks[*idx];
                let mut worker = LayoutWorker::new(self.measurer.clone(), self.images.clone());
                let lb = worker.layout_block(block, config);
                (block.id(), std::sync::Arc::new(lb))
            })
            .collect();

        let mut blocks = Vec::with_capacity(doc.blocks.len());
        for (idx, block) in doc.blocks.iter().enumerate() {
            let sig = sigs[idx];
            let lb = if let Some(hit) = reuse[idx].clone() {
                hit
            } else if let Some(comp) = computed.get(&block.id()) {
                cache.insert_with_sig(block.id(), comp.clone(), sig);
                comp.clone()
            } else {
                let fresh = std::sync::Arc::new(self.layout_block_with_pool(block, config, cache));
                cache.insert_with_sig(block.id(), fresh.clone(), sig);
                fresh
            };
            blocks.push(lb);
        }
        paginate_blocks(blocks, config)
    }

    fn layout_block(&mut self, block: &Block, config: &LayoutConfig) -> LayoutBlock {
        self.layout_block_inner(block, config, None)
    }

    fn layout_block_with_pool(&mut self, block: &Block, config: &LayoutConfig, cache: &mut LayoutCache) -> LayoutBlock {
        self.layout_block_inner(block, config, Some(cache))
    }

    fn layout_block_inner(&mut self, block: &Block, config: &LayoutConfig, cache: Option<&mut LayoutCache>) -> LayoutBlock {
        let mut cache = cache;
        let width = config.page_width - config.margin * 2.0;
        match block {
            Block::Heading { level, content, .. } => {
                let text = join_inline(content);
                let lines = self.wrap_text_with_pool(&text, width, config.metrics, cache.as_deref_mut());
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Heading(*level),
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Paragraph { content, .. } => {
                let text = join_inline(content);
                let lines = self.wrap_text_with_pool(&text, width, config.metrics, cache.as_deref_mut());
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Paragraph,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::List { items, .. } => {
                let mut lines = self.alloc_lines(cache.as_deref_mut(), items.len().saturating_mul(2));
                for (idx, item) in items.iter().enumerate() {
                    if let Some(cache) = cache.as_deref_mut() {
                        let sig = hash_inlines_value(&item.content);
                        if let Some(hit) = cache.get_list_item(block.id(), idx, sig) {
                            lines.extend(hit.iter().cloned());
                            continue;
                        }
                    }
                    self.scratch.clear();
                    let item_len = inline_text_len(&item.content);
                    let digits = (idx + 1).to_string().len();
                    self.scratch.reserve(item_len + digits + 1);
                    let _ = std::fmt::Write::write_fmt(&mut self.scratch, format_args!("{} ", idx + 1));
                    join_inline_into(&mut self.scratch, &item.content);
                    let text = std::mem::take(&mut self.scratch);
                    let wrapped = self.wrap_text_with_pool(&text, width, config.metrics, cache.as_deref_mut());
                    if let Some(cache) = cache.as_deref_mut() {
                        let sig = hash_inlines_value(&item.content);
                        cache.put_list_item(block.id(), idx, sig, wrapped.clone());
                    }
                    lines.extend(wrapped);
                    self.scratch = text;
                }
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::List,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Quote { content, .. } => {
                let mut lines = self.alloc_lines(cache.as_deref_mut(), content.len().saturating_mul(2));
                for (idx, b) in content.iter().enumerate() {
                    if let Block::Paragraph { content, .. } = b {
                        if let Some(cache) = cache.as_deref_mut() {
                            let sig = hash_inlines_value(content);
                            if let Some(hit) = cache.get_quote_item(block.id(), idx, sig) {
                                lines.extend(hit.iter().cloned());
                                continue;
                            }
                        }
                        self.scratch.clear();
                        join_inline_into(&mut self.scratch, content);
                        let text = std::mem::take(&mut self.scratch);
                        let wrapped = self.wrap_text_with_pool(&text, width, config.metrics, cache.as_deref_mut());
                        if let Some(cache) = cache.as_deref_mut() {
                            let sig = hash_inlines_value(content);
                            cache.put_quote_item(block.id(), idx, sig, wrapped.clone());
                        }
                        lines.extend(wrapped);
                        self.scratch = text;
                    }
                }
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Quote,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Code { code, .. } => {
                let line_count = code.as_ref().bytes().filter(|b| *b == b'\n').count() + 1;
                let mut lines = self.alloc_lines(cache.as_deref_mut(), line_count);
                for l in code.as_ref().lines() {
                    lines.push(Line {
                        text: l.to_string(),
                        width: self.measurer.0.measure(l, config.metrics),
                    });
                }
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Code,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Table { rows, .. } => {
                let mut lines = self.alloc_lines(cache.as_deref_mut(), rows.len());
                for (ri, row) in rows.iter().enumerate() {
                    if let Some(cache) = cache.as_deref_mut() {
                        let sig = hash_row_value(row);
                        if let Some(hit) = cache.get_table_row(block.id(), ri, sig) {
                            lines.extend(hit.iter().cloned());
                            continue;
                        }
                    }
                    let mut row_len = 0usize;
                    for cell in row.iter() {
                        row_len += inline_text_len(&cell.content);
                    }
                    if row.len() > 1 {
                        row_len += (row.len() - 1) * 3;
                    }
                    let mut row_text = String::with_capacity(row_len);
                    for (idx, cell) in row.iter().enumerate() {
                        if idx > 0 {
                            row_text.push_str(" | ");
                        }
                        join_inline_into(&mut row_text, &cell.content);
                    }
                    let row_line = Line {
                        text: row_text,
                        width: width,
                    };
                    lines.push(row_line.clone());
                    if let Some(cache) = cache.as_deref_mut() {
                        let sig = hash_row_value(row);
                        cache.put_table_row(block.id(), ri, sig, vec![row_line]);
                    }
                }
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Table,
                    lines,
                    height,
                    meta: Some(BlockMeta { width, height }),
                }
            }
            Block::Figure { url, caption, size, .. } => {
                let asset = self.images.load(url);
                let (asset_w, asset_h) = if let Some(sz) = size {
                    (sz.width.max(1.0), sz.height.max(1.0))
                } else {
                    (asset.width, asset.height)
                };
                let fig_height = asset_h;
                let text = caption.as_ref().map(|c| c.as_ref()).unwrap_or("图片");
                let lines = self.wrap_text_with_pool(&text, width, config.metrics, cache.as_deref_mut());
                let height = fig_height + lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Figure,
                    lines,
                    height,
                    meta: Some(BlockMeta { width: asset_w, height: asset_h }),
                }
            }
        }
    }

    fn wrap_text_with_pool(&mut self, text: &str, width: f32, metrics: FontMetrics, cache: Option<&mut LayoutCache>) -> Vec<Line> {
        if text.is_empty() {
            return vec![Line { text: String::new(), width: 0.0 }];
        }
        self.fill_break_buf(text, width, metrics.font_size);
        let mut break_idx = 0usize;
        let cap = self.break_buf.len().saturating_add(1);
        let mut out = self.alloc_lines(cache, cap);
        let break_positions = &self.break_buf;
        let mut start = 0usize;
        let mut last_break: Option<usize> = None;
        let mut last_break_width = 0.0;
        let mut current_width = 0.0;
        let mut iter = text.char_indices().peekable();
        let mut buf = [0u8; 4];
        while let Some((pos, ch)) = iter.next() {
            while break_idx < break_positions.len() && break_positions[break_idx] < pos {
                break_idx += 1;
            }
            if break_idx < break_positions.len() && break_positions[break_idx] == pos {
                last_break = Some(pos);
                last_break_width = current_width;
            }
            let w = self.measurer.0.measure(ch.encode_utf8(&mut buf), metrics);
            current_width += w;
            let total_width = current_width;
            let next_pos = iter.peek().map(|(p, _)| *p).unwrap_or(text.len());
            if current_width > width && pos > start {
                let mut break_pos = last_break.unwrap_or(pos);
                if break_pos <= start {
                    break_pos = pos;
                }
                let mut adjusted = false;
                let adjusted_pos = adjust_break(text, start, break_pos);
                if adjusted_pos != break_pos {
                    adjusted = true;
                    break_pos = adjusted_pos;
                }
                let slice = text[start..break_pos].trim_end();
                if !slice.is_empty() {
                    let slice_width = if !adjusted && Some(break_pos) == last_break {
                        last_break_width
                    } else if !adjusted && break_pos == pos {
                        (current_width - w).max(0.0)
                    } else {
                        self.measurer.0.measure(slice, metrics)
                    };
                    out.push(Line { text: slice.to_string(), width: slice_width });
                }
                let base_width = if !adjusted && Some(break_pos) == last_break {
                    last_break_width
                } else if !adjusted && break_pos == pos {
                    (current_width - w).max(0.0)
                } else {
                    self.measurer.0.measure(&text[start..break_pos], metrics)
                };
                start = break_pos;
                current_width = 0.0;
                if start < next_pos {
                    if !adjusted && Some(break_pos) == last_break {
                        current_width = (total_width - base_width).max(0.0);
                    } else if !adjusted && break_pos == pos {
                        current_width = w;
                    } else {
                        let rem = &text[start..next_pos];
                        current_width = self.measurer.0.measure(rem, metrics);
                    }
                }
                last_break = None;
                last_break_width = 0.0;
            }
        }
        let slice = text[start..text.len()].trim_end();
        if !slice.is_empty() {
            let raw = &text[start..text.len()];
            let slice_width = if slice.len() == raw.len() {
                current_width
            } else {
                self.measurer.0.measure(slice, metrics)
            };
            out.push(Line { text: slice.to_string(), width: slice_width });
        }
        if out.is_empty() {
            out.push(Line { text: String::new(), width: 0.0 });
        }
        out
    }

    fn alloc_lines(&mut self, cache: Option<&mut LayoutCache>, cap: usize) -> Vec<Line> {
        let mut out = if let Some(cache) = cache {
            cache.take_lines()
        } else {
            Vec::new()
        };
        out.clear();
        if cap > 0 {
            out.reserve(cap);
        }
        out
    }

    fn prewarm_if_needed(&mut self, doc: &Document, metrics: FontMetrics) {
        if self.last_prewarm_version == doc.version {
            return;
        }
        let mut chars = Vec::new();
        collect_doc_chars(doc, &mut chars, 512);
        if !chars.is_empty() {
            self.real.prewarm_chars(&chars, metrics);
        }
        self.last_prewarm_version = doc.version;
    }

    fn fill_break_buf(&mut self, text: &str, width: f32, font_size: f32) {
        let mut hasher = DefaultHasher::new();
        text.hash(&mut hasher);
        let key = BreakKey {
            text_hash: hasher.finish(),
            width_q: quantize_width(width),
            size_q: quantize_size(font_size),
        };
        if text.len() <= 128 {
            if let Some(cached) = self.break_cache_short.get(&key) {
                self.break_buf.clear();
                self.break_buf.extend_from_slice(cached);
                self.break_cache_hits += 1;
                return;
            }
        } else if let Some(cached) = self.break_cache_long.get(&key) {
            self.break_buf.clear();
            self.break_buf.extend_from_slice(cached);
            self.break_cache_hits += 1;
            return;
        }
        self.breaker.break_positions_into(text, &mut self.break_buf);
        self.break_cache_misses += 1;
        if text.len() <= 128 {
            if self.break_cache_short.len() > 4096 {
                self.break_cache_short.clear();
            }
            self.break_cache_short.insert(key, self.break_buf.clone());
        } else {
            self.break_cache_long.put(key, self.break_buf.clone());
        }
    }

    fn maybe_log_stats(&self) {
        if std::env::var("WA_DIAG").ok().as_deref() != Some("1") {
            return;
        }
        if self.break_cache_hits + self.break_cache_misses == 0 {
            return;
        }
        let total = self.break_cache_hits + self.break_cache_misses;
        let hit_rate = self.break_cache_hits as f64 / total as f64;
        eprintln!("[layout] break_cache hit_rate={:.2} hits={} misses={}", hit_rate, self.break_cache_hits, self.break_cache_misses);
        if let Some(rate) = self.real.hit_rate() {
            eprintln!("[layout] glyph_cache hit_rate={:.2}", rate);
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct BreakKey {
    text_hash: u64,
    width_q: u32,
    size_q: u16,
}

fn quantize_width(width: f32) -> u32 {
    (width.max(0.0) * 10.0).round() as u32
}

fn quantize_size(size: f32) -> u16 {
    size.round().max(1.0) as u16
}

#[cfg(feature = "parallel")]
fn paginate_blocks(blocks: Vec<std::sync::Arc<LayoutBlock>>, config: &LayoutConfig) -> LayoutTree {
    let mut pages = Vec::new();
    let mut current = Page {
        number: 1,
        blocks: Vec::new(),
        height: 0.0,
    };
    let max_height = config.page_height - config.margin * 2.0;
    for block in blocks {
        let needed = block.height;
        if config.paged && current.height + needed > max_height && !current.blocks.is_empty() {
            pages.push(current);
            current = Page {
                number: pages.len() + 1,
                blocks: Vec::new(),
                height: 0.0,
            };
        }
        current.height += needed;
        current.blocks.push(block);
    }
    pages.push(current);
    LayoutTree { pages }
}

#[cfg(feature = "parallel")]
struct LayoutWorker {
    breaker: LineBreaker,
    measurer: SharedMeasurer,
    images: ImageCache,
    break_buf: Vec<usize>,
    scratch: String,
}

#[cfg(feature = "parallel")]
impl LayoutWorker {
    fn new(measurer: SharedMeasurer, images: ImageCache) -> Self {
        Self {
            breaker: LineBreaker,
            measurer,
            images,
            break_buf: Vec::new(),
            scratch: String::new(),
        }
    }

    fn layout_block(&mut self, block: &Block, config: &LayoutConfig) -> LayoutBlock {
        let width = config.page_width - config.margin * 2.0;
        match block {
            Block::Heading { level, content, .. } => {
                let text = join_inline(content);
                let lines = self.wrap_text(&text, width, config.metrics);
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Heading(*level),
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Paragraph { content, .. } => {
                let text = join_inline(content);
                let lines = self.wrap_text(&text, width, config.metrics);
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Paragraph,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::List { items, .. } => {
                let mut lines = Vec::with_capacity(items.len().saturating_mul(2));
                for (idx, item) in items.iter().enumerate() {
                    self.scratch.clear();
                    let item_len = inline_text_len(&item.content);
                    let digits = (idx + 1).to_string().len();
                    self.scratch.reserve(item_len + digits + 1);
                    let _ = std::fmt::Write::write_fmt(&mut self.scratch, format_args!("{} ", idx + 1));
                    join_inline_into(&mut self.scratch, &item.content);
                    let text = std::mem::take(&mut self.scratch);
                    lines.extend(self.wrap_text(&text, width, config.metrics));
                    self.scratch = text;
                }
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::List,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Quote { content, .. } => {
                self.scratch.clear();
                let mut total_len = 0usize;
                let mut parts = 0usize;
                for b in content {
                    if let Block::Paragraph { content, .. } = b {
                        total_len += inline_text_len(content);
                        parts += 1;
                    }
                }
                if parts > 1 {
                    total_len += parts - 1;
                }
                self.scratch.reserve(total_len);
                let mut first = true;
                for b in content {
                    if let Block::Paragraph { content, .. } = b {
                        if !first {
                            self.scratch.push(' ');
                        }
                        join_inline_into(&mut self.scratch, content);
                        first = false;
                    }
                }
                let text = std::mem::take(&mut self.scratch);
                let lines = self.wrap_text(&text, width, config.metrics);
                self.scratch = text;
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Quote,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Code { code, .. } => {
                let line_count = code.as_ref().bytes().filter(|b| *b == b'\n').count() + 1;
                let mut lines = Vec::with_capacity(line_count);
                for l in code.as_ref().lines() {
                    lines.push(Line {
                        text: l.to_string(),
                        width: self.measurer.0.measure(l, config.metrics),
                    });
                }
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Code,
                    lines,
                    height,
                    meta: None,
                }
            }
            Block::Table { rows, .. } => {
                let mut lines = Vec::with_capacity(rows.len());
                for row in rows {
                    let mut row_len = 0usize;
                    for cell in row.iter() {
                        row_len += inline_text_len(&cell.content);
                    }
                    if row.len() > 1 {
                        row_len += (row.len() - 1) * 3;
                    }
                    let mut row_text = String::with_capacity(row_len);
                    for (idx, cell) in row.iter().enumerate() {
                        if idx > 0 {
                            row_text.push_str(" | ");
                        }
                        join_inline_into(&mut row_text, &cell.content);
                    }
                    lines.push(Line {
                        text: row_text,
                        width: width,
                    });
                }
                let height = lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Table,
                    lines,
                    height,
                    meta: Some(BlockMeta { width, height }),
                }
            }
            Block::Figure { url, caption, size, .. } => {
                let asset = self.images.load(url);
                let (asset_w, asset_h) = if let Some(sz) = size {
                    (sz.width.max(1.0), sz.height.max(1.0))
                } else {
                    (asset.width, asset.height)
                };
                let fig_height = asset_h;
                let text = caption.as_ref().map(|c| c.as_ref()).unwrap_or("图片");
                let lines = self.wrap_text(&text, width, config.metrics);
                let height = fig_height + lines.len() as f32 * config.metrics.font_size * config.metrics.line_height;
                LayoutBlock {
                    block_id: block.id(),
                    kind: LayoutKind::Figure,
                    lines,
                    height,
                    meta: Some(BlockMeta { width: asset_w, height: asset_h }),
                }
            }
        }
    }

    fn wrap_text(&mut self, text: &str, width: f32, metrics: FontMetrics) -> Vec<Line> {
        if text.is_empty() {
            return vec![Line { text: String::new(), width: 0.0 }];
        }
        self.breaker.break_positions_into(text, &mut self.break_buf);
        let break_positions = &self.break_buf;
        let mut break_idx = 0usize;
        let mut out = Vec::with_capacity(break_positions.len().saturating_add(1));
        let mut start = 0usize;
        let mut last_break: Option<usize> = None;
        let mut last_break_width = 0.0;
        let mut current_width = 0.0;
        let mut iter = text.char_indices().peekable();
        let mut buf = [0u8; 4];
        while let Some((pos, ch)) = iter.next() {
            while break_idx < break_positions.len() && break_positions[break_idx] < pos {
                break_idx += 1;
            }
            if break_idx < break_positions.len() && break_positions[break_idx] == pos {
                last_break = Some(pos);
                last_break_width = current_width;
            }
            let w = self.measurer.0.measure(ch.encode_utf8(&mut buf), metrics);
            current_width += w;
            let total_width = current_width;
            let next_pos = iter.peek().map(|(p, _)| *p).unwrap_or(text.len());
            if current_width > width && pos > start {
                let mut break_pos = last_break.unwrap_or(pos);
                if break_pos <= start {
                    break_pos = pos;
                }
                let mut adjusted = false;
                let adjusted_pos = adjust_break(text, start, break_pos);
                if adjusted_pos != break_pos {
                    adjusted = true;
                    break_pos = adjusted_pos;
                }
                let slice = text[start..break_pos].trim_end();
                if !slice.is_empty() {
                    let slice_width = if !adjusted && Some(break_pos) == last_break {
                        last_break_width
                    } else if !adjusted && break_pos == pos {
                        (current_width - w).max(0.0)
                    } else {
                        self.measurer.0.measure(slice, metrics)
                    };
                    out.push(Line { text: slice.to_string(), width: slice_width });
                }
                let base_width = if !adjusted && Some(break_pos) == last_break {
                    last_break_width
                } else if !adjusted && break_pos == pos {
                    (current_width - w).max(0.0)
                } else {
                    self.measurer.0.measure(&text[start..break_pos], metrics)
                };
                start = break_pos;
                current_width = 0.0;
                if start < next_pos {
                    if !adjusted && Some(break_pos) == last_break {
                        current_width = (total_width - base_width).max(0.0);
                    } else if !adjusted && break_pos == pos {
                        current_width = w;
                    } else {
                        let rem = &text[start..next_pos];
                        current_width = self.measurer.0.measure(rem, metrics);
                    }
                }
                last_break = None;
                last_break_width = 0.0;
            }
        }
        let slice = text[start..text.len()].trim_end();
        if !slice.is_empty() {
            let raw = &text[start..text.len()];
            let slice_width = if slice.len() == raw.len() {
                current_width
            } else {
                self.measurer.0.measure(slice, metrics)
            };
            out.push(Line { text: slice.to_string(), width: slice_width });
        }
        if out.is_empty() {
            out.push(Line { text: String::new(), width: 0.0 });
        }
        out
    }
}

fn hash_block(block: &Block) -> u64 {
    let mut hasher = DefaultHasher::new();
    hash_block_into(block, &mut hasher);
    hasher.finish()
}

fn hash_block_into(block: &Block, hasher: &mut impl Hasher) {
    std::mem::discriminant(block).hash(hasher);
    match block {
        Block::Heading { level, content, .. } => {
            level.hash(hasher);
            hash_inlines(content, hasher);
        }
        Block::Paragraph { content, .. } => {
            hash_inlines(content, hasher);
        }
        Block::List { ordered, items, .. } => {
            ordered.hash(hasher);
            items.len().hash(hasher);
            for item in items {
                hash_inlines(&item.content, hasher);
            }
        }
        Block::Quote { content, .. } => {
            content.len().hash(hasher);
            for inner in content {
                hash_block_into(inner, hasher);
            }
        }
        Block::Code { lang, code, .. } => {
            lang.as_ref().hash(hasher);
            code.as_ref().hash(hasher);
        }
        Block::Table { rows, .. } => {
            rows.len().hash(hasher);
            for row in rows {
                row.len().hash(hasher);
                for cell in row {
                    hash_inlines(&cell.content, hasher);
                }
            }
        }
        Block::Figure { url, caption, size, .. } => {
            url.as_ref().hash(hasher);
            caption.as_ref().map(|c| c.as_ref()).hash(hasher);
            if let Some(sz) = size {
                sz.width.to_bits().hash(hasher);
                sz.height.to_bits().hash(hasher);
            }
        }
    }
}

fn hash_inlines(inlines: &[Inline], hasher: &mut impl Hasher) {
    inlines.len().hash(hasher);
    for inline in inlines {
        std::mem::discriminant(inline).hash(hasher);
        match inline {
            Inline::Text { value } | Inline::CodeSpan { value } => {
                value.as_ref().hash(hasher);
            }
            Inline::Styled { style, content } => {
                style.bold.hash(hasher);
                style.italic.hash(hasher);
                style.underline.hash(hasher);
                hash_inlines(content, hasher);
            }
            Inline::Link { url, text } => {
                url.as_ref().hash(hasher);
                hash_inlines(text, hasher);
            }
        }
    }
}

fn hash_inlines_value(inlines: &[Inline]) -> u64 {
    let mut hasher = DefaultHasher::new();
    hash_inlines(inlines, &mut hasher);
    hasher.finish()
}

fn hash_row_value(row: &[wa_core::Cell]) -> u64 {
    let mut hasher = DefaultHasher::new();
    row.len().hash(&mut hasher);
    for cell in row {
        hash_inlines(&cell.content, &mut hasher);
    }
    hasher.finish()
}

fn is_effectively_dirty(block: &Block) -> bool {
    if block.is_dirty() {
        return true;
    }
    if let Block::Quote { content, .. } = block {
        return content.iter().any(is_effectively_dirty);
    }
    false
}

fn collect_doc_chars(doc: &Document, out: &mut Vec<char>, limit: usize) {
    let mut seen = HashSet::new();
    for block in &doc.blocks {
        collect_block_chars(block, out, &mut seen, limit);
        if out.len() >= limit {
            break;
        }
    }
}

fn collect_block_chars(block: &Block, out: &mut Vec<char>, seen: &mut HashSet<char>, limit: usize) {
    if out.len() >= limit {
        return;
    }
    match block {
        Block::Heading { content, .. }
        | Block::Paragraph { content, .. } => {
            collect_inline_chars(content, out, seen, limit);
        }
        Block::List { items, .. } => {
            for item in items {
                collect_inline_chars(&item.content, out, seen, limit);
                if out.len() >= limit {
                    break;
                }
            }
        }
        Block::Quote { content, .. } => {
            for inner in content {
                collect_block_chars(inner, out, seen, limit);
                if out.len() >= limit {
                    break;
                }
            }
        }
        Block::Code { code, .. } => {
            for ch in code.as_ref().chars() {
                if out.len() >= limit {
                    break;
                }
                if seen.insert(ch) {
                    out.push(ch);
                }
            }
        }
        Block::Table { rows, .. } => {
            for row in rows {
                for cell in row {
                    collect_inline_chars(&cell.content, out, seen, limit);
                    if out.len() >= limit {
                        return;
                    }
                }
            }
        }
        Block::Figure { caption, .. } => {
            if let Some(cap) = caption.as_ref() {
                for ch in cap.as_ref().chars() {
                    if out.len() >= limit {
                        break;
                    }
                    if seen.insert(ch) {
                        out.push(ch);
                    }
                }
            }
        }
    }
}

fn collect_inline_chars(inlines: &[Inline], out: &mut Vec<char>, seen: &mut HashSet<char>, limit: usize) {
    for inline in inlines {
        if out.len() >= limit {
            break;
        }
        match inline {
            Inline::Text { value } | Inline::CodeSpan { value } => {
                for ch in value.as_ref().chars() {
                    if out.len() >= limit {
                        break;
                    }
                    if seen.insert(ch) {
                        out.push(ch);
                    }
                }
            }
            Inline::Styled { content, .. } => collect_inline_chars(content, out, seen, limit),
            Inline::Link { text, .. } => collect_inline_chars(text, out, seen, limit),
        }
    }
}

fn adjust_break(text: &str, start: usize, mut break_pos: usize) -> usize {
    if break_pos <= start {
        return break_pos;
    }
    if let Some((prev_idx, prev_ch)) = prev_char(text, break_pos) {
        if is_forbidden_line_end(prev_ch) && prev_idx > start {
            break_pos = prev_idx;
        }
    }
    if let Some(next_ch) = next_char(text, break_pos) {
        if is_forbidden_line_start(next_ch) {
            if let Some(next_idx) = next_char_index(text, break_pos) {
                break_pos = next_idx;
            }
        }
    }
    break_pos
}

fn prev_char(text: &str, idx: usize) -> Option<(usize, char)> {
    if idx == 0 || idx > text.len() {
        return None;
    }
    let mut it = text[..idx].char_indices();
    it.next_back()
}

fn next_char(text: &str, idx: usize) -> Option<char> {
    if idx >= text.len() {
        return None;
    }
    text[idx..].chars().next()
}

fn next_char_index(text: &str, idx: usize) -> Option<usize> {
    if idx >= text.len() {
        return None;
    }
    let mut it = text[idx..].char_indices();
    let (_, ch) = it.next()?;
    Some(idx + ch.len_utf8())
}

fn is_forbidden_line_start(ch: char) -> bool {
    matches!(
        ch,
        '，' | '。' | '！' | '？' | '；' | '：' | '、' | '）' | '】' | '》' | '〉' | '」' | '』' | '”' | '’'
            | ',' | '.' | '!' | '?' | ';' | ':' | ')' | ']' | '}'
    )
}

fn is_forbidden_line_end(ch: char) -> bool {
    matches!(
        ch,
        '（' | '【' | '《' | '〈' | '「' | '『' | '“' | '‘' | '〔' | '［' | '｛'
            | '(' | '[' | '{'
    )
}

fn join_inline(inlines: &[Inline]) -> String {
    let mut out = String::with_capacity(inline_text_len(inlines));
    join_inline_into(&mut out, inlines);
    out
}

fn inline_text_len(inlines: &[Inline]) -> usize {
    let mut len = 0usize;
    for inline in inlines {
        match inline {
            Inline::Text { value } => len += value.len(),
            Inline::CodeSpan { value } => len += value.len(),
            Inline::Link { text, .. } => len += inline_text_len(text),
            Inline::Styled { content, .. } => len += inline_text_len(content),
        }
    }
    len
}

fn join_inline_into(out: &mut String, inlines: &[Inline]) {
    for inline in inlines {
        match inline {
            Inline::Text { value } => out.push_str(value.as_ref()),
            Inline::CodeSpan { value } => out.push_str(value.as_ref()),
            Inline::Link { text, .. } => join_inline_into(out, text),
            Inline::Styled { content, .. } => join_inline_into(out, content),
        }
    }
}









