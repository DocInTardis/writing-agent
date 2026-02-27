use crate::{Block, Document, Inline, ListItem};
use std::collections::HashMap;
use std::hash::{Hash, Hasher};
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct Patch {
    pub block_id: Uuid,
    pub kind: PatchKind,
}

#[derive(Debug, Clone)]
pub enum PatchKind {
    InsertBlock,
    ReplaceBlock,
    RemoveBlock,
}

#[derive(Debug, Default)]
pub struct DiffEngine {
    cache: HashMap<Uuid, CacheEntry>,
    generation: u64,
    removed_scratch: Vec<Uuid>,
}

#[derive(Debug, Clone, Copy)]
struct CacheEntry {
    hash: u64,
    generation: u64,
}

impl DiffEngine {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn incremental_diff(&mut self, doc: &Document) -> Vec<Patch> {
        self.generation = self.generation.wrapping_add(1);
        let generation = self.generation;
        let mut out = Vec::new();
        for block in &doc.blocks {
            let id = block.id();
            let prev = self.cache.get(&id).map(|entry| entry.hash);
            let hash = if !block.is_dirty() {
                match prev {
                    Some(value) => value,
                    None => hash_block(block),
                }
            } else {
                hash_block(block)
            };
            match prev {
                None => out.push(Patch { block_id: id, kind: PatchKind::InsertBlock }),
                Some(prev) if prev != hash => out.push(Patch { block_id: id, kind: PatchKind::ReplaceBlock }),
                _ => {}
            }
            self.cache.insert(
                id,
                CacheEntry {
                    hash,
                    generation,
                },
            );
        }
        self.removed_scratch.clear();
        for (id, entry) in &self.cache {
            if entry.generation != generation {
                self.removed_scratch.push(*id);
            }
        }
        for id in self.removed_scratch.drain(..) {
            self.cache.remove(&id);
            out.push(Patch {
                block_id: id,
                kind: PatchKind::RemoveBlock,
            });
        }
        out
    }

    pub fn incremental_diff_and_clear(&mut self, doc: &mut Document) -> Vec<Patch> {
        let patches = self.incremental_diff(doc);
        doc.clear_dirty();
        patches
    }
}

fn hash_block(block: &Block) -> u64 {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    hash_block_inner(block, &mut hasher);
    hasher.finish()
}

fn hash_block_inner(block: &Block, hasher: &mut impl Hasher) {
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
            for item in items {
                hash_list_item(item, hasher);
            }
        }
        Block::Quote { content, .. } => {
            for inner in content {
                hash_block_inner(inner, hasher);
            }
        }
        Block::Code { lang, code, .. } => {
            lang.as_ref().hash(hasher);
            code.as_ref().hash(hasher);
        }
        Block::Table { rows, .. } => {
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

fn hash_list_item(item: &ListItem, hasher: &mut impl Hasher) {
    hash_inlines(&item.content, hasher);
}

fn hash_inlines(inlines: &[Inline], hasher: &mut impl Hasher) {
    for inline in inlines {
        std::mem::discriminant(inline).hash(hasher);
        match inline {
            Inline::Text { value } => value.as_ref().hash(hasher),
            Inline::Styled { style, content } => {
                style.bold.hash(hasher);
                style.italic.hash(hasher);
                style.underline.hash(hasher);
                style.strikethrough.hash(hasher);
                hash_inlines(content, hasher);
            }
            Inline::Link { url, text } => {
                url.as_ref().hash(hasher);
                hash_inlines(text, hasher);
            }
            Inline::CodeSpan { value } => value.as_ref().hash(hasher),
        }
    }
}
