# Rust + egui 鑷爺缂栬緫寮曟搸鎵ц璁″垝

## Phase 0锛氬伐绋嬪熀纭€璁炬柦

### 椤圭洰缁撴瀯
```
writing-agent-editor/
鈹溾攢鈹€ core/          # 鏂囨。妯″瀷 + AST
鈹溾攢鈹€ engine/        # 甯冨眬 + 娓叉煋寮曟搸
鈹溾攢鈹€ ui/            # egui 鐣岄潰
鈹溾攢鈹€ benches/       # 鎬ц兘鍩哄噯娴嬭瘯
鈹斺攢鈹€ tests/         # 闆嗘垚娴嬭瘯
```

### 鎬ц兘娴嬭瘯妗嗘灦
```toml
[dev-dependencies]
criterion = "0.5"
dhat = "0.3"
tracing-subscriber = "0.3"
```

### 鎬ц兘鎸囨爣鍩虹嚎
```rust
// benches/baseline.rs
#[bench] fn input_latency()      // 鐩爣: <8ms
#[bench] fn layout_10k_blocks()  // 鐩爣: <50ms
#[bench] fn render_frame()       // 鐩爣: <8.33ms (120fps)
#[bench] fn scroll_10k_lines()   // 鐩爣: 120fps绋冲畾
```

### CI/CD娴佹按绾?
```yaml
# .github/workflows/perf.yml
- 姣忔PR鑷姩杩愯benchmark
- 鎬ц兘鍥炲綊>5%鑷姩鎷掔粷
- 璺ㄥ钩鍙版瀯寤虹煩闃?Windows/macOS/Linux)
```

### 鍐呭瓨profiling闆嗘垚
```rust
#[global_allocator]
static ALLOC: dhat::Alloc = dhat::Alloc;

// 鐩爣: 10000瀛?20MB, 闆舵硠婕?
```

---

## Phase 1锛氭枃妗ｆā鍨?+ 搴忓垪鍖?

### AST缁撴瀯璁捐
```rust
struct Document {
    id: Uuid,           // 鏂囨。鍞竴鏍囪瘑
    version: u64,       // 鐗堟湰鍙凤紙鍗忎綔鍩虹锛?
    blocks: Vec<Block>,
    metadata: Metadata,
}

enum Block {
    Heading { id: Uuid, level: u8, content: Vec<Inline>, dirty: bool },
    Paragraph { id: Uuid, content: Vec<Inline>, dirty: bool },
    List { id: Uuid, ordered: bool, items: Vec<ListItem>, dirty: bool },
    Quote { id: Uuid, content: Vec<Block>, dirty: bool },
    Code { id: Uuid, lang: String, code: String, dirty: bool },
    Table { id: Uuid, rows: Vec<Vec<Cell>>, dirty: bool },
    Figure { id: Uuid, url: String, caption: Option<String>, dirty: bool },
}

enum Inline {
    Text(String),              // Arc闆舵嫹璐?
    Styled { style: Style, content: Vec<Inline> },
    Link { url: String, text: Vec<Inline> },
    CodeSpan(String),
}
```

### 澧為噺Diff鏈哄埗
```rust
struct DiffEngine {
    cache: HashMap<Uuid, u64>,  // id -> version缂撳瓨
}

impl DiffEngine {
    // 浠卍iff dirty鍧楋紙鎬ц兘鎻愬崌90%锛?
    fn incremental_diff(&self, doc: &Document) -> Vec<Patch> {
        doc.blocks.iter()
            .filter(|b| b.is_dirty())
            .map(|b| self.diff_block(b))
            .collect()
    }
}
```

### 搴忓垪鍖栨€ц兘
```rust
// JSON瀛樺偍
use serde_json;

// 鐩爣:
// - 10000鍧楀簭鍒楀寲<20ms
// - 鍙嶅簭鍒楀寲<30ms
// - 闆舵嫹璐漇tring澶嶇敤Arc<str>
```

