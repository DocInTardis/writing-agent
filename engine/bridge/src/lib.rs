use wasm_bindgen::prelude::*;
use wa_core::{Document, Editor, EditorCommand, Block, Inline, Style};
use wa_engine::{LayoutEngine, LayoutCache, LayoutConfig};
use serde::Serialize;
use std::sync::Arc;

#[wasm_bindgen]
pub struct WasmEditor {
    editor: Editor,
    layout_engine: LayoutEngine,
    layout_cache: LayoutCache,
}

#[wasm_bindgen]
impl WasmEditor {
    #[wasm_bindgen(constructor)]
    pub fn new() -> Self {
        console_error_panic_hook::set_once();
        Self {
            editor: Editor::new(Document::new()),
            layout_engine: LayoutEngine::new(),
            layout_cache: LayoutCache::new(),
        }
    }

    #[wasm_bindgen(js_name = loadJson)]
    pub fn load_json(&mut self, json: &str) -> Result<(), JsValue> {
        let doc: Document = serde_json::from_str(json)
            .map_err(|e| JsValue::from_str(&format!("JSON解析失败: {}", e)))?;
        self.editor = Editor::new(doc);
        Ok(())
    }

    #[wasm_bindgen(js_name = exportJson)]
    pub fn export_json(&self) -> Result<String, JsValue> {
        serde_json::to_string(&self.editor.doc)
            .map_err(|e| JsValue::from_str(&format!("JSON序列化失败: {}", e)))
    }

    #[wasm_bindgen(js_name = insertText)]
    pub fn insert_text(&mut self, text: &str) {
        self.editor.execute(EditorCommand::InsertText(text.to_string()));
    }

    #[wasm_bindgen(js_name = deleteBackward)]
    pub fn delete_backward(&mut self) {
        self.editor.execute(EditorCommand::DeleteSelection);
    }

    #[wasm_bindgen(js_name = toggleBold)]
    pub fn toggle_bold(&mut self) {
        let mut style = Style::default();
        style.bold = true;
        self.editor.execute(EditorCommand::ApplyStyle(style));
    }

    #[wasm_bindgen(js_name = toggleItalic)]
    pub fn toggle_italic(&mut self) {
        let mut style = Style::default();
        style.italic = true;
        self.editor.execute(EditorCommand::ApplyStyle(style));
    }

    #[wasm_bindgen(js_name = toggleUnderline)]
    pub fn toggle_underline(&mut self) {
        let mut style = Style::default();
        style.underline = true;
        self.editor.execute(EditorCommand::ApplyStyle(style));
    }

    #[wasm_bindgen(js_name = toggleStrikethrough)]
    pub fn toggle_strikethrough(&mut self) {
        let mut style = Style::default();
        style.strikethrough = true;
        self.editor.execute(EditorCommand::ApplyStyle(style));
    }

    #[wasm_bindgen(js_name = setHeading)]
    pub fn set_heading(&mut self, level: u8) {
        self.editor.execute(EditorCommand::SetHeading(level));
    }

    #[wasm_bindgen(js_name = insertList)]
    pub fn insert_list(&mut self, ordered: bool) {
        self.editor.execute(EditorCommand::InsertList(ordered));
    }

    #[wasm_bindgen(js_name = insertTable)]
    pub fn insert_table(&mut self, rows: usize, cols: usize) {
        self.editor.execute(EditorCommand::InsertTable(rows, cols));
    }

    #[wasm_bindgen(js_name = insertCode)]
    pub fn insert_code(&mut self, lang: &str, code: &str) {
        self.editor.execute(EditorCommand::InsertCode {
            lang: lang.to_string(),
            code: code.to_string(),
        });
    }

    #[wasm_bindgen(js_name = insertImage)]
    pub fn insert_image(&mut self, url: &str) {
        self.editor.execute(EditorCommand::InsertImage(url.to_string()));
    }

    #[wasm_bindgen(js_name = insertFigure)]
    pub fn insert_figure(&mut self, url: &str, caption: Option<String>) {
        self.editor.execute(EditorCommand::InsertFigure {
            url: url.to_string(),
            caption,
        });
    }

    #[wasm_bindgen(js_name = insertQuote)]
    pub fn insert_quote(&mut self, text: &str) {
        self.editor.execute(EditorCommand::InsertQuote(text.to_string()));
    }

