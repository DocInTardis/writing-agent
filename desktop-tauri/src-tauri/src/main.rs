use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use serde::Serialize;
use tauri::State;
use wa_core::{Block, Document, Editor, EditorCommand, Inline, Style};
use wa_engine::{LayoutCache, LayoutConfig, LayoutEngine};

struct EditorState {
    editor: Editor,
    layout_engine: LayoutEngine,
    layout_cache: LayoutCache,
}

#[allow(dead_code)]
struct SidecarState {
    process: Mutex<Option<Child>>,
}

impl Drop for SidecarState {
    fn drop(&mut self) {
        if let Ok(process) = self.process.get_mut() {
            if let Some(child) = process.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

#[derive(Serialize)]
struct CursorPosition {
    block_id: String,
    offset: usize,
}

#[derive(Serialize)]
struct DocStats {
    char_count: usize,
    block_count: usize,
    reading_time: usize,
}

#[derive(Serialize)]
struct LayoutBlockInfo {
    id: String,
    height: f32,
    lines: usize,
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
        Block::Heading { content, .. } | Block::Paragraph { content, .. } => {
            count_in_inlines(content, query)
        }
        Block::List { items, .. } => items
            .iter()
            .map(|i| count_in_inlines(&i.content, query))
            .sum(),
        Block::Quote { content, .. } => content.iter().map(|b| count_in_block(b, query)).sum(),
        Block::Code { code, .. } => count_in_text(code.as_ref(), query),
        Block::Table { rows, .. } => rows
            .iter()
            .map(|r| {
                r.iter()
                    .map(|c| count_in_inlines(&c.content, query))
                    .sum::<usize>()
            })
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
                    *value = std::sync::Arc::from(new_text);
                    count += c;
                }
            }
            Inline::CodeSpan { value } => {
                let (new_text, c) = replace_text(value.as_ref(), query, replacement);
                if c > 0 {
                    *value = std::sync::Arc::from(new_text);
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
            let (new_text, code_count) = replace_text(code.as_ref(), query, replacement);
            if code_count > 0 {
                *code = std::sync::Arc::from(new_text);
                *dirty = true;
            }
            code_count
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
                    *caption = Some(std::sync::Arc::from(new_text));
                    *dirty = true;
                }
                count
            } else {
                0
            }
        }
    }
}

#[tauri::command]
fn load_json(state: State<Mutex<EditorState>>, json: &str) -> Result<(), String> {
    let doc: Document =
        serde_json::from_str(json).map_err(|e| format!("JSON parse error: {}", e))?;
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor = Editor::new(doc);
    Ok(())
}

#[tauri::command]
fn export_json(state: State<Mutex<EditorState>>) -> Result<String, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    serde_json::to_string(&guard.editor.doc).map_err(|e| e.to_string())
}

#[tauri::command]
fn insert_text(state: State<Mutex<EditorState>>, text: &str) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard
        .editor
        .execute(EditorCommand::InsertText(text.to_string()));
    Ok(())
}

#[tauri::command]
fn delete_backward(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::DeleteSelection);
    Ok(())
}

#[tauri::command]
fn toggle_bold(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    let mut style = Style::default();
    style.bold = true;
    guard.editor.execute(EditorCommand::ApplyStyle(style));
    Ok(())
}

#[tauri::command]
fn toggle_italic(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    let mut style = Style::default();
    style.italic = true;
    guard.editor.execute(EditorCommand::ApplyStyle(style));
    Ok(())
}

#[tauri::command]
fn toggle_underline(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    let mut style = Style::default();
    style.underline = true;
    guard.editor.execute(EditorCommand::ApplyStyle(style));
    Ok(())
}

#[tauri::command]
fn toggle_strikethrough(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    let mut style = Style::default();
    style.strikethrough = true;
    guard.editor.execute(EditorCommand::ApplyStyle(style));
    Ok(())
}

#[tauri::command]
fn set_heading(state: State<Mutex<EditorState>>, level: u8) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::SetHeading(level));
    Ok(())
}

#[tauri::command]
fn insert_list(state: State<Mutex<EditorState>>, ordered: bool) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::InsertList(ordered));
    Ok(())
}

#[tauri::command]
fn insert_table(state: State<Mutex<EditorState>>, rows: usize, cols: usize) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::InsertTable(rows, cols));
    Ok(())
}

