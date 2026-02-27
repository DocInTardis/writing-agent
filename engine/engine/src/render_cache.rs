use std::collections::HashSet;
use uuid::Uuid;

#[derive(Debug, Default)]
pub struct RenderCache {
    dirty_blocks: HashSet<Uuid>,
    dirty_threshold: f32,
}

impl RenderCache {
    pub fn new() -> Self {
        Self { dirty_blocks: HashSet::new(), dirty_threshold: 0.05 }
    }

    pub fn mark_dirty(&mut self, id: Uuid) {
        self.dirty_blocks.insert(id);
    }

    pub fn clear(&mut self) {
        self.dirty_blocks.clear();
    }

    pub fn dirty_ratio(&self, total_blocks: usize) -> f32 {
        if total_blocks == 0 { return 0.0; }
        self.dirty_blocks.len() as f32 / total_blocks as f32
    }

    pub fn is_dirty(&self, id: Uuid) -> bool {
        self.dirty_blocks.contains(&id)
    }

    pub fn should_render(&self, id: Uuid, total_blocks: usize) -> bool {
        let ratio = self.dirty_ratio(total_blocks);
        if ratio == 0.0 {
            return true;
        }
        if ratio <= self.dirty_threshold {
            return self.is_dirty(id);
        }
        true
    }
}
