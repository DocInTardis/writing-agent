use wa_core::Position;

use crate::{LayoutConfig, LayoutTree, SharedMeasurer, RealMeasurer};

pub struct HitTester {
    measurer: SharedMeasurer,
}

impl HitTester {
    pub fn new() -> Self {
        Self { measurer: SharedMeasurer(std::sync::Arc::new(RealMeasurer::new())) }
    }

    pub fn hit_test(&self, layout: &LayoutTree, config: &LayoutConfig, x: f32, y: f32, page_gap: f32) -> Option<Position> {
        let mut page_top = 0.0;
        for page in &layout.pages {
            let page_bottom = page_top + config.page_height;
            if y >= page_top && y <= page_bottom {
                let mut cursor_y = page_top + config.margin;
                for block in &page.blocks {
                    for line in &block.lines {
                        let line_height = config.metrics.font_size * config.metrics.line_height;
                        let line_top = cursor_y;
                        let line_bottom = cursor_y + line_height;
                        if y >= line_top && y <= line_bottom {
                            let mut acc = 0.0;
                            let mut offset = 0usize;
                            let mut buf = [0u8; 4];
                            for ch in line.text.chars() {
                                let w = self.measurer.0.measure(ch.encode_utf8(&mut buf), config.metrics);
                                if (config.margin + acc + w) >= x {
                                    break;
                                }
                                acc += w;
                                offset += 1;
                            }
                            return Some(Position { block_id: block.block_id, offset });
                        }
                        cursor_y += line_height;
                    }
                    cursor_y += config.metrics.font_size * 0.5;
                }
            }
            page_top = page_bottom + page_gap;
        }
        None
    }
}
