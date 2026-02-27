use std::collections::HashMap;
use uuid::Uuid;

use crate::{LayoutBlock, LayoutKind, Line};
use std::sync::Arc;

#[derive(Debug, Default)]
pub struct LayoutCache {
    blocks: HashMap<Uuid, Arc<LayoutBlock>>,
    line_pool: Vec<Vec<Line>>,
    sigs: HashMap<Uuid, u64>,
    list_item_cache: HashMap<(Uuid, usize), (u64, Vec<Line>)>,
    quote_item_cache: HashMap<(Uuid, usize), (u64, Vec<Line>)>,
    table_row_cache: HashMap<(Uuid, usize), (u64, Vec<Line>)>,
}

impl LayoutCache {
    pub fn new() -> Self {
        Self {
            blocks: HashMap::new(),
            line_pool: Vec::new(),
            sigs: HashMap::new(),
            list_item_cache: HashMap::new(),
            quote_item_cache: HashMap::new(),
            table_row_cache: HashMap::new(),
        }
    }

    pub fn get(&self, id: Uuid) -> Option<&Arc<LayoutBlock>> {
        self.blocks.get(&id)
    }

    pub fn insert(&mut self, id: Uuid, block: Arc<LayoutBlock>) {
        if let Some(old) = self.blocks.insert(id, block) {
            self.recycle_block(old);
        }
    }

    pub fn insert_with_sig(&mut self, id: Uuid, block: Arc<LayoutBlock>, sig: u64) {
        self.insert(id, block);
        self.sigs.insert(id, sig);
    }

    pub fn signature(&self, id: Uuid) -> Option<u64> {
        self.sigs.get(&id).copied()
    }

    pub fn clear(&mut self) {
        let blocks: Vec<_> = self.blocks.drain().map(|(_, block)| block).collect();
        for block in blocks {
            self.recycle_block(block);
        }
        self.sigs.clear();
        self.list_item_cache.clear();
        self.quote_item_cache.clear();
        self.table_row_cache.clear();
    }

    pub fn take_lines(&mut self) -> Vec<Line> {
        self.line_pool.pop().unwrap_or_default()
    }

    fn recycle_block(&mut self, block: Arc<LayoutBlock>) {
        if let Ok(block) = Arc::try_unwrap(block) {
            self.line_pool.push(block.lines);
        }
    }

    pub fn get_list_item(&self, block_id: Uuid, idx: usize, sig: u64) -> Option<&Vec<Line>> {
        self.list_item_cache.get(&(block_id, idx)).and_then(|(s, lines)| {
            if *s == sig { Some(lines) } else { None }
        })
    }

    pub fn put_list_item(&mut self, block_id: Uuid, idx: usize, sig: u64, lines: Vec<Line>) {
        self.list_item_cache.insert((block_id, idx), (sig, lines));
    }

    pub fn get_quote_item(&self, block_id: Uuid, idx: usize, sig: u64) -> Option<&Vec<Line>> {
        self.quote_item_cache.get(&(block_id, idx)).and_then(|(s, lines)| {
            if *s == sig { Some(lines) } else { None }
        })
    }

    pub fn put_quote_item(&mut self, block_id: Uuid, idx: usize, sig: u64, lines: Vec<Line>) {
        self.quote_item_cache.insert((block_id, idx), (sig, lines));
    }

    pub fn get_table_row(&self, block_id: Uuid, idx: usize, sig: u64) -> Option<&Vec<Line>> {
        self.table_row_cache.get(&(block_id, idx)).and_then(|(s, lines)| {
            if *s == sig { Some(lines) } else { None }
        })
    }

    pub fn put_table_row(&mut self, block_id: Uuid, idx: usize, sig: u64, lines: Vec<Line>) {
        self.table_row_cache.insert((block_id, idx), (sig, lines));
    }
}

pub fn placeholder_block(kind: LayoutKind) -> Arc<LayoutBlock> {
    Arc::new(LayoutBlock {
        block_id: Uuid::nil(),
        kind,
        lines: vec![Line { text: String::new(), width: 0.0 }],
        height: 0.0,
        meta: None,
    })
}
