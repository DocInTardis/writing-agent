use wa_core::{Block, import_any, import_html_rich};
#[cfg(feature = "export_docx")]
use std::sync::Arc;
#[cfg(feature = "export_docx")]
use wa_core::{Document, Inline};
#[cfg(feature = "export_docx")]
use wa_core::export_pdf;

#[test]
fn import_plaintext_smoke() {
    let mut tmp = std::env::temp_dir();
    tmp.push("wa_import_test.txt");
    std::fs::write(&tmp, "第一段\n\n第二段").unwrap();
    let doc = import_any(&tmp).unwrap();
    assert!(doc.blocks.len() >= 1);
}

#[test]
fn import_html_rich_list_table() {
    let list_html = "<ul><li><b>一</b>号</li><li>二号</li></ul>";
    let doc = import_html_rich(list_html);
    assert!(doc.blocks.iter().any(|b| matches!(b, Block::List { .. })));

    let table_html = "<table><tr><td>甲</td><td><i>乙</i></td></tr></table>";
    let doc = import_html_rich(table_html);
    match doc.blocks.get(0) {
        Some(Block::Table { rows, .. }) => assert_eq!(rows.get(0).map(|r| r.len()), Some(2)),
        _ => panic!("expected table"),
    }
}

#[cfg(feature = "export_docx")]
#[test]
fn export_pdf_smoke() {
    let mut doc = Document::new();
    doc.blocks.push(Block::Paragraph {
        id: uuid::Uuid::new_v4(),
        content: vec![Inline::Text { value: Arc::from("PDF 导出测试") }],
        dirty: false,
    });
    let mut tmp = std::env::temp_dir();
    tmp.push("wa_export_test.pdf");
    match export_pdf(&doc, &tmp) {
        Ok(_) => {
            let size = std::fs::metadata(&tmp).unwrap().len();
            assert!(size > 0);
            let _ = std::fs::remove_file(&tmp);
        }
        Err(err) => {
            let msg = format!("{:?}", err);
            if msg.contains("font not found") {
                return;
            }
            panic!("pdf export failed: {:?}", err);
        }
    }
}