### 鎬ц兘楠岃瘉
```rust
#[bench]
fn diff_10k_blocks_1_changed(b: &mut Bencher) {
    // 鐩爣: <5ms锛堜粎diff鍙樺寲鍧楋級
}

#[bench]
fn serialize_10k_blocks(b: &mut Bencher) {
    // 鐩爣: <20ms
}
```

---

## Phase 2锛氬竷灞€寮曟搸锛堝叧閿矾寰勶級

### 瀛椾綋绠＄悊POC锛堝墠缃獙璇侊級
```rust
// 閫夊瀷娴嬭瘯: fontdue vs rusttype
#[bench] fn shape_1000_chars_fontdue();   // 鐩爣: <2ms
#[bench] fn shape_1000_chars_rusttype();  // 瀵规瘮鍩哄噯

// 蹇呴€塮ontdue锛堝揩3鍊嶏級
use fontdue::{Font, FontSettings};

struct FontCache {
    fonts: LruCache<FontKey, Font>,
    glyph_cache: LruCache<(char, f32), GlyphMetrics>,
}

// 鐩爣: 缂撳瓨鍛戒腑鐜?95%
```

### 琛岀洅鎷嗗垎寮曟搸
```rust
use unicode_segmentation::UnicodeSegmentation;
use unicode_linebreak::{linebreaks, BreakOpportunity};

struct LineBreaker {
    // UAX #14鏍囧噯瀹炵幇
    fn break_text(&self, text: &str, width: f32) -> Vec<Line> {
        // 澶勭悊:
        // - CJK绂佸垯锛堣棣栬灏炬爣鐐癸級
        // - 鑻辨枃杩炲瓧绗︽柇璇?
        // - emoji涓嶅彲鎷嗗垎
    }
}

// 鎬ц兘鐩爣: 1000瀛?1ms
```

### 甯冨眬绠楁硶
```rust
struct LayoutEngine {
    font_cache: FontCache,
    line_breaker: LineBreaker,
}

impl LayoutEngine {
    fn layout_block(&mut self, block: &Block, width: f32) -> LayoutBox {
        match block {
            Block::Paragraph { content, .. } => {
                // 1. 鍐呰仈鎺掔増锛坆old/italic/link锛?
                // 2. 琛岀洅鎷嗗垎
                // 3. 瀵归綈璁＄畻
            }
            Block::Table { rows, .. } => {
                // 缃戞牸甯冨眬绠楁硶
                self.layout_table(rows, width)
            }
            // ...
        }
    }
}
```

### 澧為噺甯冨眬缂撳瓨
```rust
struct LayoutCache {
    cache: HashMap<Uuid, Arc<LayoutBox>>,  // 缂撳瓨宸茶绠楀竷灞€
}

// 浠呴噸绠梔irty鍧楋紙鎬ц兘鎻愬崌80%锛?
fn incremental_layout(&mut self, doc: &Document) -> LayoutTree {
    doc.blocks.iter().map(|block| {
        if block.is_dirty() {
            let layout = self.engine.layout_block(block);
            self.cache.insert(block.id(), Arc::new(layout));
            layout
        } else {
            self.cache.get(&block.id()).cloned().unwrap()
        }
    }).collect()
}
```

### 鎬ц兘楠岃瘉
```rust
#[bench]
fn layout_paragraph_1000_chars(b: &mut Bencher) {
    // 鐩爣: <3ms
}

#[bench]
fn layout_table_10x10(b: &mut Bencher) {
    // 鐩爣: <5ms
}

#[bench]
fn incremental_layout_1_changed(b: &mut Bencher) {
    // 鐩爣: <1ms锛堝懡涓紦瀛橈級
}
```

---

## Phase 3锛氭覆鏌撳眰

### 鑴忕煩褰紭鍖?
```rust
struct RenderCache {
    last_frame: Option<egui::TextureHandle>,
    dirty_rects: Vec<Rect>,  // 鍙樺寲鍖哄煙
}

impl RenderCache {
    fn render(&mut self, ctx: &egui::Context, layout: &LayoutTree) {
        // 1. 璁＄畻鑴忕煩褰紙鍙樺寲鐨勫潡锛?
        let dirty = self.compute_dirty_rects(layout);
        
        // 2. 浠呴噸缁樿剰鍖哄煙
        if dirty.len() < layout.blocks.len() * 0.1 {
            self.render_dirty_only(ctx, &dirty);  // <10%鍙樺寲
        } else {
            self.render_full(ctx, layout);        // 鍏ㄩ噺閲嶇粯
        }
    }
}

// 鐩爣: 95%鎯呭喌浠呴噸缁?5%灞忓箷
```

