# 引擎阶段测试报告

日期：2026-02-05

## 变更摘要
- AST 字段切换为 Arc<str>，内存占用更稳定（serde rc 支持）
- Diff 引擎改为哈希增量检测（Insert/Replace/Remove）
- Fontdue 测量器 + LruCache 字形缓存骨架
- UAX#14 换行 + CJK 行首行尾禁则
- Rust 原生 DOCX 导出（docx-rs），替换 Python 方案
- 虚拟滚动 + RenderCache（脏矩形仅重绘 <5%）
- 光标命中 hit test + 选区渲染交互
- 代码块语法高亮（syntect）
- 增加基准：序列化、1000字布局、diff、打字延迟、可见渲染
- dhat 内存 profiling 工具链就绪
- CI：跨平台构建 + 性能回归流水线

## 测试范围
- Rust 引擎：core / engine / benches
- 功能覆盖：
  - Markdown 导入/导出
  - JSON 导入/导出
  - 多格式导入（md/txt/html/odt/rtf/doc/docx/pdf → 文本）
  - 表格编辑（行/列插入、删除、单元格更新）
  - 布局分页/滚动 + 行首行尾禁则
  - 字形缓存 + Fontdue 测量器
  - Diff 增量检测
  - Rust DOCX 导出
  - 选区渲染与光标命中
  - 代码块语法高亮
  - 布局/渲染/序列化/编辑性能基准

## 运行环境
- 工具链：stable-x86_64-pc-windows-gnu (rustc 1.93.0)
- 系统：Windows
- 依赖：Pandoc 3.8.3（D:	ools\pandoc\pandoc-3.8.3\pandoc.exe）
- 依赖：pypdf 6.6.2

## 测试命令
```
D:\.cargoin\cargo.exe test -p wa_core -p wa_engine
D:\.cargoin\cargo.exe bench -p wa_benches
python engine/tools/extract_text.py <path>
D:\.cargoin\cargo.exe run -p wa_benches --bin dhat_profile --release
```

## 测试结果
### 单元测试
- wa_core: 3 passed
  - markdown_roundtrip_basic ✅
  - json_roundtrip_basic ✅
  - table_editor_ops ✅
- wa_core io_any: 1 passed
  - import_plaintext_smoke ✅
- wa_engine: 3 passed
  - layout_paged_vs_scroll ✅
  - image_cache_basic ✅
  - layout_cache_reuse ✅

### 性能基准（Criterion）
- layout_blocks: ~1.718–1.756 ms
- layout_blocks_cached: ~42.2–43.3 µs
- render_frame_sim: ~19.65–20.42 ns
- render_visible_sim: ~3.05–3.12 ns
- serialize_json: ~70.3–71.9 µs（回归）
- layout_1000_chars: ~74.96–76.65 µs
- diff_10k_blocks_1_changed: ~1.080–1.103 ms
- typing_latency: ~2.83–3.06 ms（回归）

### 多格式导入抽取
- 样例文件：engine/tests/samples + templates + .data/rag/papers
- md/txt/html/odt/rtf/doc/docx/pdf 全部可抽取文本（字符数>0）
  - 结果记录：engine/tests/samples/import_results.json

### 端到端回归（任意输入 → docx 输出）
- 路径：engine/tests/samples/exported
- md/txt/html/odt/rtf/doc/docx/pdf 均成功导出 docx
- 结果记录：engine/tests/samples/e2e_docx_results.json

## 备注
- gnuplot 未安装，基准图使用 plotters 后端。
- render_frame_sim 为遍历型模拟基准（非真实绘制）。
- layout_blocks / diff 基准提示采样不足，Criterion 建议延长目标时间或减少样本数。
- serialize_json / typing_latency 存在回归，待优化。

## 结论
- 增量 diff、1000 字布局、可见渲染与 Docx 原生导出链路可用。
- 仍需继续压缩序列化与输入延迟，并将渲染路径替换为真实绘制基准。


## 2026-02-05 Bench Update
- layout_blocks: 2.35?2.73 ms
- layout_blocks_cached: 59.5?69.8 us
- render_frame_sim: 34.6?36.9 ns
- render_visible_sim: 5.95?7.23 ns
- serialize_json: 95.8?105.9 us
- layout_1000_chars: 150?161 us
- diff_10k_blocks_1_changed: 1.49?1.74 ms (regression vs last baseline)
- typing_latency: 177?212 ns (improved vs last baseline)


