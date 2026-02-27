use eframe::{egui, App, Frame};
use wa_core::{Block, Document, Editor, EditorCommand, FigureSize, Inline, Style, import_html_rich};
use std::sync::Arc;
use wa_engine::{FontMetrics, LayoutCache, LayoutConfig, LayoutEngine, LayoutKind, RealMeasurer, RenderCache, TextMeasurer};
use arboard::Clipboard;

pub fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions::default();
    eframe::run_native(
        "Writing Agent Editor",
        options,
        Box::new(|_cc| Box::new(EditorApp::new())),
    )
}

struct EditorApp {
    editor: Editor,
    layout: LayoutEngine,
    cache: LayoutCache,
    render_cache: RenderCache,
    view_mode: ViewMode,
    measurer: RealMeasurer,
    ime_buffer: String,
    ime_active: bool,
    image_sizes: std::collections::HashMap<uuid::Uuid, (f32, f32)>,
    resizing_image: Option<(String, egui::Pos2)>,
    rect_select: Option<(egui::Pos2, egui::Pos2)>,
    extra_cursors: Vec<wa_core::Position>,
    table_focus: Option<(uuid::Uuid, usize, usize)>,
    layout_tree: Option<wa_engine::LayoutTree>,
    layout_version: u64,
    last_scroll_at: Option<std::time::Instant>,
    scroll_debounce: std::time::Duration,
    layout_paged_view: bool,
    layout_page_height: i32,
    hit_cache: std::collections::HashMap<(uuid::Uuid, usize), Vec<f32>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ViewMode {
    Paged,
    Scroll,
}

impl EditorApp {
    fn new() -> Self {
        let mut doc = Document::new();
        doc.blocks = vec![
            Block::Heading {
                id: uuid::Uuid::new_v4(),
                level: 1,
                content: vec![Inline::Text { value: Arc::from("示例标题") }],
                dirty: false,
            },
            Block::Paragraph {
                id: uuid::Uuid::new_v4(),
                content: vec![Inline::Text {
                    value: Arc::from("这里是 Rust + egui 引擎原型。开始输入即可修改内容。"),
                }],
                dirty: false,
            },
        ];
        Self {
            editor: Editor::new(doc),
            layout: LayoutEngine::new(),
            cache: LayoutCache::new(),
            render_cache: RenderCache::new(),
            view_mode: ViewMode::Paged,
            measurer: RealMeasurer::new(),
            ime_buffer: String::new(),
            ime_active: false,
            image_sizes: std::collections::HashMap::new(),
            resizing_image: None,
            rect_select: None,
            extra_cursors: Vec::new(),
            table_focus: None,
            layout_tree: None,
            layout_version: 0,
            last_scroll_at: None,
            scroll_debounce: std::time::Duration::from_millis(80),
            layout_paged_view: true,
            layout_page_height: LayoutConfig::default().page_height as i32,
            hit_cache: std::collections::HashMap::new(),
        }
    }


    fn block_to_text(block: &Block) -> String {
        fn inline_to_text(inlines: &[Inline], out: &mut String) {
            for inline in inlines {
                match inline {
                    Inline::Text { value } => out.push_str(value.as_ref()),
                    Inline::CodeSpan { value } => out.push_str(value.as_ref()),
                    Inline::Link { text, .. } => inline_to_text(text, out),
                    Inline::Styled { content, .. } => inline_to_text(content, out),
                }
            }
        }
        let mut out = String::new();
        match block {
            Block::Heading { content, .. } | Block::Paragraph { content, .. } => {
                inline_to_text(content, &mut out);
            }
            Block::List { items, .. } => {
                for (i, item) in items.iter().enumerate() {
                    if i > 0 { out.push('\n'); }
                    inline_to_text(&item.content, &mut out);
                }
            }
            Block::Quote { content, .. } => {
                for (i, b) in content.iter().enumerate() {
                    if i > 0 { out.push('\n'); }
                    if let Block::Paragraph { content, .. } = b {
                        inline_to_text(content, &mut out);
                    }
                }
            }
            Block::Code { code, .. } => out.push_str(code.as_ref()),
            Block::Table { rows, .. } => {
                for (ri, row) in rows.iter().enumerate() {
                    if ri > 0 { out.push('\n'); }
                    for (ci, cell) in row.iter().enumerate() {
                        if ci > 0 { out.push('\t'); }
                        inline_to_text(&cell.content, &mut out);
                    }
                }
            }
            Block::Figure { caption, .. } => {
                if let Some(c) = caption { out.push_str(c.as_ref()); }
            }
        }
        out
    }