### 鍒嗛〉娓叉煋
```rust
struct PageRenderer {
    page_size: PageSize,  // A4/Letter
}

impl PageRenderer {
    fn render_page(&self, painter: &Painter, page: &Page) {
        // 1. 缁樺埗椤甸潰鑳屾櫙+闃村奖
        // 2. 缁樺埗椤佃竟璺濈嚎
        // 3. 缁樺埗鍐呭鍧?
    }
}
```

### 鏃犻檺婊氬姩娓叉煋
```rust
struct ScrollRenderer {
    visible_range: Range<usize>,  // 鍙鍧楄寖鍥?
}

// 浠呮覆鏌撳彲瑙?缂撳啿鍖猴紙铏氭嫙婊氬姩锛?
fn render_visible(&self, painter: &Painter, blocks: &[LayoutBox]) {
    let buffer = 5;  // 涓婁笅鍚?涓潡缂撳啿
    let start = self.visible_range.start.saturating_sub(buffer);
    let end = (self.visible_range.end + buffer).min(blocks.len());
    
    for block in &blocks[start..end] {
        self.render_block(painter, block);
    }
}
```

### 鎬ц兘楠岃瘉
```rust
#[bench]
fn render_page_100_blocks(b: &mut Bencher) {
    // 鐩爣: <8.33ms (120fps)
}

#[bench]
fn render_dirty_rect_only(b: &mut Bencher) {
    // 鐩爣: <2ms锛堜粎閲嶇粯鍙樺寲锛?
}
```

---

## Phase 4锛氱紪杈戜氦浜?

### 鍏夋爣涓庨€夊尯
```rust
struct Selection {
    anchor: Position,  // 璧风偣
    focus: Position,   // 缁堢偣锛堝厜鏍囦綅缃級
}

struct Position {
    block_id: Uuid,
    offset: usize,  // 瀛楃鍋忕Щ
}

// 鎬ц兘: 鍏夋爣绉诲姩鍝嶅簲<1ms
```

### 杈撳叆娉曢泦鎴愶紙璺ㄥ钩鍙帮級
```rust
use winit::event::Ime;

struct ImeHandler {
    composition: Option<String>,  // 鏈‘璁ゆ枃鏈?
    cursor_pos: usize,
}

// 蹇呴』娴嬭瘯骞冲彴:
// - Windows: 鎼滅嫍/寰蒋鎷奸煶
// - macOS: 绯荤粺鎷奸煶
// - Linux: ibus/fcitx
```

### 瀵屾枃鏈懡浠?
```rust
enum EditorCommand {
    InsertText(String),
    DeleteSelection,
    ApplyStyle(Style),      // bold/italic/underline
    SetHeading(u8),
    InsertList(bool),       // ordered
    InsertTable(usize, usize),
    InsertImage(String),
    Undo,
    Redo,
}

impl Editor {
    fn execute(&mut self, cmd: EditorCommand) {
        // 1. 搴旂敤鍛戒护鍒癆ST
        // 2. 鏍囪affected鍧椾负dirty
        // 3. 鎺ㄩ€佸埌undo鏍?
        // 4. 澧為噺甯冨眬+娓叉煋
    }
}
```

### Undo/Redo鏍?
```rust
struct CommandHistory {
    undo_stack: VecDeque<Command>,  // 闄愬埗100姝?
    redo_stack: VecDeque<Command>,
    checkpoints: Vec<(usize, Arc<Document>)>,  // 姣?0姝ュ揩鐓?
}

// 鎬ц兘: 1000娆℃挙閿€<100MB鍐呭瓨
```

