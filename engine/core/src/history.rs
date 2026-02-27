use crate::{Block, Document, Selection};
use std::collections::VecDeque;
use std::time::{Duration, Instant};
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct Snapshot {
    pub doc: Document,
    pub selection: Selection,
}

#[derive(Debug, Clone)]
pub enum HistoryEntry {
    Snapshot(Snapshot),
    BlockChange {
        block_id: Uuid,
        before: Block,
        after: Block,
        selection_before: Selection,
        selection_after: Selection,
    },
}

#[derive(Debug, Clone)]
pub struct CommandHistory {
    undo_stack: VecDeque<HistoryEntry>,
    redo_stack: VecDeque<HistoryEntry>,
    max_depth: usize,
    last_merge_at: Option<Instant>,
}

impl CommandHistory {
    pub fn new(max_depth: usize) -> Self {
        Self {
            undo_stack: VecDeque::new(),
            redo_stack: VecDeque::new(),
            max_depth,
            last_merge_at: None,
        }
    }

    pub fn push_entry(&mut self, entry: HistoryEntry) {
        self.undo_stack.push_back(entry);
        if self.undo_stack.len() > self.max_depth {
            self.undo_stack.pop_front();
        }
        self.redo_stack.clear();
        self.last_merge_at = None;
    }

    pub fn push_or_merge_block_change(&mut self, entry: HistoryEntry) {
        match entry {
            HistoryEntry::BlockChange { block_id, before, after, selection_before, selection_after } => {
                const MERGE_WINDOW: Duration = Duration::from_millis(400);
                let now = Instant::now();
                if let Some(HistoryEntry::BlockChange {
                    block_id: last_id,
                    before: _,
                    after: last_after,
                    selection_before: _,
                    selection_after: last_sel_after,
                }) = self.undo_stack.back_mut()
                {
                    if *last_id == block_id
                        && *last_sel_after == selection_before
                        && self.last_merge_at.map_or(false, |t| now.duration_since(t) <= MERGE_WINDOW)
                    {
                        *last_after = after;
                        *last_sel_after = selection_after;
                        self.redo_stack.clear();
                        self.last_merge_at = Some(now);
                        return;
                    }
                }
                self.push_entry(HistoryEntry::BlockChange {
                    block_id,
                    before,
                    after,
                    selection_before,
                    selection_after,
                });
                self.last_merge_at = Some(now);
            }
            other => self.push_entry(other),
        }
    }

    pub fn pop_undo(&mut self) -> Option<HistoryEntry> {
        self.undo_stack.pop_back()
    }

    pub fn push_undo(&mut self, entry: HistoryEntry) {
        self.undo_stack.push_back(entry);
        if self.undo_stack.len() > self.max_depth {
            self.undo_stack.pop_front();
        }
    }

    pub fn push_redo(&mut self, entry: HistoryEntry) {
        self.redo_stack.push_back(entry);
    }

    pub fn pop_redo(&mut self) -> Option<HistoryEntry> {
        self.redo_stack.pop_back()
    }

    pub fn clear(&mut self) {
        self.undo_stack.clear();
        self.redo_stack.clear();
    }
}