    #[wasm_bindgen(js_name = insertLink)]
    pub fn insert_link(&mut self, url: &str, text: &str) {
        self.editor.execute(EditorCommand::InsertLink {
            url: url.to_string(),
            text: text.to_string(),
        });
    }

    #[wasm_bindgen(js_name = tableInsertRow)]
    pub fn table_insert_row(&mut self) {
        self.editor.execute(EditorCommand::TableInsertRow);
    }

    #[wasm_bindgen(js_name = tableInsertColumn)]
    pub fn table_insert_column(&mut self) {
        self.editor.execute(EditorCommand::TableInsertColumn);
    }

    #[wasm_bindgen(js_name = tableDeleteRow)]
    pub fn table_delete_row(&mut self) {
        self.editor.execute(EditorCommand::TableDeleteRow);
    }

    #[wasm_bindgen(js_name = tableDeleteColumn)]
    pub fn table_delete_column(&mut self) {
        self.editor.execute(EditorCommand::TableDeleteColumn);
    }

    #[wasm_bindgen(js_name = listIndent)]
    pub fn list_indent(&mut self) {
        self.editor.execute(EditorCommand::ListIndent);
    }

    #[wasm_bindgen(js_name = listOutdent)]
    pub fn list_outdent(&mut self) {
        self.editor.execute(EditorCommand::ListOutdent);
    }

    #[wasm_bindgen(js_name = undo)]
    pub fn undo(&mut self) {
        self.editor.execute(EditorCommand::Undo);
    }

    #[wasm_bindgen(js_name = redo)]
    pub fn redo(&mut self) {
        self.editor.execute(EditorCommand::Redo);
    }

    #[wasm_bindgen(js_name = getCursorPosition)]
    pub fn get_cursor_position(&self) -> JsValue {
        let pos = self.editor.selection.focus;
        serde_wasm_bindgen::to_value(&serde_json::json!({
            "blockId": pos.block_id.to_string(),
            "offset": pos.offset
        })).unwrap_or(JsValue::NULL)
    }

    #[wasm_bindgen(js_name = getStats)]
    pub fn get_stats(&self) -> JsValue {
        let char_count: usize = self.editor.doc.blocks.iter().map(|b| {
            match b {
                Block::Paragraph { content, .. } | Block::Heading { content, .. } => {
                    content.iter().map(|i| match i {
                        Inline::Text { value } => value.chars().count(),
                        Inline::CodeSpan { value } => value.chars().count(),
                        Inline::Link { text, .. } => text.iter().map(|t| match t {
                            Inline::Text { value } => value.chars().count(),
                            _ => 0,
                        }).sum(),
                        Inline::Styled { content, .. } => content.iter().map(|t| match t {
                            Inline::Text { value } => value.chars().count(),
                            _ => 0,
                        }).sum(),
                    }).sum()
                }
                _ => 0,
            }
        }).sum();

        serde_wasm_bindgen::to_value(&serde_json::json!({
            "charCount": char_count,
            "blockCount": self.editor.doc.blocks.len(),
            "readingTime": (char_count as f64 / 400.0).ceil() as usize
        })).unwrap_or(JsValue::NULL)
    }

    #[wasm_bindgen(js_name = layout)]
    pub fn layout(&mut self, width: f32) -> Result<JsValue, JsValue> {
        let config = LayoutConfig {
            page_width: width,
            ..Default::default()
        };
        
        let layout_tree = self.layout_engine.layout_cached(
            &self.editor.doc,
            &config,
            &mut self.layout_cache,
        );

        let mut blocks_info = Vec::new();
        for page in &layout_tree.pages {
            for block in &page.blocks {
                blocks_info.push(serde_json::json!({
                    "id": block.block_id.to_string(),
                    "height": block.height,
                    "lines": block.lines.len()
                }));
            }
        }

        serde_wasm_bindgen::to_value(&blocks_info)
            .map_err(|e| JsValue::from_str(&format!("布局序列化失败: {}", e)))
    }

    #[wasm_bindgen(js_name = exportMarkdown)]
    pub fn export_markdown(&self) -> String {
        wa_core::export_markdown(&self.editor.doc)
    }

    #[wasm_bindgen(js_name = importMarkdown)]
    pub fn import_markdown(&mut self, md: &str) -> Result<(), JsValue> {
        let doc = wa_core::import_markdown(md);
        self.editor = Editor::new(doc);
        Ok(())
    }

