#[cfg(feature = "export_docx")]
use std::path::PathBuf;

#[cfg(feature = "export_docx")]
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: wa_export <input_path> <output_docx>");
        std::process::exit(2);
    }
    let input = PathBuf::from(&args[1]);
    let output = PathBuf::from(&args[2]);
    let doc = match wa_core::import_any(&input) {
        Ok(doc) => doc,
        Err(err) => {
            eprintln!("import failed: {:?}", err);
            std::process::exit(1);
        }
    };
    if let Err(err) = wa_core::export_docx(&doc, &output) {
        eprintln!("export failed: {:?}", err);
        std::process::exit(1);
    }
}

#[cfg(not(feature = "export_docx"))]
fn main() {
    eprintln!("wa_export requires the `export_docx` feature");
    std::process::exit(1);
}