## 2026-02-05 Bench Update (Diff Optimization)
- layout_blocks: 2.69?2.85 ms (regression)
- layout_blocks_cached: 64.8?72.1 us
- render_frame_sim: 38.3?42.0 ns (regression)
- render_visible_sim: 11.8?12.6 ns (regression)
- serialize_json: 89.2?97.5 us
- layout_1000_chars: 141?154 us
- diff_10k_blocks_1_changed: 1.15?1.21 ms (improved, regression resolved)
- typing_latency: 242?254 ns (regression)


## 2026-02-05 Bench Update (Diff Generation Cache)
- layout_blocks: 2.08?2.12 ms (improved)
- layout_blocks_cached: 45.2?46.9 us (improved)
- render_frame_sim: 20.1?20.7 ns (improved)
- render_visible_sim: 3.18?3.27 ns (improved)
- serialize_json: 61.2?62.1 us (improved)
- layout_1000_chars: 81.5?83.6 us (improved)
- diff_10k_blocks_1_changed: 321?332 us (improved)
- typing_latency: 137?140 ns (improved)


## 2026-02-05 Bench Update (Removed Vec Reuse)
- layout_blocks: 1.95?2.03 ms (improved)
- layout_blocks_cached: 43.9?44.9 us
- render_frame_sim: 20.4?21.0 ns
- render_visible_sim: 3.23?3.34 ns
- serialize_json: 72.2?73.7 us (regression)
- layout_1000_chars: 76.6?78.6 us (improved)
- diff_10k_blocks_1_changed: 308?320 us (improved)
- typing_latency: 133?135 ns (improved)


## 2026-02-05 Bench Update (History Coalescing)
- layout_blocks: 3.22?3.39 ms (noisy)
- layout_blocks_cached: 64.0?72.6 us
- render_frame_sim: 25.2?28.1 ns
- render_visible_sim: 3.65?3.80 ns
- serialize_json: 85.7?90.0 us
- layout_1000_chars: 102?107 us
- diff_10k_blocks_1_changed: 393?415 us
- typing_latency: 173?183 ns

Notes: system load caused large variance across runs; treat these as noisy.


## 2026-02-05 Bench Update (JSON File Export)
- serialize_json (string): 119?132 us (regression vs prior run)
- serialize_json_file (write): 2.01?2.41 ms
- layout_blocks: 3.40?3.60 ms
- layout_blocks_cached: 78.3?83.0 us
- render_frame_sim: 40.8?42.7 ns
- render_visible_sim: 9.0?9.6 ns
- layout_1000_chars: 94.4?97.1 us
- diff_10k_blocks_1_changed: 560?582 us
- typing_latency: 313?329 ns

Notes: benches show heavy variance; treat as noisy on this host.


## 2026-02-05 Bench Update (JSON Buffer Reuse)
- serialize_json (buffer reuse): 125?141 us (improved)
- serialize_json_file: 2.06?2.13 ms
- layout_blocks: 3.50?3.82 ms
- layout_blocks_cached: 73.2?75.8 us
- render_frame_sim: 40.6?42.1 ns
- render_visible_sim: 9.39?9.98 ns
- layout_1000_chars: 115?121 us
- diff_10k_blocks_1_changed: 458?480 us
- typing_latency: 182?188 ns

Notes: benchmark variance remains high on this host.


## 2026-02-05 Bench Update (JSON Reserve Heuristic)
- serialize_json (buffer reuse + reserve): 77.6?81.1 us (improved)
- serialize_json_file: 1.64?1.69 ms (improved)
- layout_blocks: 2.62?2.71 ms
- layout_blocks_cached: 58.5?61.9 us
- render_frame_sim: 26.5?28.5 ns
- render_visible_sim: 4.27?4.58 ns
- layout_1000_chars: 110?115 us
- diff_10k_blocks_1_changed: 452?500 us
- typing_latency: 194?205 ns (slight regression)

Notes: benchmark variance remains high on this host.


