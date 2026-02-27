use wa_core::{export_markdown, export_json, import_json, import_markdown, sanitize_doc, Block, Inline, TableEditor};
use std::sync::Arc;

#[test]
fn markdown_roundtrip_basic() {
    let md = "# 标题\n\n- 项目一\n- 项目二\n\n> 引用\n\n```rs\nfn main() {}\n```\n";
    let doc = import_markdown(md);
    let out = export_markdown(&doc);
    assert!(out.contains("# 标题"));
    assert!(out.contains("- 项目一"));
    assert!(out.contains("> 引用"));
    assert!(out.contains("```rs"));
}

#[test]
fn json_roundtrip_basic() {
    let md = "# 标题\n\n段落";
    let doc = import_markdown(md);
    let json = export_json(&doc).unwrap();
    let doc2 = import_json(&json).unwrap();
    let clean = sanitize_doc(doc2);
    assert!(!clean.blocks.is_empty());
}

#[test]
fn table_editor_ops() {
    let mut block = Block::Table {
        id: uuid::Uuid::new_v4(),
        rows: vec![vec![wa_core::Cell { content: vec![Inline::Text { value: Arc::from("a") }] }]],
        dirty: false,
    };
    assert!(TableEditor::insert_row(&mut block, 1));
    assert!(TableEditor::insert_column(&mut block, 1));
    assert!(TableEditor::set_cell_text(&mut block, 0, 0, "b".into()));
    assert!(TableEditor::delete_row(&mut block, 0));
    assert!(TableEditor::delete_column(&mut block, 0));
}