### 澶嶅埗绮樿创
```rust
use arboard::Clipboard;

struct ClipboardHandler {
    fn copy_selection(&self, sel: &Selection) -> ClipboardData {
        ClipboardData {
            html: self.to_html(sel),      // 瀵屾枃鏈?
            plain: self.to_plain(sel),    // 绾枃鏈?
        }
    }
    
    fn paste(&mut self, data: ClipboardData) {
        // 浼樺厛HTML锛堜繚鐣欐牸寮忥級
        if let Some(html) = data.html {
            self.insert_html(html);
        } else {
            self.insert_text(data.plain);
        }
    }
}
```

### 鎬ц兘楠岃瘉
```rust
#[bench]
fn input_single_char(b: &mut Bencher) {
    // 鐩爣: <8ms锛堝惈甯冨眬+娓叉煋锛?
}

#[bench]
fn undo_100_operations(b: &mut Bencher) {
    // 鐩爣: <50ms
}

#[bench]
fn paste_1000_chars(b: &mut Bencher) {
    // 鐩爣: <20ms
}
```

---

## Phase 5锛氱粨鏋勫寲鍐呭缂栬緫

### 鍥剧墖绠＄悊
```rust
struct ImageManager {
    cache: LruCache<String, egui::TextureHandle>,
}

// 鍔熻兘:
// - 鏈湴鍥剧墖鍔犺浇
// - URL鍥剧墖寮傛涓嬭浇
// - 鎷栨嫿璋冩暣澶у皬
// - 鑷€傚簲姣斾緥
```

### 琛ㄦ牸缂栬緫
```rust
struct TableEditor {
    fn insert_row(&mut self, table_id: Uuid, index: usize);
    fn delete_row(&mut self, table_id: Uuid, index: usize);
    fn insert_column(&mut self, table_id: Uuid, index: usize);
    fn delete_column(&mut self, table_id: Uuid, index: usize);
    fn merge_cells(&mut self, range: CellRange);
}
```

### 鍒楄〃涓庡紩鐢?
```rust
// Tab缂╄繘
// Shift+Tab鍙嶇缉杩?
// Enter鑷姩缁」
// Backspace鍒犻櫎鏍囪
```

### 浠ｇ爜鍧?
```rust
use syntect::{highlighting, parsing};

struct CodeBlockRenderer {
    highlighter: highlighting::Highlighter,
    
    fn render(&self, code: &str, lang: &str) -> Vec<StyledText> {
        // 璇硶楂樹寒
    }
}
```

---

## Phase 6锛氬鍏ュ鍑?

### 瀵煎嚭DOCX
```rust
// 澶嶇敤鐜版湁python-docx閫昏緫
use pyo3::prelude::*;

fn export_docx(doc: &Document) -> Result<Vec<u8>> {
    Python::with_gil(|py| {
        let docx = py.import("docx")?;
        // 璋冪敤鐜版湁瀵煎嚭浠ｇ爜
    })
}
```

### 瀵煎叆Markdown
```rust
use pulldown_cmark::{Parser, Event};

fn import_markdown(md: &str) -> Document {
    let parser = Parser::new(md);
    let mut builder = DocumentBuilder::new();
    
    for event in parser {
        match event {
            Event::Start(Tag::Heading(level)) => { /* ... */ }
            Event::Text(text) => { /* ... */ }
            // ...
        }
    }
    
    builder.build()
}
```

---

## 鎬ц兘鎸囨爣鎬昏

```
鎿嶄綔              鐩爣      楠岃瘉鏂规硶
鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
鎵撳瓧寤惰繜          <8ms      benches/input.rs
甯冨眬10k鍧?        <50ms     benches/layout.rs
娓叉煋鍗曞抚          <8.33ms   benches/render.rs
婊氬姩10k琛?        120fps    benches/scroll.rs
鎾ら攢100娆?        <50ms     benches/undo.rs
瀵煎嚭1000瀛梔ocx    <100ms    benches/export.rs
鍐呭瓨鍗犵敤(10k瀛?   <20MB     tests/memory.rs
鍚姩鏃堕棿          <200ms    tests/startup.rs
```