    #[wasm_bindgen(js_name = find)]
    pub fn find(&self, query: &str) -> JsValue {
        let q = query;
        if q.is_empty() {
            let empty: Vec<FindHit> = Vec::new();
            return serde_wasm_bindgen::to_value(&empty).unwrap_or(JsValue::NULL);
        }
        let mut hits: Vec<FindHit> = Vec::new();
        let q_len = q.chars().count();
        for (block_index, block) in self.editor.doc.blocks.iter().enumerate() {
            let text = block_plain_text(block);
            if text.is_empty() {
                continue;
            }
            for (byte_idx, _) in text.match_indices(q) {
                let start = text[..byte_idx].chars().count();
                let end = start + q_len;
                let snippet = build_snippet(&text, start, end);
                hits.push(FindHit {
                    block_id: block.id().to_string(),
                    block_index,
                    start,
                    end,
                    block_type: block_type_name(block).to_string(),
                    snippet,
                });
            }
        }
        serde_wasm_bindgen::to_value(&hits).unwrap_or(JsValue::NULL)
    }

    #[wasm_bindgen(js_name = replace)]
    pub fn replace(&mut self, query: &str, replacement: &str) -> Result<usize, JsValue> {
        if query.is_empty() {
            return Ok(0);
        }
        let mut total = 0usize;
        for block in &self.editor.doc.blocks {
            total += count_in_block(block, query);
        }
        if total == 0 {
            return Ok(0);
        }
        self.editor.checkpoint();
        let mut replaced = 0usize;
        for block in &mut self.editor.doc.blocks {
            replaced += replace_in_block(block, query, replacement);
        }
        if replaced > 0 {
            self.editor.doc.touch();
        }
        Ok(replaced)
    }

    #[wasm_bindgen(js_name = checkpoint)]
    pub fn checkpoint(&mut self) {
        self.editor.checkpoint();
    }
}

#[derive(Serialize)]
struct FindHit {
    block_id: String,
    block_index: usize,
    start: usize,
    end: usize,
    block_type: String,
    snippet: String,
}

fn block_type_name(block: &Block) -> &'static str {
    match block {
        Block::Heading { .. } => "heading",
        Block::Paragraph { .. } => "paragraph",
        Block::List { .. } => "list",
        Block::Quote { .. } => "quote",
        Block::Code { .. } => "code",
        Block::Table { .. } => "table",
        Block::Figure { .. } => "figure",
    }
}

fn inline_plain_text(inlines: &[Inline], out: &mut String) {
    for inline in inlines {
        match inline {
            Inline::Text { value } => out.push_str(value.as_ref()),
            Inline::CodeSpan { value } => out.push_str(value.as_ref()),
            Inline::Link { text, .. } => inline_plain_text(text, out),
            Inline::Styled { content, .. } => inline_plain_text(content, out),
        }
    }
}

fn block_plain_text(block: &Block) -> String {
    let mut out = String::new();
    match block {
        Block::Heading { content, .. } | Block::Paragraph { content, .. } => {
            inline_plain_text(content, &mut out);
        }
        Block::List { items, .. } => {
            for (idx, item) in items.iter().enumerate() {
                if idx > 0 {
                    out.push('\n');
                }
                inline_plain_text(&item.content, &mut out);
            }
        }
        Block::Quote { content, .. } => {
            for (idx, inner) in content.iter().enumerate() {
                if idx > 0 {
                    out.push('\n');
                }
                out.push_str(&block_plain_text(inner));
            }
        }
        Block::Code { code, .. } => out.push_str(code.as_ref()),
        Block::Table { rows, .. } => {
            for (ri, row) in rows.iter().enumerate() {
                if ri > 0 {
                    out.push('\n');
                }
                for (ci, cell) in row.iter().enumerate() {
                    if ci > 0 {
                        out.push('\t');
                    }
                    inline_plain_text(&cell.content, &mut out);
                }
            }
        }
        Block::Figure { caption, .. } => {
            if let Some(c) = caption {
                out.push_str(c.as_ref());
            }
        }
    }
    out
}

fn char_to_byte_idx(s: &str, char_idx: usize) -> usize {
    if char_idx == 0 {
        return 0;
    }
    s.char_indices()
        .nth(char_idx)
        .map(|(i, _)| i)
        .unwrap_or_else(|| s.len())
}

fn build_snippet(text: &str, start: usize, end: usize) -> String {
    let total = text.chars().count();
    let ctx = 20usize;
    let s = start.saturating_sub(ctx);
    let e = (end + ctx).min(total);
    let s_b = char_to_byte_idx(text, s);
    let e_b = char_to_byte_idx(text, e);
    text[s_b..e_b].to_string()
}

