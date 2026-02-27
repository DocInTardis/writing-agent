use crate::Style;

#[derive(Debug, Clone)]
pub enum EditorCommand {
    InsertText(String),
    DeleteSelection,
    ApplyStyle(Style),
    SetHeading(u8),
    InsertList(bool),
    InsertQuote(String),
    InsertCode { lang: String, code: String },
    InsertTable(usize, usize),
    InsertImage(String),
    InsertFigure { url: String, caption: Option<String> },
    InsertLink { url: String, text: String },
    TableEditCell { block_id: uuid::Uuid, row: usize, col: usize, text: String },
    TableInsertRow,
    TableInsertColumn,
    TableDeleteRow,
    TableDeleteColumn,
    ListIndent,
    ListOutdent,
    Undo,
    Redo,
}