    fn selection_text(&self) -> String {
        let sel = self.editor.selection;
        if let Some(block) = self.editor.doc.blocks.iter().find(|b| b.id() == sel.focus.block_id) {
            let text = Self::block_to_text(block);
            let start = sel.anchor.offset.min(sel.focus.offset);
            let end = sel.anchor.offset.max(sel.focus.offset);
            let mut s_idx = 0usize;
            let mut e_idx = text.len();
            let mut count = 0usize;
            for (idx, _) in text.char_indices() {
                if count == start { s_idx = idx; }
                if count == end { e_idx = idx; break; }
                count += 1;
            }
            return text[s_idx..e_idx].to_string();
        }
        String::new()
    }

    fn selection_html(&self) -> String {
        let plain = self.selection_text();
        if plain.is_empty() {
            return String::new();
        }
        format!("<p>{}</p>", plain.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;"))
    }

    fn apply_to_cursors(&mut self, cmd: EditorCommand, extra: &[wa_core::Position]) {
        if extra.is_empty() {
            self.editor.execute(cmd);
            return;
        }
        let mut positions = Vec::with_capacity(extra.len() + 1);
        positions.push(self.editor.selection.focus);
        for p in extra {
            if !positions.iter().any(|x| x.block_id == p.block_id && x.offset == p.offset) {
                positions.push(*p);
            }
        }
        for pos in &positions {
            self.editor.selection = wa_core::Selection::collapsed(*pos);
            self.editor.execute(cmd.clone());
        }
        self.editor.selection = wa_core::Selection::collapsed(positions[0]);
    }

    fn find_table_cell(&self, page: &wa_engine::Page, config: &LayoutConfig, rect: egui::Rect, pos: egui::Pos2) -> Option<(uuid::Uuid, usize, usize)> {
        let mut cursor_y = rect.top() + config.margin;
        for block in &page.blocks {
            let start_y = cursor_y;
            let block_height = block.height;
            let end_y = start_y + block_height;
            if pos.y >= start_y && pos.y <= end_y {
                if let Some(doc_block) = self.editor.doc.blocks.iter().find(|b| b.id() == block.block_id) {
                    if let Block::Table { rows, .. } = doc_block {
                        if rows.is_empty() || rows[0].is_empty() {
                            return None;
                        }
                        let row_h = config.metrics.font_size * config.metrics.line_height;
                        let row = ((pos.y - start_y) / row_h).floor() as usize;
                        let cols = rows[0].len();
                        let width = config.page_width - config.margin * 2.0;
                        let col_w = width / cols as f32;
                        let local_x = (pos.x - (rect.left() + config.margin)).max(0.0);
                        let col = (local_x / col_w).floor() as usize;
                        return Some((block.block_id, row.min(rows.len() - 1), col.min(cols - 1)));
                    }
                }
            }
            for _line in &block.lines {
                cursor_y += config.metrics.font_size * config.metrics.line_height;
            }
            cursor_y += config.metrics.font_size * 0.5;
        }
        None
    }
    fn handle_input(&mut self, ctx: &egui::Context) {
        let mut to_insert = String::new();
        let mut copy = false;
        let mut paste = false;
        let mut paste_image = false;
        let mut backspace = false;
        let mut bold = false;
        let mut italic = false;
        let mut heading = None;
        let extra = self.extra_cursors.clone();
        ctx.input(|i| {
            for ev in &i.events {
                match ev {
                    egui::Event::CompositionStart => {
                        self.ime_active = true;
                        self.ime_buffer.clear();
                    }
                    egui::Event::CompositionUpdate(text) => {
                        self.ime_active = true;
                        self.ime_buffer = text.clone();
                    }
                    egui::Event::CompositionEnd(text) => {
                        self.ime_active = false;
                        if !text.is_empty() {
                            to_insert.push_str(text);
                        }
                        self.ime_buffer.clear();
                    }
                    egui::Event::Text(text) => {
                        if !self.ime_active {
                            to_insert.push_str(text);
                        }
                    }
                    egui::Event::Paste(text) => {
                        if text.contains("<") && text.contains(">") {
                            self.editor.checkpoint();
                            let mut doc = import_html_rich(text);
                            if !doc.blocks.is_empty() {
                                self.editor.doc.blocks.extend(doc.blocks.drain(..));
                                self.editor.doc.touch();
                            } else {
                                to_insert.push_str(text);
                            }
                        } else {
                            to_insert.push_str(text);
                        }
                    }
                    egui::Event::Key { key, pressed, modifiers, .. } => {
                        if !*pressed {
                            continue;
                        }
                        if *key == egui::Key::Tab {
                            if modifiers.shift {
                                self.apply_to_cursors(EditorCommand::ListOutdent, &extra);
                            } else {
                                self.apply_to_cursors(EditorCommand::ListIndent, &extra);
                            }
                        }
                        if *key == egui::Key::Backspace {
                            backspace = true;
                        }
                        if modifiers.ctrl && *key == egui::Key::C {
                            copy = true;
                        }
                        if modifiers.ctrl && *key == egui::Key::V {
                            paste = true;
                            paste_image = true;
                        }
                        if modifiers.ctrl && *key == egui::Key::B {
                            bold = true;
                        }
                        if modifiers.ctrl && *key == egui::Key::I {
                            italic = true;
                        }
                        if modifiers.ctrl && *key == egui::Key::Num1 {
                            heading = Some(1);
                        }
                        if modifiers.ctrl && *key == egui::Key::Num2 {
                            heading = Some(2);
                        }
                    }
                    _ => {}
                }
            }
        });

        let had_insert = !to_insert.is_empty();
        if had_insert {
            let insert_text = std::mem::take(&mut to_insert);
            if let Some((bid, row, col)) = self.table_focus {
                if let Some(block) = self.editor.doc.blocks.iter().find(|b| b.id() == bid) {
                    if let Block::Table { rows, .. } = block {
                        if let Some(r) = rows.get(row) {
                            if let Some(c) = r.get(col) {
                                let mut current = String::new();
                                for inline in &c.content {
                                    if let Inline::Text { value } = inline {
                                        current.push_str(value.as_ref());
                                    }
                                }
                                current.push_str(&insert_text);
                                self.editor.execute(EditorCommand::TableEditCell { block_id: bid, row, col, text: current });
                            }
                        }
                    }
                }
            } else {
                self.apply_to_cursors(EditorCommand::InsertText(insert_text), &extra);
            }
        }
        if backspace {
            if let Some((bid, row, col)) = self.table_focus {
                if let Some(block) = self.editor.doc.blocks.iter().find(|b| b.id() == bid) {
                    if let Block::Table { rows, .. } = block {
                        if let Some(r) = rows.get(row) {
                            if let Some(c) = r.get(col) {
                                let mut current = String::new();
                                for inline in &c.content {
                                    if let Inline::Text { value } = inline {
                                        current.push_str(value.as_ref());
                                    }
                                }
                                current.pop();
                                self.editor.execute(EditorCommand::TableEditCell { block_id: bid, row, col, text: current });
                            }
                        }
                    }
                }
            } else {
                self.apply_to_cursors(EditorCommand::DeleteSelection, &extra);
            }
        }
        if bold {
            self.apply_to_cursors(EditorCommand::ApplyStyle(Style { bold: true, italic: false, underline: false, strikethrough: false }), &extra);
        }
        if italic {
            self.apply_to_cursors(EditorCommand::ApplyStyle(Style { bold: false, italic: true, underline: false, strikethrough: false }), &extra);
        }
        if let Some(level) = heading {
            self.apply_to_cursors(EditorCommand::SetHeading(level), &extra);
        }

        if copy {
            let plain = self.selection_text();
            let html = self.selection_html();
            if !plain.is_empty() {
                ctx.output_mut(|o| o.copied_text = plain.clone());
                if let Ok(mut cb) = Clipboard::new() {
                    let _ = cb.set_text(if html.is_empty() { plain } else { html });
                }
            }
        }

        if paste && !had_insert && paste_image {
            if let Ok(mut cb) = Clipboard::new() {
                if let Ok(image) = cb.get_image() {
                    let id = uuid::Uuid::new_v4();
                    self.image_sizes.insert(id, (image.width as f32, image.height as f32));
                    self.editor.doc.blocks.push(wa_core::Block::Figure {
                        id,
                        url: std::sync::Arc::from("clipboard://image"),
                        caption: Some(std::sync::Arc::from("?????")),
                        size: Some(wa_core::FigureSize { width: image.width as f32, height: image.height as f32 }),
                        dirty: true,
                    });
                    self.editor.doc.touch();
                }
            }
        }
    }

    fn draw_block_frame(painter: &egui::Painter, rect: egui::Rect) {
        painter.rect_stroke(rect, 4.0, egui::Stroke::new(1.0, egui::Color32::from_gray(210)));
    }


    fn hit_test_page(&mut self, page: &wa_engine::Page, config: &LayoutConfig, rect: egui::Rect, pos: egui::Pos2) -> Option<wa_core::Position> {
        let mut cursor_y = rect.top() + config.margin;
        for (b_idx, block) in page.blocks.iter().enumerate() {
            for (line_idx, _line) in block.lines.iter().enumerate() {
                let line_height = config.metrics.font_size * config.metrics.line_height;
                let line_top = cursor_y;
                let line_bottom = cursor_y + line_height;
                if pos.y >= line_top && pos.y <= line_bottom {
                    let local_x = (pos.x - (rect.left() + config.margin)).max(0.0);
                    let key = (block.block_id, line_idx);
                    if let Some(offsets) = self.hit_cache.get(&key) {
                        let mut offset = 0usize;
                        if let Err(idx) = offsets.binary_search_by(|v| v.partial_cmp(&local_x).unwrap_or(std::cmp::Ordering::Greater)) {
                            offset = idx.saturating_sub(1);
                        } else if let Ok(idx) = offsets.binary_search_by(|v| v.partial_cmp(&local_x).unwrap_or(std::cmp::Ordering::Greater)) {
                            offset = idx.saturating_sub(1);
                        }
                        return Some(wa_core::Position { block_id: block.block_id, offset });
                    }
                    return self.hit_test_page_uncached(page, config, rect, pos);
                }
                cursor_y += line_height;
            }
            let block_end = cursor_y;
            if pos.y > block_end && pos.y <= block_end + (config.metrics.font_size * 0.5) {
                let offset = block.lines.last()
                    .map(|l| l.text.chars().count())
                    .unwrap_or(0);
                return Some(wa_core::Position { block_id: block.block_id, offset });
            }
            cursor_y += config.metrics.font_size * 0.5;
            if b_idx > 0 && cursor_y > rect.bottom() {
                break;
            }
        }
        None
    }

    fn hit_test_page_uncached(&mut self, page: &wa_engine::Page, config: &LayoutConfig, rect: egui::Rect, pos: egui::Pos2) -> Option<wa_core::Position> {
        let mut cursor_y = rect.top() + config.margin;
        for (b_idx, block) in page.blocks.iter().enumerate() {
            for (line_idx, line) in block.lines.iter().enumerate() {
                let line_height = config.metrics.font_size * config.metrics.line_height;
                let line_top = cursor_y;
                let line_bottom = cursor_y + line_height;
                if pos.y >= line_top && pos.y <= line_bottom {
                    let local_x = (pos.x - (rect.left() + config.margin)).max(0.0);
                    let mut acc = 0.0f32;
                    let mut offsets = Vec::with_capacity(line.text.chars().count() + 1);
                    offsets.push(0.0);
                    let mut buf = [0u8; 4];
                    for ch in line.text.chars() {
                        let w = self.measurer.measure(ch.encode_utf8(&mut buf), config.metrics);
                        acc += w;
                        offsets.push(acc);
                    }
                    self.hit_cache.insert((block.block_id, line_idx), offsets.clone());
                    let mut offset = 0usize;
                    if let Err(idx) = offsets.binary_search_by(|v| v.partial_cmp(&local_x).unwrap_or(std::cmp::Ordering::Greater)) {
                        offset = idx.saturating_sub(1);
                    } else if let Ok(idx) = offsets.binary_search_by(|v| v.partial_cmp(&local_x).unwrap_or(std::cmp::Ordering::Greater)) {
                        offset = idx.saturating_sub(1);
                    }
                    return Some(wa_core::Position { block_id: block.block_id, offset });
                }
                cursor_y += line_height;
            }
            cursor_y += config.metrics.font_size * 0.5;
            if b_idx > 0 && cursor_y > rect.bottom() {
                break;
            }
        }
        None
    }

    fn draw_page_at(&mut self, ui: &mut egui::Ui, page: &wa_engine::Page, config: &LayoutConfig, rect: egui::Rect, show_frame: bool) {
        let painter = ui.painter_at(rect);
        if show_frame {
            painter.rect_filled(rect, 6.0, egui::Color32::from_rgb(250, 248, 242));
            painter.rect_stroke(rect, 6.0, egui::Stroke::new(1.0, egui::Color32::from_gray(200)));
        }

        let mut cursor_y = rect.top() + config.margin;
        let block_gap = config.metrics.font_size * 0.5;
        let clip = ui.clip_rect();
        let ratio = self.render_cache.dirty_ratio(page.blocks.len());
        let mut idx = 0usize;
        while idx < page.blocks.len() {
            let block = &page.blocks[idx];
            let block_top = cursor_y;
            let block_bottom = block_top + block.height;
            if block_bottom < clip.top() {
                cursor_y = block_bottom + block_gap;
                idx += 1;
                continue;
            }
            if block_top > clip.bottom() {
                break;
            }
            if ratio > 0.0 && ratio <= 0.05 && !self.render_cache.is_dirty(block.block_id) {
                let mut skip_height = block.height + block_gap;
                let mut j = idx + 1;
                while j < page.blocks.len() {
                    let next = &page.blocks[j];
                    if self.render_cache.is_dirty(next.block_id) {
                        break;
                    }
                    skip_height += next.height + block_gap;
                    j += 1;
                }
                cursor_y += skip_height;
                idx = j;
                continue;
            }
            let block_rect = egui::Rect::from_min_max(
                egui::pos2(rect.left() + config.margin, block_top),
                egui::pos2(rect.right() - config.margin, block_bottom),
            );
            let font_id = match block.kind {
                LayoutKind::Heading(level) => {
                    let size = match level {
                        1 => 20.0,
                        2 => 18.0,
                        _ => 16.0,
                    };
                    egui::FontId::proportional(size)
                }
                _ => egui::FontId::proportional(config.metrics.font_size),
            };
            let start_y = block_top;
            let mut line_y = block_top;
            for line in &block.lines {
                painter.text(
                    egui::pos2(rect.left() + config.margin, line_y),
                    egui::Align2::LEFT_TOP,
                    &line.text,
                    font_id.clone(),
                    egui::Color32::from_rgb(40, 30, 20),
                );
                line_y += config.metrics.font_size * config.metrics.line_height;
            }
            if self.editor.selection.focus.block_id == block.block_id {
                let caret_x = rect.left() + config.margin;
                let caret_rect = egui::Rect::from_min_size(
                    egui::pos2(caret_x, start_y),
                    egui::vec2(2.0, config.metrics.font_size * config.metrics.line_height),
                );
                painter.rect_filled(caret_rect, 0.0, egui::Color32::from_rgb(30, 30, 30));
            }
            match block.kind {
                LayoutKind::Quote => {
                    if show_frame {
                        Self::draw_block_frame(&painter, block_rect);
                    }
                }
                LayoutKind::Code => {
                    painter.rect_filled(block_rect, 4.0, egui::Color32::from_rgb(245, 242, 235));
                }
                LayoutKind::Table => {
                    if let Some((bid, row, col)) = self.table_focus {
                        if bid == block.block_id {
                            if let Some(doc_block) = self.editor.doc.blocks.iter().find(|b| b.id() == bid) {
                                if let Block::Table { rows, .. } = doc_block {
                                    if !rows.is_empty() {
                                        let row_h = config.metrics.font_size * config.metrics.line_height;
                                        let cols = rows[0].len().max(1);
                                        let width = block_rect.width();
                                        let col_w = width / cols as f32;
                                        let x0 = block_rect.left() + col_w * col as f32;
                                        let y0 = block_rect.top() + row_h * row as f32;
                                        let cell_rect = egui::Rect::from_min_size(egui::pos2(x0, y0), egui::vec2(col_w, row_h));
                                        painter.rect_stroke(cell_rect, 2.0, egui::Stroke::new(1.0, egui::Color32::from_rgb(90, 120, 200)));
                                    }
                                }
                            }
                        }
                    }
                    if show_frame {
                        Self::draw_block_frame(&painter, block_rect);
                    }
                }
                LayoutKind::Figure => {
                    painter.rect_filled(block_rect, 6.0, egui::Color32::from_rgb(238, 232, 220));
                    if let Some(meta) = &block.meta {
                        let (w, h) = self.image_sizes.get(&block.block_id)
                            .copied()
                            .unwrap_or((meta.width, meta.height));
                        let max_w = (block_rect.width() - 16.0).max(1.0);
                        let max_h = (block_rect.height() - 16.0).max(1.0);
                        let img_rect = egui::Rect::from_min_size(
                            egui::pos2(block_rect.left() + 8.0, block_rect.top() + 8.0),
                            egui::vec2(w.min(max_w), h.min(max_h)),
                        );
                        painter.rect_filled(img_rect, 4.0, egui::Color32::from_rgb(210, 200, 185));
                        painter.text(
                            img_rect.center(),
                            egui::Align2::CENTER_CENTER,
                            "图片",
                            egui::FontId::proportional(12.0),
                            egui::Color32::from_rgb(90, 80, 70),
                        );
                        let handle = egui::Rect::from_min_size(
                            egui::pos2(img_rect.right() - 8.0, img_rect.bottom() - 8.0),
                            egui::vec2(8.0, 8.0),
                        );
                        painter.rect_filled(handle, 2.0, egui::Color32::from_rgb(120, 110, 100));
                        let resp = ui.interact(handle, egui::Id::new(block.block_id), egui::Sense::drag());
                        if resp.drag_started() {
                            if let Some(pos) = resp.interact_pointer_pos() {
                                self.resizing_image = Some((block.block_id.to_string(), pos));
                            }
                        }
                    }
                    if show_frame {
                        Self::draw_block_frame(&painter, block_rect);
                    }
                }
                _ => {}
            }
            cursor_y = block_bottom + block_gap;
            idx += 1;
        }

        if self.ime_active && !self.ime_buffer.is_empty() {
            let overlay_rect = egui::Rect::from_min_size(
                egui::pos2(rect.left() + config.margin, rect.bottom() - 48.0),
                egui::vec2(260.0, 32.0),
            );
            painter.rect_filled(overlay_rect, 6.0, egui::Color32::from_rgb(255, 255, 255));
            painter.rect_stroke(overlay_rect, 6.0, egui::Stroke::new(1.0, egui::Color32::from_gray(180)));
            painter.text(
                overlay_rect.min + egui::vec2(8.0, 6.0),
                egui::Align2::LEFT_TOP,
                &self.ime_buffer,
                egui::FontId::proportional(14.0),
                egui::Color32::from_rgb(80, 70, 60),
            );
        }
    }
}

impl App for EditorApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut Frame) {
        self.handle_input(ctx);

