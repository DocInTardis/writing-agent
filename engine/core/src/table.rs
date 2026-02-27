use crate::{Block, Cell, Inline};
use std::sync::Arc;
use uuid::Uuid;

#[derive(Debug, Default)]
pub struct TableEditor;

impl TableEditor {
    pub fn insert_row(block: &mut Block, index: usize) -> bool {
        if let Block::Table { rows, .. } = block {
            let cols = rows.first().map(|r| r.len()).unwrap_or(1);
            let mut row = Vec::with_capacity(cols);
            for _ in 0..cols {
                row.push(Cell { content: vec![Inline::Text { value: Arc::from("") }] });
            }
            let idx = index.min(rows.len());
            rows.insert(idx, row);
            return true;
        }
        false
    }

    pub fn delete_row(block: &mut Block, index: usize) -> bool {
        if let Block::Table { rows, .. } = block {
            if index < rows.len() {
                rows.remove(index);
                return true;
            }
        }
        false
    }

    pub fn insert_column(block: &mut Block, index: usize) -> bool {
        if let Block::Table { rows, .. } = block {
            for row in rows.iter_mut() {
                let idx = index.min(row.len());
                row.insert(idx, Cell { content: vec![Inline::Text { value: Arc::from("") }] });
            }
            return true;
        }
        false
    }

    pub fn delete_column(block: &mut Block, index: usize) -> bool {
        if let Block::Table { rows, .. } = block {
            for row in rows.iter_mut() {
                if index < row.len() {
                    row.remove(index);
                }
            }
            return true;
        }
        false
    }

    pub fn set_cell_text(block: &mut Block, row: usize, col: usize, text: String) -> bool {
        if let Block::Table { rows, .. } = block {
            if let Some(r) = rows.get_mut(row) {
                if let Some(c) = r.get_mut(col) {
                    c.content = vec![Inline::Text { value: Arc::from(text) }];
                    return true;
                }
            }
        }
        false
    }
}

#[derive(Debug, Clone)]
pub struct TableDescriptor {
    pub id: Uuid,
    pub rows: usize,
    pub cols: usize,
}