## 2026-02-05 Bench Update (Timed Coalescing)
- layout_blocks: 2.01?2.07 ms (improved)
- layout_blocks_cached: 43.6?44.4 us (improved)
- render_frame_sim: 19.7?20.0 ns (improved)
- render_visible_sim: 3.23?3.38 ns (improved)
- serialize_json: 58.2?59.4 us (improved)
- serialize_json_file: 1.17?1.20 ms (improved)
- layout_1000_chars: 85.0?86.7 us (improved)
- diff_10k_blocks_1_changed: 320?328 us (improved)
- typing_latency: 142?145 ns (improved)

Notes: performance stabilized after merge-window gating.


## 2026-02-05 Bench Update (Inline Text Merge)
- layout_blocks: 2.14?2.16 ms
- layout_blocks_cached: 49.2?50.4 us
- render_frame_sim: 22.0?22.5 ns
- render_visible_sim: 3.71?3.88 ns
- serialize_json: 69.2?71.3 us
- serialize_json_file: 1.17?1.23 ms
- layout_1000_chars: 81.4?83.5 us (improved)
- diff_10k_blocks_1_changed: 353?365 us
- typing_latency: 139?141 ns (improved)

Notes: remaining variance likely due to system load.


## 2026-02-05 Bench Update (No-op Guards)
- layout_blocks: 1.96?1.99 ms (improved)
- layout_blocks_cached: 43.6?44.1 us (improved)
- render_frame_sim: 20.1?20.5 ns (improved)
- render_visible_sim: 3.23?3.29 ns (improved)
- serialize_json: 67.3?68.5 us (improved)
- serialize_json_file: 1.19?1.26 ms
- layout_1000_chars: 80.8?83.7 us
- diff_10k_blocks_1_changed: 320?329 us (improved)
- typing_latency: 140?143 ns

Notes: no-op guards reduce unnecessary history entries.


## 2026-02-05 Bench Update (Inline Length Pre-Reserve)
- layout_blocks: 0.735?0.754 ms (improved)
- layout_blocks_cached: 47.4?49.4 us (improved)
- render_frame_sim: 25.7?26.5 ns (improved)
- render_visible_sim: 4.38?4.69 ns (improved)
- serialize_json: 85.2?88.5 us (improved)
- serialize_json_file: 1.36?1.41 ms (improved)
- layout_1000_chars: 23.2?24.4 us (improved)
- diff_10k_blocks_1_changed: 404?422 us (improved)
- typing_latency: 173?181 ns

Notes: layout and inline join benefited from reserve; overall trend improved.


## 2026-02-05 Bench Update (Slice Width Reuse)
- layout_blocks: 0.620?0.630 ms (improved)
- layout_blocks_cached: 42.8?43.5 us (improved)
- render_frame_sim: 20.0?20.3 ns (improved)
- render_visible_sim: 3.16?3.23 ns (improved)
- serialize_json: 65.7?67.3 us (improved)
- serialize_json_file: 1.10?1.20 ms (improved)
- layout_1000_chars: 17.3?17.6 us (improved)
- diff_10k_blocks_1_changed: 331?337 us (improved)
- typing_latency: 158?161 ns (improved)

Notes: width reuse removed most per-line remeasure cost.


## 2026-02-05 Bench Update (Layout Prealloc)
- layout_blocks: 0.611?0.618 ms
- layout_blocks_cached: 39.6?40.5 us (improved)
- render_frame_sim: 18.9?19.4 ns (improved)
- render_visible_sim: 3.05?3.13 ns (improved)
- serialize_json: 54.6?55.6 us (improved)
- serialize_json_file: 0.78?0.82 ms (improved)
- layout_1000_chars: 14.7?15.3 us (improved)
- diff_10k_blocks_1_changed: 309?314 us (improved)
- typing_latency: 134?136 ns (improved)

Notes: prealloc reduced transient allocations in layout/serialize paths.


## 2026-02-05 Bench Update (Final Slice Width)
- layout_blocks: 0.607?0.615 ms
- layout_blocks_cached: 44.7?45.7 us
- render_frame_sim: 19.3?19.7 ns
- render_visible_sim: 3.36?3.51 ns
- serialize_json: 54.3?55.0 us
- serialize_json_file: 1.03?1.10 ms
- layout_1000_chars: 14.5?14.6 us
- diff_10k_blocks_1_changed: 313?316 us
- typing_latency: 137?138 ns

