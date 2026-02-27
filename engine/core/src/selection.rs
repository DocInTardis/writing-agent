use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Position {
    pub block_id: Uuid,
    pub offset: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Selection {
    pub anchor: Position,
    pub focus: Position,
}

impl Selection {
    pub fn collapsed(pos: Position) -> Self {
        Self { anchor: pos, focus: pos }
    }

    pub fn is_collapsed(&self) -> bool {
        self.anchor == self.focus
    }
}