        let mut scrolled = false;
        ctx.input(|i| {
            if i.raw_scroll_delta.y.abs() > 0.0 {
                scrolled = true;
            }
        });
        if scrolled {
            self.last_scroll_at = Some(std::time::Instant::now());
        }
        let is_scrolling = self.last_scroll_at
            .map(|t| t.elapsed() < self.scroll_debounce)
            .unwrap_or(false);

        if let Some((block_id, start)) = self.resizing_image.clone() {
            if let Some(pos) = ctx.input(|i| i.pointer.interact_pos()) {
                let dx = (pos.x - start.x).max(1.0);
                let dy = (pos.y - start.y).max(1.0);
                if let Ok(uid) = uuid::Uuid::parse_str(&block_id) {
                    self.image_sizes.insert(uid, (dx, dy));
                    for block in &mut self.editor.doc.blocks {
                        if let wa_core::Block::Figure { id, size, .. } = block {
                            if *id == uid {
                                *size = Some(FigureSize { width: dx, height: dy });
                                block.set_dirty(true);
                            }
                        }
                    }
                    self.editor.doc.touch();
                }
            }
            if ctx.input(|i| !i.pointer.primary_down()) {
                self.resizing_image = None;
            }
        }

        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.label("视图：");
                ui.selectable_value(&mut self.view_mode, ViewMode::Paged, "分页");
                ui.selectable_value(&mut self.view_mode, ViewMode::Scroll, "滚动");
                ui.separator();
                if ui.button("列表").clicked() {
                    self.editor.execute(EditorCommand::InsertList(false));
                }
                if ui.button("引用").clicked() {
                    self.editor.execute(EditorCommand::InsertQuote("引用内容".to_string()));
                }
                if ui.button("代码块").clicked() {
                    self.editor.execute(EditorCommand::InsertCode {
                        lang: "rs".to_string(),
                        code: "fn main() {}".to_string(),
                    });
                }
                if ui.button("表格").clicked() {
                    self.editor.execute(EditorCommand::InsertTable(3, 3));
                }
                if ui.button("图" ).clicked() {
                    let id = uuid::Uuid::new_v4();
                    self.image_sizes.insert(id, (320.0, 180.0));
                    self.editor.doc.blocks.push(wa_core::Block::Figure {
                        id,
                        url: std::sync::Arc::from("local://placeholder"),
                        caption: Some(std::sync::Arc::from("示意图")),
                        size: Some(wa_core::FigureSize { width: 320.0, height: 180.0 }),
                        dirty: true,
                    });
                }
                ui.separator();
                if ui.button("+行").clicked() {
                    self.editor.execute(EditorCommand::TableInsertRow);
                }
                if ui.button("+列").clicked() {
                    self.editor.execute(EditorCommand::TableInsertColumn);
                }
                if ui.button("-行").clicked() {
                    self.editor.execute(EditorCommand::TableDeleteRow);
                }
                if ui.button("-列").clicked() {
                    self.editor.execute(EditorCommand::TableDeleteColumn);
                }
            });
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            let paged_view = self.view_mode == ViewMode::Paged;
            let mut base = LayoutConfig::default();
            let viewport_h = ui.available_height().max(600.0);
            let page_height = if paged_view { base.page_height } else { viewport_h };
            base.page_height = page_height;
            let config = LayoutConfig {
                paged: true,
                metrics: FontMetrics { font_size: 14.0, line_height: 1.7 },
                ..base
            };
            let config_changed = self.layout_paged_view != paged_view
                || (self.layout_page_height - page_height as i32).abs() > 1;
            if self.editor.doc.version != self.layout_version || config_changed {
                self.render_cache.clear();
                self.hit_cache.clear();
                for block in &self.editor.doc.blocks {
                    if block.is_dirty() {
                        self.render_cache.mark_dirty(block.id());
                    }
                }
                let layout = self.layout.layout_cached(&self.editor.doc, &config, &mut self.cache);
                self.layout_tree = Some(layout);
                self.layout_version = self.editor.doc.version;
                self.layout_paged_view = paged_view;
                self.layout_page_height = page_height as i32;
                self.editor.doc.clear_dirty();
            }
            let layout = self.layout_tree.as_ref().unwrap().clone();
            egui::ScrollArea::vertical().show(ui, |ui| {
                let clip = ui.clip_rect();
                let gap = if paged_view { 24.0 } else { 0.0 };
                let page_h = config.page_height + gap;
                let buf_pages = 1usize;
                let total_pages = layout.pages.len();
                let start_idx = ((clip.top() / page_h).floor() as isize - buf_pages as isize).max(0) as usize;
                let end_idx = ((clip.bottom() / page_h).ceil() as isize + buf_pages as isize).min(total_pages as isize) as usize;
                for (idx, page) in layout.pages.iter().enumerate() {
                    if idx < start_idx || idx >= end_idx {
                        ui.add_space(page_h);
                        continue;
                    }
                    let (rect, resp) = ui.allocate_exact_size(
                        egui::vec2(config.page_width, config.page_height),
                        egui::Sense::click(),
                    );
                    if resp.clicked() {
                        if resp.ctx.input(|i| i.modifiers.alt) {
                            if let Some(pos) = resp.interact_pointer_pos() {
                                if let Some(hit) = self.hit_test_page(page, &config, rect, pos) {
                                    if let Some(idx) = self.extra_cursors.iter().position(|p| *p == hit) {
                                        self.extra_cursors.remove(idx);
                                    } else {
                                        self.extra_cursors.push(hit);
                                    }
                                }
                            }
                        }
                        if let Some(pos) = resp.interact_pointer_pos() {
                            if let Some(hit) = self.hit_test_page(page, &config, rect, pos) {
                                self.editor.selection = wa_core::Selection::collapsed(hit);
                                self.table_focus = self.find_table_cell(page, &config, rect, pos);
                                if !resp.ctx.input(|i| i.modifiers.alt) {
                                    self.extra_cursors.clear();
                                }
                            }
                        }
                    }
                    if resp.dragged() && !is_scrolling {
                        if resp.ctx.input(|i| i.modifiers.alt) {
                            if let Some(pos) = resp.interact_pointer_pos() {
                                if let Some((start, _)) = self.rect_select {
                                    self.rect_select = Some((start, pos));
                                } else {
                                    self.rect_select = Some((pos, pos));
                                }
                            }
                            continue;
                        }
                        if let Some(pos) = resp.interact_pointer_pos() {
                            if let Some(hit) = self.hit_test_page(page, &config, rect, pos) {
                                self.editor.selection.focus = hit;
                            }
                        }
                    }
                    if let Some((a, b)) = self.rect_select {
                        if !resp.ctx.input(|i| i.pointer.primary_down()) {
                            if let Some(start) = self.hit_test_page(page, &config, rect, a) {
                                if let Some(end) = self.hit_test_page(page, &config, rect, b) {
                                    self.editor.selection = wa_core::Selection { anchor: start, focus: end };
                                }
                            }
                            self.rect_select = None;
                        }
                    }
                    self.draw_page_at(ui, page, &config, rect, paged_view);
                    ui.add_space(gap);
                }
            });
        });
    }
}