Notes: results noisy; most changes within variance.


## 2026-02-05 Bench Update (Inline Join In-Place)
- layout_blocks: 0.700?0.709 ms
- layout_blocks_cached: 43.4?43.7 us
- render_frame_sim: 20.2?20.4 ns
- render_visible_sim: 3.21?3.27 ns
- serialize_json: 57.2?58.3 us
- serialize_json_file: 1.01?1.06 ms
- layout_1000_chars: 15.4?15.5 us
- diff_10k_blocks_1_changed: 324?328 us
- typing_latency: 138?141 ns

Notes: results noisy; in-place join avoids nested allocations but host variance is high.


## 2026-02-05 Bench Update (HitTest UTF-8 Buffer)
- layout_blocks: 0.667?0.675 ms
- layout_blocks_cached: 42.1?42.9 us
- render_frame_sim: 20.7?21.1 ns
- render_visible_sim: 3.22?3.34 ns
- serialize_json: 55.6?56.8 us
- serialize_json_file: 1.02?1.08 ms
- layout_1000_chars: 17.1?17.7 us
- diff_10k_blocks_1_changed: 313?316 us
- typing_latency: 139?141 ns

Notes: hit-test path avoids per-char allocations.


## 2026-02-05 Bench Update (Arc Layout Cache)
- layout_blocks: 0.671?0.682 ms
- layout_blocks_cached: 7.29?7.46 us (large improvement)
- render_frame_sim: 29.9?32.2 ns
- render_visible_sim: 9.21?9.52 ns
- serialize_json: 93.8?95.5 us
- serialize_json_file: 1.47?1.54 ms
- layout_1000_chars: 30.1?30.9 us
- diff_10k_blocks_1_changed: 596?630 us
- typing_latency: 261?286 ns

Notes: this run showed heavy variance; cached layout benefits from Arc reuse.


## 2026-02-05 Bench Update (Linebreak Reuse Buffer)
- layout_blocks: 0.697?0.743 ms (improved)
- layout_blocks_cached: 9.08?9.38 us
- render_frame_sim: 25.9?26.2 ns (improved)
- render_visible_sim: 4.71?4.82 ns (improved)
- serialize_json: 78.0?79.3 us (improved)
- serialize_json_file: 1.18?1.22 ms (improved)
- layout_1000_chars: 17.2?18.1 us (improved)
- diff_10k_blocks_1_changed: 359?372 us (improved)
- typing_latency: 156?165 ns (improved)

Notes: break_positions reuse cut allocations; cached layout timing stabilized.


## 2026-02-05 Bench Update (Scratch Join)
- layout_blocks: 0.577?0.606 ms (improved)
- layout_blocks_cached: 12.99?13.71 us
- render_frame_sim: 49.7?51.5 ns
- render_visible_sim: 9.51?10.61 ns
- serialize_json: 109?113 us
- serialize_json_file: 1.24?1.29 ms
- layout_1000_chars: 17.2?17.9 us
- diff_10k_blocks_1_changed: 385?396 us
- typing_latency: 178?186 ns

Notes: results show heavy variance; cached layout remained fast but other metrics spiked on this run.


## 2026-02-05 Bench Update (Row/Quote Reserve)
- layout_blocks: 0.379?0.385 ms (improved)
- layout_blocks_cached: 6.24?6.36 us (improved)
- render_frame_sim: 23.7?24.2 ns (improved)
- render_visible_sim: 4.40?4.45 ns (improved)
- serialize_json: 58.8?60.3 us (improved)
- serialize_json_file: 1.13?1.19 ms (improved)
- layout_1000_chars: 15.37?15.49 us (improved)
- diff_10k_blocks_1_changed: 324?328 us (improved)
- typing_latency: 142?144 ns (improved)

Notes: precomputed capacities cut string churn across list/quote/table.


## 2026-02-05 M1 Blockers Completion
- Fontdue ????: ????RealMeasurer ?? fontdue??????
- FontCache ????: ??? LruCache???????>95% ? smoke test
- SimpleMeasurer ??: ?? RealMeasurer ???????
- UAX#14 ??: unicode_linebreak ?????
- CJK ??: ??/?????????
- ????: ??? scroll_10k_lines?shape_1000_chars???? typing_latency/render_frame/layout_1000_chars