---

## 閲岀▼纰?

### M1锛氬熀纭€娓叉煋
- AST + 搴忓垪鍖?
- 甯冨眬寮曟搸锛堟钀?鏍囬/鍒楄〃锛?
- 鍙屾ā寮忔覆鏌擄紙鍒嗛〉/婊氬姩锛?
- 鎬ц兘杈炬爣锛氬竷灞€<50ms锛屾覆鏌?20fps

### M2锛氬熀纭€缂栬緫
- 鍏夋爣+閫夊尯
- 鏂囨湰杈撳叆锛堝惈IME锛?
- 瀵屾枃鏈揩鎹烽敭
- 鎾ら攢/閲嶅仛
- 鎬ц兘杈炬爣锛氭墦瀛?8ms

### M3锛氬畬鏁村姛鑳?
- 鍥剧墖/琛ㄦ牸缂栬緫
- 澶嶅埗绮樿创锛堝瘜鏂囨湰锛?
- 浠ｇ爜鍧楄娉曢珮浜?
- 鎬ц兘杈炬爣锛氭墍鏈夋搷浣?16ms

### M4锛氱敓浜у氨缁?
- 瀵煎嚭DOCX涓庣幇鏈夌郴缁熶竴鑷?
- 璺ㄥ钩鍙扮ǔ瀹氭€ч獙璇?
- 鍐呭瓨鏃犳硠婕忥紙valgrind楠岃瘉锛?
- 鎬ц兘鍥炲綊娴嬭瘯閫氳繃

---

## 椋庨櫓鎺у埗

### 瀛椾綋娓叉煋鎬ц兘椋庨櫓
**瀵圭瓥**锛歅hase 0绔嬪嵆POC fontdue vs rusttype锛岀‘璁?鍊嶆€ц兘宸窛

### 杈撳叆娉曡法骞冲彴椋庨櫓
**瀵圭瓥**锛歅hase 4鍓嶇疆娴嬭瘯Windows/macOS/Linux涓夊钩鍙癐ME

### 澶ф枃妗ｆ€ц兘椋庨櫓
**瀵圭瓥**锛氭瘡涓狿hase鎸佺画娴嬭瘯10k/100k鍧楁枃妗ｆ€ц兘

### 鍐呭瓨娉勬紡椋庨櫓
**瀵圭瓥**锛氭瘡鍛ㄨ繍琛寁algrind锛孋I鑷姩妫€娴婻c寰幆寮曠敤

---

## CI娴佹按绾块厤缃?

```yaml
name: Performance CI

on: [pull_request]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: cargo bench
      - run: |
          # 鎬ц兘鍥炲綊>5%鎷掔粷PR
          python scripts/check_regression.py
  
  memory:
    runs-on: ubuntu-latest
    steps:
      - run: cargo build --release
      - run: valgrind --leak-check=full ./target/release/editor
      - run: |
          # 浠讳綍娉勬紡=澶辫触
          grep "definitely lost: 0 bytes" valgrind.log
  
  cross-platform:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - run: cargo test --release
```

---

## 浜や粯娓呭崟

- [ ] Rust宸ョ▼+CI/CD
- [ ] 鎬ц兘娴嬭瘯濂椾欢锛坈riterion锛?
- [ ] 鍐呭瓨profiling闆嗘垚锛坉hat锛?
- [ ] AST + 澧為噺Diff
- [ ] 甯冨眬寮曟搸锛堝惈缂撳瓨锛?
- [ ] 娓叉煋灞傦紙鑴忕煩褰紭鍖栵級
- [ ] 缂栬緫鍣紙鍏夋爣/杈撳叆/IME锛?
- [ ] 瀵屾枃鏈懡浠わ紙Undo/Redo锛?
- [ ] 鍥剧墖/琛ㄦ牸缂栬緫
- [ ] 瀵煎叆瀵煎嚭锛圡arkdown/DOCX锛?
- [ ] 璺ㄥ钩鍙伴獙璇佹姤鍛?
- [ ] 鎬ц兘杈炬爣鎶ュ憡
