use crate::{
    Block, CommandHistory, Document, EditorCommand, Inline, ListItem, Position, Selection, Style, TableEditor, Snapshot, HistoryEntry,
};
use std::sync::Arc;
use uuid::Uuid;

pub struct Editor {
    pub doc: Document,
    pub selection: Selection,
    history: CommandHistory,
}

impl Editor {
    pub fn new(doc: Document) -> Self {
        let first_id = doc
            .blocks
            .get(0)
            .map(|b| b.id())
            .unwrap_or_else(Uuid::new_v4);
        let selection = Selection::collapsed(Position { block_id: first_id, offset: 0 });
        Self {
            doc,
            selection,
            history: CommandHistory::new(100),
        }
    }

    pub fn execute(&mut self, cmd: EditorCommand) {
        match cmd.clone() {
            EditorCommand::InsertText(text) => {
                if text.is_empty() {
                    return;
                }
                let block_id = self.selection.focus.block_id;
                self.with_block_change_merge(block_id, |b| {
                    Self::insert_text_into_block(b, text.clone());
                });
            }
            EditorCommand::DeleteSelection => {
                let block_id = self.selection.focus.block_id;
                let should_delete = self
                    .doc
                    .blocks
                    .iter()
                    .find(|b| b.id() == block_id)
                    .and_then(|b| match b {
                        Block::Paragraph { content, .. } | Block::Heading { content, .. } => Some(!content.is_empty()),
                        _ => None,
                    })
                    .unwrap_or(false);
                if !should_delete {
                    return;
                }
                self.with_block_change_merge(block_id, |b| {
                    Self::delete_selection_in_block(b);
                });
            }
            EditorCommand::ApplyStyle(style) => {
                let block_id = self.selection.focus.block_id;
                self.with_block_change(block_id, |b| {
                    Self::apply_style_in_block(b, style);
                });
            }
            EditorCommand::SetHeading(level) => {
                let block_id = self.selection.focus.block_id;
                self.with_block_change(block_id, |b| {
                    Self::set_heading_in_block(b, level);
                });
            }
            EditorCommand::InsertList(ordered) => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.insert_list(ordered);

            }
            EditorCommand::InsertQuote(text) => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.insert_quote(text);

            }
            EditorCommand::InsertCode { lang, code } => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.insert_code(lang, code);

            }
            EditorCommand::InsertTable(r, c) => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.insert_table(r, c);

            }
            EditorCommand::InsertImage(url) => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.insert_image(url);

            }
            EditorCommand::InsertFigure { url, caption } => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.insert_figure(url, caption);

            }
            EditorCommand::InsertLink { url, text } => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.insert_link(url, text);

            }
            EditorCommand::TableEditCell { block_id, row, col, text } => {
                self.with_block_change(block_id, |b| {
                    TableEditor::set_cell_text(b, row, col, text.clone());
                });
            }
            EditorCommand::TableInsertRow => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.table_insert_row();

            }
            EditorCommand::TableInsertColumn => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.table_insert_column();

            }
            EditorCommand::TableDeleteRow => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.table_delete_row();

            }
            EditorCommand::TableDeleteColumn => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.table_delete_column();

            }
            EditorCommand::ListIndent => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.list_indent(true);

            }
            EditorCommand::ListOutdent => {
                self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
                self.list_indent(false);

            }
            EditorCommand::Undo => {
                self.undo();
                return;
            }
            EditorCommand::Redo => {
                self.redo();
                return;
            }
        }
        self.doc.touch();
    }

    pub fn checkpoint(&mut self) {
        self.history.push_entry(HistoryEntry::Snapshot(self.snapshot()));
    }

    fn snapshot(&self) -> Snapshot {
        Snapshot { doc: self.doc.clone(), selection: self.selection }
    }

    fn with_block_change<F>(&mut self, block_id: uuid::Uuid, mut f: F)
    where
        F: FnMut(&mut Block),
    {
        let selection_before = self.selection;
        if let Some(pos) = self.doc.blocks.iter().position(|b| b.id() == block_id) {
            let before = self.doc.blocks[pos].clone();
            f(&mut self.doc.blocks[pos]);
            let after = self.doc.blocks[pos].clone();
            let selection_after = self.selection;
            self.history.push_entry(HistoryEntry::BlockChange {
                block_id,
                before,
                after,
                selection_before,
                selection_after,
            });
        }
    }

    fn with_block_change_merge<F>(&mut self, block_id: uuid::Uuid, mut f: F)
    where
        F: FnMut(&mut Block),
    {
        let selection_before = self.selection;
        if let Some(pos) = self.doc.blocks.iter().position(|b| b.id() == block_id) {
            let before = self.doc.blocks[pos].clone();
            f(&mut self.doc.blocks[pos]);
            let after = self.doc.blocks[pos].clone();
            let selection_after = self.selection;
            self.history.push_or_merge_block_change(HistoryEntry::BlockChange {
                block_id,
                before,
                after,
                selection_before,
                selection_after,
            });
        }
    }

    fn insert_text_into_block(block: &mut Block, text: String) {
        if let Block::Paragraph { content, dirty, .. } | Block::Heading { content, dirty, .. } = block {
            if let Some(Inline::Text { value }) = content.last_mut() {
                let mut merged = String::with_capacity(value.len() + text.len());
                merged.push_str(value.as_ref());
                merged.push_str(&text);
                *value = Arc::from(merged);
            } else {
                content.push(Inline::Text { value: Arc::from(text) });
            }
            *dirty = true;
        }
    }

    fn delete_selection_in_block(block: &mut Block) {
        if let Block::Paragraph { content, dirty, .. } | Block::Heading { content, dirty, .. } = block {
            content.pop();
            *dirty = true;
        }
    }

    fn apply_style_in_block(block: &mut Block, style: Style) {
        if let Block::Paragraph { content, dirty, .. } | Block::Heading { content, dirty, .. } = block {
            let inner = std::mem::take(content);
            *content = vec![Inline::Styled { style, content: inner }];
            *dirty = true;
        }
    }

    fn set_heading_in_block(block: &mut Block, level: u8) {
        let content = match block {
            Block::Paragraph { content, .. } | Block::Heading { content, .. } => content.clone(),
            _ => vec![Inline::Text { value: Arc::from("") }],
        };
        *block = Block::Heading {
            id: block.id(),
            level,
            content,
            dirty: true,
        };
    }

    fn insert_list(&mut self, ordered: bool) {
        let item = ListItem {
            id: Uuid::new_v4(),
            content: vec![Inline::Text { value: Arc::from("列表项") }],
        };
        self.doc.blocks.push(Block::List {
            id: Uuid::new_v4(),
            ordered,
            items: vec![item],
            dirty: true,
        });
    }

    fn insert_quote(&mut self, text: String) {
        self.doc.blocks.push(Block::Quote {
            id: Uuid::new_v4(),
            content: vec![Block::Paragraph {
                id: Uuid::new_v4(),
                content: vec![Inline::Text { value: Arc::from(text) }],
                dirty: false,
            }],
            dirty: true,
        });
    }

    fn insert_code(&mut self, lang: String, code: String) {
        self.doc.blocks.push(Block::Code {
            id: Uuid::new_v4(),
            lang: Arc::from(lang),
            code: Arc::from(code),
            dirty: true,
        });
    }

    fn insert_table(&mut self, rows: usize, cols: usize) {
        let mut table = Vec::new();
        for _ in 0..rows {
            let mut row = Vec::new();
            for _ in 0..cols {
                row.push(crate::Cell {
                    content: vec![Inline::Text { value: Arc::from("") }],
                });
            }
            table.push(row);
        }
        self.doc.blocks.push(Block::Table {
            id: Uuid::new_v4(),
            rows: table,
            dirty: true,
        });
    }

    fn insert_image(&mut self, url: String) {
        self.doc.blocks.push(Block::Figure {
            id: Uuid::new_v4(),
            url: Arc::from(url),
            caption: Some(Arc::from("图片")),
            size: None,
            dirty: true,
        });
    }

    fn insert_figure(&mut self, url: String, caption: Option<String>) {
        self.doc.blocks.push(Block::Figure {
            id: Uuid::new_v4(),
            url: Arc::from(url),
            caption: caption.map(Arc::from),
            size: None,
            dirty: true,
        });
    }

    fn insert_link(&mut self, url: String, text: String) {
        let link = Inline::Link {
            url: Arc::from(url),
            text: vec![Inline::Text { value: Arc::from(text) }],
        };
        let block_id = self.selection.focus.block_id;
        let mut inserted = false;
        if let Some(block) = self.doc.blocks.iter_mut().find(|b| b.id() == block_id) {
            match block {
                Block::Paragraph { content, dirty, .. } | Block::Heading { content, dirty, .. } => {
                    content.push(link.clone());
                    *dirty = true;
                    inserted = true;
                }
                Block::List { items, dirty, .. } => {
                    if let Some(item) = items.last_mut() {
                        item.content.push(link.clone());
                        *dirty = true;
                        inserted = true;
                    }
                }
                Block::Quote { content, dirty, .. } => {
                    if let Some(last) = content.last_mut() {
                        if let Block::Paragraph { content: para, dirty: p_dirty, .. } = last {
                            para.push(link.clone());
                            *p_dirty = true;
                            *dirty = true;
                            inserted = true;
                        }
                    }
                }
                Block::Table { rows, dirty, .. } => {
                    if let Some(row) = rows.last_mut() {
                        if let Some(cell) = row.last_mut() {
                            cell.content.push(link.clone());
                            *dirty = true;
                            inserted = true;
                        }
                    }
                }
                Block::Code { .. } | Block::Figure { .. } => {}
            }
        }
        if !inserted {
            self.doc.blocks.push(Block::Paragraph {
                id: Uuid::new_v4(),
                content: vec![link],
                dirty: true,
            });
        }
    }

    fn table_insert_row(&mut self) {
        if let Some(block) = self.last_table_mut() {
            TableEditor::insert_row(block, 1);
        }
    }

    fn table_insert_column(&mut self) {
        if let Some(block) = self.last_table_mut() {
            TableEditor::insert_column(block, 1);
        }
    }

    fn table_delete_row(&mut self) {
        if let Some(block) = self.last_table_mut() {
            TableEditor::delete_row(block, 0);
        }
    }

    fn table_delete_column(&mut self) {
        if let Some(block) = self.last_table_mut() {
            TableEditor::delete_column(block, 0);
        }
    }

    fn list_indent(&mut self, indent: bool) {
        let block_id = self.selection.focus.block_id;
        if let Some(block) = self.doc.blocks.iter_mut().find(|b| b.id() == block_id) {
            if let Block::List { items, dirty, .. } = block {
                for item in items.iter_mut() {
                    if let Some(first) = item.content.get_mut(0) {
                        match first {
                            Inline::Text { value } => {
                                let mut s = value.as_ref().to_string();
                                if indent {
                                    s = format!("  {}", s);
                                } else if s.starts_with("  ") {
                                    s = s.trim_start_matches("  ").to_string();
                                }
                                *value = Arc::from(s);
                            }
                            _ => {
                                if indent {
                                    item.content.insert(0, Inline::Text { value: Arc::from("  ") });
                                }
                            }
                        }
                    } else if indent {
                        item.content.push(Inline::Text { value: Arc::from("  ") });
                    }
                }
                *dirty = true;
            }
        }
    }

    fn last_table_mut(&mut self) -> Option<&mut Block> {
        self.doc.blocks.iter_mut().rev().find(|b| matches!(b, Block::Table { .. }))
    }

    fn undo(&mut self) {
        if let Some(entry) = self.history.pop_undo() {
            match entry {
                HistoryEntry::Snapshot(snapshot) => {
                    let current = HistoryEntry::Snapshot(self.snapshot());
                    self.history.push_redo(current);
                    self.doc = snapshot.doc;
                    self.selection = snapshot.selection;
                }
                HistoryEntry::BlockChange { block_id, before, after, selection_before, selection_after } => {
                    let current = HistoryEntry::BlockChange {
                        block_id,
                        before: after.clone(),
                        after: before.clone(),
                        selection_before: selection_after,
                        selection_after: selection_before,
                    };
                    self.history.push_redo(current);
                    if let Some(pos) = self.doc.blocks.iter().position(|b| b.id() == block_id) {
                        self.doc.blocks[pos] = before;
                    }
                    self.selection = selection_before;
                }
            }
        }
    }

    fn redo(&mut self) {
        if let Some(entry) = self.history.pop_redo() {
            match entry {
                HistoryEntry::Snapshot(snapshot) => {
                    let current = HistoryEntry::Snapshot(self.snapshot());
                    self.history.push_undo(current);
                    self.doc = snapshot.doc;
                    self.selection = snapshot.selection;
                }
                HistoryEntry::BlockChange { block_id, before, after, selection_before, selection_after } => {
                    let current = HistoryEntry::BlockChange {
                        block_id,
                        before: after.clone(),
                        after: before.clone(),
                        selection_before: selection_after,
                        selection_after: selection_before,
                    };
                    self.history.push_undo(current);
                    if let Some(pos) = self.doc.blocks.iter().position(|b| b.id() == block_id) {
                        self.doc.blocks[pos] = after;
                    }
                    self.selection = selection_after;
                }
            }
        }
    }
}