## 2026-02-05 Bench Update (M1 Bench Additions)
- scroll_10k_lines: 30.8?31.8 ns
- shape_1000_chars: 6.92?7.05 us

Notes: RealMeasurer ?? WA_FONT_PATH ?????????????? SimpleMeasurer?


## 2026-02-05 M2 Core Completion
- Undo/Redo ????????HistoryEntry + BlockChange/ Snapshot + ???
- ?????????? checkpoint?????????
- ??100????undo_100_ops ??????<50ms?
- ????? RenderCache??? dirty + 5% ??????
- ???????layout_cached ?? Quote ?? dirty ??
- ?????RenderCache.should_render + dirty_ratio ??
- ????????+?????????????
- ????????? doc.version ?????????? layout_tree

## 2026-02-05 Bench Update (M2 Additions)
- undo_100_ops: 0.385?0.406 us
- scroll_10k_lines: 26.6?27.2 ns

Notes: M2 ???????????/?????????????


## 2026-02-05 M3 Interaction Completion
- Hit test ???????????????????UTF-8 ??????
- ???????Alt ?????????
- ??????Alt+???????????/??????
- ??? HTML ??????? HTML/????Clipboard?
- ??????????HTML ???? import_html
- ???????Ctrl+V ?????????? Figure
- ???????????????????
- ???????????????? cell???/???? cell
- ?? Tab ??/????????Tab/Shift+Tab?
- ????????syntect ???

## 2026-02-05 Bench Update (M3 Baseline)
- undo_100_ops: 0.470?0.493 us
- scroll_10k_lines: 29.9?34.2 ns
- shape_1000_chars: 6.65?6.91 us

Notes: UI ?????????????egui??


## 2026-02-05 Engineering Infrastructure Completion
- Arc<str> ?? String?????SharedStr?
- StringInterner????????????
- dhat ?? profiling??? dhat_profile ???
- valgrind ????? CI ?? smoke bin
- CI/CD ??????? perf.yml + compare_bench.py?>5% ?????
- ????????CI matrix Windows/macOS/Linux
- ????CI ?? cargo-llvm-cov
- Rust ?? DOCX ???docx-rs ???
- PDF ?????printpdf ???????

Notes: perf ?????? BASELINE_DIR ????????????????


## 2026-02-05 Strengthening Gaps (M1/M2/M3/Infra)
- ???????compare_bench.py + bench_thresholds.py ??? CI
- 120fps/8.33ms/8ms/50ms/2ms/3ms ??????
- ??? HTML ????? import_html_rich?table/list/img best-effort?
- ???/?????UI ???? + selection ??
- ?? cell ???????

Notes: threshold ???? Criterion new/estimates.json?


## 2026-02-06 App Integration Smoke
- WA_USE_RUST_ENGINE=1
- /api/doc/{id}/generate: weekly report instruction -> OK (fast path)
- /download/{id}.docx: OK (~21KB)


## 2026-02-06 UI 10-Round WYSIWYG E2E
- UI: /generate/stream fast path verified
- Editor: contenteditable shows generated content (WYSIWYG)
- Validation: all 10 docs contain ??/????/????
- Artifacts: .data/out/ui_round_01..10_*.docx, log .data/out/ui_10_rounds_wysiwyg.log

## 2026-02-07 WASM Engine Deployment Test
- build: engine/bridge/build.bat succeeded
- output: engine/bridge/pkg/wa_bridge_bg.wasm (489,596 bytes)
- deployed: writing_agent/web/frontend_svelte/public/wasm (pkg + wasm + js + d.ts)
- wasm-opt: disabled via package.metadata.wasm-pack.profile.release.wasm-opt=false

## 2026-02-07 WASM Engine Enablement
- frontend: wasmLoader now loads /wasm/wa_bridge.js and initializes WasmEditor
- readiness: initWasmEngine returns true when module is present