#[tauri::command]
fn insert_code(state: State<Mutex<EditorState>>, lang: String, code: String) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard
        .editor
        .execute(EditorCommand::InsertCode { lang, code });
    Ok(())
}

#[tauri::command]
fn insert_image(state: State<Mutex<EditorState>>, url: String) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::InsertImage(url));
    Ok(())
}

#[tauri::command]
fn insert_figure(
    state: State<Mutex<EditorState>>,
    url: String,
    caption: Option<String>,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard
        .editor
        .execute(EditorCommand::InsertFigure { url, caption });
    Ok(())
}

#[tauri::command]
fn insert_quote(state: State<Mutex<EditorState>>, text: String) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::InsertQuote(text));
    Ok(())
}

#[tauri::command]
fn insert_link(state: State<Mutex<EditorState>>, url: String, text: String) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard
        .editor
        .execute(EditorCommand::InsertLink { url, text });
    Ok(())
}

#[tauri::command]
fn table_insert_row(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::TableInsertRow);
    Ok(())
}

#[tauri::command]
fn table_insert_column(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::TableInsertColumn);
    Ok(())
}

#[tauri::command]
fn table_delete_row(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::TableDeleteRow);
    Ok(())
}

#[tauri::command]
fn table_delete_column(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::TableDeleteColumn);
    Ok(())
}

#[tauri::command]
fn list_indent(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::ListIndent);
    Ok(())
}

#[tauri::command]
fn list_outdent(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::ListOutdent);
    Ok(())
}

#[tauri::command]
fn undo(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::Undo);
    Ok(())
}

#[tauri::command]
fn redo(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.execute(EditorCommand::Redo);
    Ok(())
}

#[tauri::command]
fn get_cursor_position(state: State<Mutex<EditorState>>) -> Result<CursorPosition, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    let pos = guard.editor.selection.focus;
    Ok(CursorPosition {
        block_id: pos.block_id.to_string(),
        offset: pos.offset,
    })
}

#[tauri::command]
fn get_stats(state: State<Mutex<EditorState>>) -> Result<DocStats, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    let char_count: usize = guard
        .editor
        .doc
        .blocks
        .iter()
        .map(|b| match b {
            Block::Paragraph { content, .. } | Block::Heading { content, .. } => content
                .iter()
                .map(|i| match i {
                    Inline::Text { value } => value.chars().count(),
                    Inline::CodeSpan { value } => value.chars().count(),
                    Inline::Link { text, .. } => text
                        .iter()
                        .map(|t| match t {
                            Inline::Text { value } => value.chars().count(),
                            _ => 0,
                        })
                        .sum(),
                    Inline::Styled { content, .. } => content
                        .iter()
                        .map(|t| match t {
                            Inline::Text { value } => value.chars().count(),
                            _ => 0,
                        })
                        .sum(),
                })
                .sum(),
            _ => 0,
        })
        .sum();

    Ok(DocStats {
        char_count,
        block_count: guard.editor.doc.blocks.len(),
        reading_time: (char_count as f64 / 400.0).ceil() as usize,
    })
}

#[tauri::command]
fn layout(state: State<Mutex<EditorState>>, width: f32) -> Result<Vec<LayoutBlockInfo>, String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    let config = LayoutConfig {
        page_width: width,
        ..Default::default()
    };

    let EditorState {
        editor,
        layout_engine,
        layout_cache,
    } = &mut *guard;
    let layout_tree = layout_engine.layout_cached(&editor.doc, &config, layout_cache);

    let mut blocks_info = Vec::new();
    for page in &layout_tree.pages {
        for block in &page.blocks {
            blocks_info.push(LayoutBlockInfo {
                id: block.block_id.to_string(),
                height: block.height,
                lines: block.lines.len(),
            });
        }
    }

    Ok(blocks_info)
}

#[tauri::command]
fn export_markdown(state: State<Mutex<EditorState>>) -> Result<String, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    Ok(wa_core::export_markdown(&guard.editor.doc))
}

#[tauri::command]
fn import_markdown(state: State<Mutex<EditorState>>, md: &str) -> Result<(), String> {
    let doc = wa_core::import_markdown(md);
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor = Editor::new(doc);
    Ok(())
}

