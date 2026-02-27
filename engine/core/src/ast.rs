use serde::{Deserialize, Serialize};
use std::sync::Arc;
use uuid::Uuid;

pub type SharedStr = Arc<str>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Document {
    pub id: Uuid,
    pub version: u64,
    pub blocks: Vec<Block>,
    pub metadata: Metadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Metadata {
    pub title: SharedStr,
    pub author: SharedStr,
    pub created_at: i64,
    pub updated_at: i64,
}

impl Default for Metadata {
    fn default() -> Self {
        Self {
            title: Arc::from(""),
            author: Arc::from(""),
            created_at: 0,
            updated_at: 0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Block {
    Heading {
        id: Uuid,
        level: u8,
        content: Vec<Inline>,
        dirty: bool,
    },
    Paragraph {
        id: Uuid,
        content: Vec<Inline>,
        dirty: bool,
    },
    List {
        id: Uuid,
        ordered: bool,
        items: Vec<ListItem>,
        dirty: bool,
    },
    Quote {
        id: Uuid,
        content: Vec<Block>,
        dirty: bool,
    },
    Code {
        id: Uuid,
        lang: SharedStr,
        code: SharedStr,
        dirty: bool,
    },
    Table {
        id: Uuid,
        rows: Vec<Vec<Cell>>,
        dirty: bool,
    },
    Figure {
        id: Uuid,
        url: SharedStr,
        caption: Option<SharedStr>,
        size: Option<FigureSize>,
        dirty: bool,
    },
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct FigureSize {
    pub width: f32,
    pub height: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ListItem {
    pub id: Uuid,
    pub content: Vec<Inline>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Cell {
    pub content: Vec<Inline>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Inline {
    Text { value: SharedStr },
    Styled { style: Style, content: Vec<Inline> },
    Link { url: SharedStr, text: Vec<Inline> },
    #[serde(rename = "codespan")]
    CodeSpan { value: SharedStr },
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct Style {
    pub bold: bool,
    pub italic: bool,
    pub underline: bool,
    pub strikethrough: bool,
}

impl Document {
    pub fn new() -> Self {
        Self {
            id: Uuid::new_v4(),
            version: 1,
            blocks: Vec::new(),
            metadata: Metadata {
                title: Arc::from(""),
                author: Arc::from(""),
                created_at: 0,
                updated_at: 0,
            },
        }
    }

    pub fn touch(&mut self) {
        self.version = self.version.saturating_add(1);
        self.metadata.updated_at = chrono::Utc::now().timestamp();
    }

    pub fn clear_dirty(&mut self) {
        for block in &mut self.blocks {
            block.set_dirty(false);
            if let Block::Quote { content, .. } = block {
                for inner in content {
                    inner.set_dirty(false);
                }
            }
        }
    }
}

impl Block {
    pub fn id(&self) -> Uuid {
        match self {
            Block::Heading { id, .. }
            | Block::Paragraph { id, .. }
            | Block::List { id, .. }
            | Block::Quote { id, .. }
            | Block::Code { id, .. }
            | Block::Table { id, .. }
            | Block::Figure { id, .. } => *id,
        }
    }

    pub fn is_dirty(&self) -> bool {
        match self {
            Block::Heading { dirty, .. }
            | Block::Paragraph { dirty, .. }
            | Block::List { dirty, .. }
            | Block::Quote { dirty, .. }
            | Block::Code { dirty, .. }
            | Block::Table { dirty, .. }
            | Block::Figure { dirty, .. } => *dirty,
        }
    }

    pub fn set_dirty(&mut self, value: bool) {
        match self {
            Block::Heading { dirty, .. }
            | Block::Paragraph { dirty, .. }
            | Block::List { dirty, .. }
            | Block::Quote { dirty, .. }
            | Block::Code { dirty, .. }
            | Block::Table { dirty, .. }
            | Block::Figure { dirty, .. } => *dirty = value,
        }
    }
}