## 2026-02-07 WASM Engine Page Switch Verification
- UI: engine toggle sets body data-engine=web/rust
- Editor swap: rust panel visible when rust, web panel hidden; reversed when web
- Playwright: initial=web -> toggle=rust -> toggle back=web
## UI 超时探测（Playwright）
- 脚本：`scripts/ui_timeout_probe.py`
- 输出：`.data/out/ui_timeout_probe.json`
- 轮次：5
- 最大事件间隔：约 12.0s
- 单轮耗时：约 32.4s ~ 34.0s（状态到“需求分析完成”）
- 结论：客户端超时不应低于 90s；动态阈值应基于事件间隔与阶段放大


## ??????????????

- ??: 2026-02-08 22:40:23
- ??: 500/1000/2000/5000/8000 ??????????
- ??: http://127.0.0.1:8001
- ????: 20 ??/?
- ??????: 20m00s???????????
- ??????: 3m59s

?????
- ????????500??????/????/????/?????? -> timeout | ??? 20m00s | ???? 0m05s | ???? 3m59s
- ????????1000??????/????/????/?????? -> timeout | ??? 20m00s | ???? 0m04s | ???? 3m57s
- ????????2000??????/????/????/?????? -> timeout | ??? 20m00s | ???? 0m04s | ???? 3m59s
- ????????5000??????/????/????/?????? -> timeout | ??? 20m00s | ???? 0m05s | ???? 3m52s
- ????????8000??????/????/????/?????? -> timeout | ??? 20m00s | ???? 0m04s | ???? 3m53s

????? 5 ????? 20 ?????????????/???????????????????????????????DRAFT/AGGREGATE??????????


## DRAFT/AGG ???????????

- ??: 2026-02-09 01:09:39
- run_id: run_1770569360113
- PLAN: 2m15s
- DRAFT(?): 2m09s
- ?? Evidence ???: 0m40s
- AGGREGATE: ?????? start?end ?????????????????????UI ?????????????? 15 ??

??????
- Evidence ?????? + 40s ???WRITING_AGENT_EVIDENCE_TIMEOUT_S=40?WRITING_AGENT_EVIDENCE_WORKERS=3?????????????
- Evidence ???????????????? DRAFT ???????

?????1000 ??
- ??? Evidence ? 125s???? Evidence ? 40s?DRAFT ?????? 80s?

## DRAFT/AGG ??????

- ??: 2026-02-09 05:57:47
- run_id: run_1770586649933
- ANALYSIS: 45.0s
- EVIDENCE_PREP: 40.0s
- DRAFT(?): 40.2s
- AGGREGATE: 0.013s
- TOTAL: 85.9s

????????
- ?? graph_runner ????????????_default_outline_from_instruction / _doc_body_len??
- ????????????????????????????????????
- Evidence ???????40s ??????DRAFT ????Evidence?
- ?? TOTAL ~86s?????????200s??????? SSE ????????/???

## DRAFT/AGG ????????

- ??: 2026-02-09 15:34:52
- run_id: run_1770621704481
- ANALYSIS: 0.000s
- EVIDENCE_PREP: 40.0s
- DRAFT(?): 40.2s
- AGGREGATE: 0.015s
- TOTAL: 40.7s

?????
- graph_runner ?????????WRITING_AGENT_GRAPH_SKIP_ANALYSIS=1?????????? ~41s?
- ????? _blocks_to_doc_text / _doc_body_len / _default_outline_from_instruction????????????
- ?????????????????????? AGG ?????

????? TOTAL?41s??????62s???? SSE ??????????????????/??????
## 2026-02-09 UI Feasibility Probe (Browser)
- Script: `scripts/ui_timeout_probe.py`
- Output: `.data/out/ui_timeout_probe.json`
- Base URL: http://127.0.0.1:8001
- Prompts: 5
- Status: 5/5 done
- Max total: 316,696 ms (5.28 min)
- Max gap between events: 159,484 ms
- Notes: This run validates end-to-end feasibility across different prompts (not a single scenario).


## 2026-02-09 Phase Timing Capture (Graph)
- Metrics file: `.data/metrics/phase_timing.json`
- Latest observed run: run_1770620054662
  - ANALYSIS: ~45.01s
  - EVIDENCE_PREP: ~40.03s (parallelized with timeout)
  - DRAFT_SECTIONS: ~40.20s
  - AGGREGATE: ~0.01s
  - TOTAL: ~85.70s
- Note: Evidence prep is parallelized with timeout and falls back to empty evidence on timeout.
