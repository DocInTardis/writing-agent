use std::path::PathBuf;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: wa_import <input_path> <output_md>");
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
    let md = wa_core::export_markdown(&doc);
    if let Err(err) = std::fs::write(&output, md) {
        eprintln!("write failed: {:?}", err);
        std::process::exit(1);
    }
}