#[tauri::command]
fn find(state: State<Mutex<EditorState>>, query: &str) -> Result<Vec<FindHit>, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    if query.is_empty() {
        return Ok(Vec::new());
    }
    let mut hits: Vec<FindHit> = Vec::new();
    let q_len = query.chars().count();
    for (block_index, block) in guard.editor.doc.blocks.iter().enumerate() {
        let text = block_plain_text(block);
        if text.is_empty() {
            continue;
        }
        for (byte_idx, _) in text.match_indices(query) {
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
    Ok(hits)
}

#[tauri::command]
fn replace(
    state: State<Mutex<EditorState>>,
    query: &str,
    replacement: &str,
) -> Result<usize, String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    if query.is_empty() {
        return Ok(0);
    }
    let mut total = 0usize;
    for block in &guard.editor.doc.blocks {
        total += count_in_block(block, query);
    }
    if total == 0 {
        return Ok(0);
    }
    guard.editor.checkpoint();
    let mut replaced = 0usize;
    for block in &mut guard.editor.doc.blocks {
        replaced += replace_in_block(block, query, replacement);
    }
    if replaced > 0 {
        guard.editor.doc.touch();
    }
    Ok(replaced)
}

#[tauri::command]
fn checkpoint(state: State<Mutex<EditorState>>) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;
    guard.editor.checkpoint();
    Ok(())
}

#[tauri::command]
fn ping() -> String {
    "pong".to_string()
}

fn project_root() -> Option<PathBuf> {
    if let Some(value) = std::env::var_os("WRITING_AGENT_PROJECT_ROOT") {
        return Some(PathBuf::from(value));
    }
    let cwd = std::env::current_dir().ok()?;
    if cwd.file_name().and_then(|name| name.to_str()) == Some("desktop-tauri") {
        return cwd.parent().map(Path::to_path_buf);
    }
    Some(cwd)
}

fn start_python_backend() -> Result<Child, String> {
    let root = project_root().ok_or_else(|| "could not resolve project root".to_string())?;
    let bundled = PathBuf::from("python-backend.exe");
    let configured = std::env::var_os("WRITING_AGENT_PYTHON_BACKEND").map(PathBuf::from);
    let windows_venv = root.join(".venv").join("Scripts").join("python.exe");
    let unix_venv = root.join(".venv").join("bin").join("python");

    let executable = configured
        .or_else(|| bundled.exists().then_some(bundled))
        .or_else(|| windows_venv.exists().then_some(windows_venv))
        .or_else(|| unix_venv.exists().then_some(unix_venv))
        .ok_or_else(|| {
            "Python backend not found; set WRITING_AGENT_PYTHON_BACKEND or create the project .venv"
                .to_string()
        })?;

    let is_bundled =
        executable.file_name().and_then(|name| name.to_str()) == Some("python-backend.exe");
    let mut command = Command::new(&executable);
    if !is_bundled {
        command
            .args(["-m", "writing_agent.launch"])
            .current_dir(&root);
    }
    command
        // The desktop shell does not consume child output; piping could block
        // the backend once the OS pipe buffer fills.
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| {
            format!(
                "failed to start Python backend with {}: {e}",
                executable.display()
            )
        })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let editor_state = Mutex::new(EditorState {
        editor: Editor::new(Document::new()),
        layout_engine: LayoutEngine::new(),
        layout_cache: LayoutCache::new(),
    });

    let sidecar = match start_python_backend() {
        Ok(child) => {
            println!("Python backend started with PID: {}", child.id());
            SidecarState {
                process: Mutex::new(Some(child)),
            }
        }
        Err(e) => {
            eprintln!("Warning: could not start Python backend sidecar: {}", e);
            SidecarState {
                process: Mutex::new(None),
            }
        }
    };

    tauri::Builder::default()
        .manage(editor_state)
        .manage(sidecar)
        .invoke_handler(tauri::generate_handler![
            load_json,
            export_json,
            insert_text,
            delete_backward,
            toggle_bold,
            toggle_italic,
            toggle_underline,
            toggle_strikethrough,
            set_heading,
            insert_list,
            insert_table,
            insert_code,
            insert_image,
            insert_figure,
            insert_quote,
            insert_link,
            table_insert_row,
            table_insert_column,
            table_delete_row,
            table_delete_column,
            list_indent,
            list_outdent,
            undo,
            redo,
            get_cursor_position,
            get_stats,
            layout,
            export_markdown,
            import_markdown,
            find,
            replace,
            checkpoint,
            ping,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn main() {
    run();
}