fn count_in_text(text: &str, query: &str) -> usize {
    if query.is_empty() {
        return 0;
    }
    text.matches(query).count()
}

fn count_in_inlines(inlines: &[Inline], query: &str) -> usize {
    let mut count = 0;
    for inline in inlines {
        match inline {
            Inline::Text { value } => count += count_in_text(value.as_ref(), query),
            Inline::CodeSpan { value } => count += count_in_text(value.as_ref(), query),
            Inline::Link { text, .. } => count += count_in_inlines(text, query),
            Inline::Styled { content, .. } => count += count_in_inlines(content, query),
        }
    }
    count
}

fn count_in_block(block: &Block, query: &str) -> usize {
    match block {
        Block::Heading { content, .. } | Block::Paragraph { content, .. } => count_in_inlines(content, query),
        Block::List { items, .. } => items.iter().map(|i| count_in_inlines(&i.content, query)).sum(),
        Block::Quote { content, .. } => content.iter().map(|b| count_in_block(b, query)).sum(),
        Block::Code { code, .. } => count_in_text(code.as_ref(), query),
        Block::Table { rows, .. } => rows
            .iter()
            .map(|r| r.iter().map(|c| count_in_inlines(&c.content, query)).sum::<usize>())
            .sum(),
        Block::Figure { caption, .. } => caption
            .as_ref()
            .map(|c| count_in_text(c.as_ref(), query))
            .unwrap_or(0),
    }
}

fn replace_text(text: &str, query: &str, replacement: &str) -> (String, usize) {
    let count = count_in_text(text, query);
    if count == 0 {
        return (text.to_string(), 0);
    }
    (text.replace(query, replacement), count)
}

fn replace_in_inlines(inlines: &mut Vec<Inline>, query: &str, replacement: &str) -> usize {
    let mut count = 0;
    for inline in inlines.iter_mut() {
        match inline {
            Inline::Text { value } => {
                let (new_text, c) = replace_text(value.as_ref(), query, replacement);
                if c > 0 {
                    *value = Arc::from(new_text);
                    count += c;
                }
            }
            Inline::CodeSpan { value } => {
                let (new_text, c) = replace_text(value.as_ref(), query, replacement);
                if c > 0 {
                    *value = Arc::from(new_text);
                    count += c;
                }
            }
            Inline::Link { text, .. } => {
                count += replace_in_inlines(text, query, replacement);
            }
            Inline::Styled { content, .. } => {
                count += replace_in_inlines(content, query, replacement);
            }
        }
    }
    count
}

fn replace_in_block(block: &mut Block, query: &str, replacement: &str) -> usize {
    match block {
        Block::Heading { content, dirty, .. } | Block::Paragraph { content, dirty, .. } => {
            let count = replace_in_inlines(content, query, replacement);
            if count > 0 {
                *dirty = true;
            }
            count
        }
        Block::List { items, dirty, .. } => {
            let mut count = 0;
            for item in items.iter_mut() {
                count += replace_in_inlines(&mut item.content, query, replacement);
            }
            if count > 0 {
                *dirty = true;
            }
            count
        }
        Block::Quote { content, dirty, .. } => {
            let mut count = 0;
            for inner in content.iter_mut() {
                count += replace_in_block(inner, query, replacement);
            }
            if count > 0 {
                *dirty = true;
            }
            count
        }
        Block::Code { code, dirty, .. } => {
            let (new_text, count) = replace_text(code.as_ref(), query, replacement);
            if count > 0 {
                *code = Arc::from(new_text);
                *dirty = true;
            }
            count
        }
        Block::Table { rows, dirty, .. } => {
            let mut count = 0;
            for row in rows.iter_mut() {
                for cell in row.iter_mut() {
                    count += replace_in_inlines(&mut cell.content, query, replacement);
                }
            }
            if count > 0 {
                *dirty = true;
            }
            count
        }
        Block::Figure { caption, dirty, .. } => {
            let existing = caption.as_ref().map(|c| c.as_ref().to_string());
            if let Some(text) = existing {
                let (new_text, count) = replace_text(&text, query, replacement);
                if count > 0 {
                    *caption = Some(Arc::from(new_text));
                    *dirty = true;
                }
                count
            } else {
                0
            }
        }
    }
}

#[wasm_bindgen(start)]
pub fn main() {
    console_error_panic_hook::set_once();
}
