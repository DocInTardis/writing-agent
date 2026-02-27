(() => {
  function init() {
    const el = (id) => document.getElementById(id);
    const app = document.querySelector(".app");
    if (!app) return;
    const docId = app.getAttribute("data-doc-id");

    const toastRoot = el("toastRoot");
    function toast(message, kind = "") {
      if (!toastRoot) return;
      const div = document.createElement("div");
      div.className = `toast ${kind}`.trim();
      div.textContent = message;
      toastRoot.appendChild(div);
      setTimeout(() => div.classList.add("hide"), 2600);
      setTimeout(() => div.remove(), 3200);
    }

    const modalRoot = el("modalRoot");
    const modalTitle = el("modalTitle");
    const modalBody = el("modalBody");
    const modalFoot = el("modalFoot");
    const systemName = "写作 Agent 工作台";
    function closeModal() {
      if (!modalRoot) return;
      modalRoot.classList.add("hidden");
      if (modalTitle) modalTitle.textContent = "";
      if (modalBody) modalBody.innerHTML = "";
      if (modalFoot) modalFoot.innerHTML = "";
    }
    function openModal({ title, body, actions }) {
      if (!modalRoot || !modalTitle || !modalBody || !modalFoot) return;
      modalTitle.textContent = title || "";
      modalBody.innerHTML = "";
      modalBody.appendChild(body);
      modalFoot.innerHTML = "";
      (actions || []).forEach((a) => modalFoot.appendChild(a));
      modalRoot.classList.remove("hidden");
    }

    function showSystemNameModal() {
      if (!modalRoot || !modalTitle || !modalBody || !modalFoot) {
        window.alert(systemName);
        return;
      }
      if (!modalRoot.classList.contains("hidden")) return;
      const body = document.createElement("div");
      body.className = "muted";
      body.textContent = systemName;
      const ok = document.createElement("button");
      ok.className = "btn primary";
      ok.type = "button";
      ok.textContent = "知道了";
      ok.addEventListener("click", closeModal);
      openModal({ title: "系统名称", body, actions: [ok] });
    }
    if (modalRoot) {
      modalRoot.addEventListener("click", (e) => {
        const t = e.target;
        if (t && t.getAttribute && t.getAttribute("data-close") === "1") closeModal();
      });
    }
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modalRoot && !modalRoot.classList.contains("hidden")) closeModal();
    });

  async function postJson(url, payload) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(await resp.text());
    return await resp.json();
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function parseTextBlocks(text) {
    const src = String(text || "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    if (!src.trim()) return { title: "", blocks: [], citations: {} };
    const jsonDoc = tryParseJsonDoc(src);
    if (jsonDoc) return jsonDoc;
    const lines = src.split("\n");
    const blocks = [];
    let title = "自动生成文档";
    let sawH1 = false;
    
    // 提取引用映射 [@citekey] -> [数字]
    const citations = {};
    let citationCounter = 1;
    const citePattern = /\[@([a-zA-Z0-9_-]+)\]/g;
    let match;
    while ((match = citePattern.exec(src)) !== null) {
      const key = match[1];
      if (!citations[key]) {
        citations[key] = citationCounter++;
      }
    }

    const flushPara = (buf) => {
      const t = buf.join("\n").trim();
      buf.length = 0;
      if (t) blocks.push({ type: "paragraph", text: t });
    };
    const buf = [];
    for (const line of lines) {
      const m = line.match(/^(#{1,3})\s+(.+?)\s*$/);
      if (m) {
        flushPara(buf);
        const level = m[1].length;
        const txt = m[2].trim();
        if (level === 1 && !sawH1 && txt) {
          title = txt;
          sawH1 = true;
        }
        blocks.push({ type: "heading", level, text: txt });
        continue;
      }
      if (!line.trim()) {
        flushPara(buf);
        continue;
      }
      buf.push(line);
    }
    flushPara(buf);
    if (!sawH1) blocks.unshift({ type: "heading", level: 1, text: title });
    return { title, blocks: explodeMarkers(blocks), citations };
  }

  function tryParseJsonDoc(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed) return null;
    let jsonText = trimmed;
    if (jsonText.startsWith("```")) {
      jsonText = jsonText.replace(/^```json/i, "").replace(/^```/, "");
      if (jsonText.endsWith("```")) jsonText = jsonText.slice(0, -3);
      jsonText = jsonText.trim();
    }
    if (!(jsonText.startsWith("{") || jsonText.startsWith("["))) return null;
    let data = null;
    try {
      data = JSON.parse(jsonText);
    } catch {
      return null;
    }
    return jsonToBlocks(data);
  }

  function jsonToBlocks(data) {
    if (!data || typeof data !== "object") return null;
    if (data.doc_ir && typeof data.doc_ir === "object") return docIrToBlocks(data.doc_ir);
    if (Array.isArray(data)) return blocksFromArray(data);
    if (Array.isArray(data.blocks)) return blocksFromArray(data.blocks, data.title);
    if (Array.isArray(data.sections)) return docIrToBlocks(data);
    return null;
  }

  function docIrToBlocks(doc) {
    const title = String(doc.title || "").trim();
    const sections = Array.isArray(doc.sections) ? doc.sections : [];
    const blocks = [];
    const titleNorm = title.toLowerCase();
    if (title) blocks.push({ type: "heading", level: 1, text: title });
    const pushSection = (sec) => {
      if (!sec || typeof sec !== "object") return;
      const secTitle = String(sec.title || "").trim();
      const level = Math.max(1, Math.min(6, Number(sec.level || 2)));
      if (secTitle) {
        const skip = level === 1 && titleNorm && secTitle.toLowerCase() === titleNorm;
        if (!skip) blocks.push({ type: "heading", level, text: secTitle });
      }
      const secBlocks = Array.isArray(sec.blocks) ? sec.blocks : [];
      for (const b of secBlocks) {
        const mapped = mapDocBlock(b);
        if (mapped) blocks.push(mapped);
      }
      const children = Array.isArray(sec.children) ? sec.children : [];
      for (const child of children) pushSection(child);
    };
    for (const sec of sections) pushSection(sec);
    const finalTitle = title || "自动生成文档";
    return { title: finalTitle, blocks: explodeMarkers(blocks), citations: {} };
  }

  function blocksFromArray(items, title) {
    const blocks = [];
    const docTitle = String(title || "").trim();
    if (docTitle) blocks.push({ type: "heading", level: 1, text: docTitle });
    let lastSection = "";
    for (const raw of items || []) {
      const sec = String(raw.section_id || raw.section_title || "").trim();
      if (sec && sec !== lastSection) {
        const heading = headingFromSectionId(sec);
        if (heading) blocks.push(heading);
        lastSection = sec;
      }
      const mapped = mapDocBlock(raw);
      if (mapped) blocks.push(mapped);
    }
    return { title: docTitle || "自动生成文档", blocks: explodeMarkers(blocks), citations: {} };
  }

  function headingFromSectionId(sectionId) {
    const m = /^H([1-6])::(.+)$/.exec(sectionId);
    if (m) {
      const level = Math.max(1, Math.min(6, Number(m[1] || 2)));
      const text = String(m[2] || "").trim();
      if (text) return { type: "heading", level, text };
    }
    return { type: "heading", level: 2, text: sectionId };
  }

  function mapDocBlock(block) {
    if (!block || typeof block !== "object") return null;
    const t = String(block.type || "paragraph").toLowerCase();
    if (t === "heading") {
      return { type: "heading", level: Number(block.level || 2), text: String(block.text || "") };
    }
    if (t === "paragraph" || t === "text" || t === "p") {
      const text = String(block.text || "").trim();
      return text ? { type: "paragraph", text } : null;
    }
    if (t === "list" || t === "bullets" || t === "bullet") {
      const items = Array.isArray(block.items) ? block.items : [];
      if (items.length) {
        return { type: "paragraph", text: items.map((v) => `• ${String(v).trim()}`).join("\n") };
      }
      const text = String(block.text || "").trim();
      return text ? { type: "paragraph", text } : null;
    }
    if (t === "table") {
      return { type: "table", table: block.table || block.data || block };
    }
    if (t === "figure") {
      return { type: "figure", figure: block.figure || block.data || block };
    }
    const fallback = String(block.text || "").trim();
    return fallback ? { type: "paragraph", text: fallback } : null;
  }

  function explodeMarkers(blocks) {
    const out = [];
    const markerRe = /\[\[(FIGURE|TABLE)\s*:\s*(\{[\s\S]*?\})\s*\]\]/gi;
    for (const b of blocks) {
      if (b.type !== "paragraph" || !String(b.text || "").trim()) {
        out.push(b);
        continue;
      }
      const txt = String(b.text || "");
      let pos = 0;
      let m;
      while ((m = markerRe.exec(txt))) {
        const before = txt.slice(pos, m.index).trim();
        if (before) out.push({ type: "paragraph", text: before });
        const kind = String(m[1] || "").toLowerCase();
        const raw = String(m[2] || "").trim();
        let data = null;
        try {
          data = JSON.parse(raw);
        } catch {
          data = { raw };
        }
        if (kind === "table") out.push({ type: "table", table: data });
        else out.push({ type: "figure", figure: data });
        pos = m.index + m[0].length;
      }
      const tail = txt.slice(pos).trim();
      if (tail) out.push({ type: "paragraph", text: tail });
    }
    return out;
  }

  const figureCache = new Map();
  async function renderFigure(spec) {
    const key = JSON.stringify(spec || {});
    if (figureCache.has(key)) return figureCache.get(key);
    const resp = await fetch("/api/figure/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    figureCache.set(key, data);
    return data;
  }

  async function renderPreviewFromSource(text) {
    const preview = el("preview");
    const parsed = parseTextBlocks(text);
    const citations = parsed.citations || {};
    const htmlParts = ['<div class="sheet">'];
    if (!parsed.blocks.length) {
      htmlParts.push('<p class="muted">空白文档：在右侧输入要求生成，或切到"源文本"自行编写。</p>');
      htmlParts.push("</div>");
      preview.innerHTML = htmlParts.join("");
      return;
    }
    for (const b of parsed.blocks) {
      if (b.type === "heading") {
        const level = Math.max(1, Math.min(3, Number(b.level || 1)));
        htmlParts.push(`<h${level}>${escapeHtml(b.text || "")}</h${level}>`);
      } else if (b.type === "paragraph") {
        let paraText = escapeHtml(b.text || "").replace(/\n/g, "<br/>");
        // 替换引用标记 [@citekey] -> [数字]上标
        paraText = paraText.replace(/\[@([a-zA-Z0-9_-]+)\]/g, (match, key) => {
          const num = citations[key] || '?';
          return `<sup class="citation-ref">[${num}]</sup>`;
        });
        htmlParts.push(`<p>${paraText}</p>`);
      } else if (b.type === "table") {
        const t = b.table || {};
        const caption = String(t.caption || "").trim();
        const cols = Array.isArray(t.columns) ? t.columns.map((x) => String(x)) : [];
        const rows = Array.isArray(t.rows) ? t.rows : [];
        htmlParts.push(`<figure><div class="muted">${escapeHtml(caption || "表格")}</div>`);
        htmlParts.push("<table><thead><tr>");
        (cols.length ? cols : ["列1", "列2"]).forEach((c) => htmlParts.push(`<th>${escapeHtml(c)}</th>`));
        htmlParts.push("</tr></thead><tbody>");
        (rows.length ? rows : [["[待补充]", "[待补充]"]]).forEach((r) => {
          htmlParts.push("<tr>");
          const rr = Array.isArray(r) ? r : [String(r)];
          (cols.length ? cols.length : 2).toString();
          const width = cols.length || 2;
          for (let i = 0; i < width; i++) htmlParts.push(`<td>${escapeHtml(String(rr[i] ?? ""))}</td>`);
          htmlParts.push("</tr>");
        });
        htmlParts.push("</tbody></table></figure>");
      } else if (b.type === "figure") {
        const spec = b.figure || {};
        const caption = String(spec.caption || "").trim() || "图";
        const payload = escapeHtml(JSON.stringify(spec));
        htmlParts.push(
          `<figure class="fig" data-fig="1" data-spec="${payload}"><div class="fig-ph">图生成中…</div><figcaption>图：${escapeHtml(
            caption,
          )}</figcaption></figure>`,
        );
      }
    }
    htmlParts.push("</div>");
    preview.innerHTML = htmlParts.join("");

    const figs = Array.from(preview.querySelectorAll('figure[data-fig="1"]'));
    await Promise.all(
      figs.map(async (f) => {
        const raw = f.getAttribute("data-spec") || "{}";
        let spec = {};
        try {
          spec = JSON.parse(raw);
        } catch {
          spec = { caption: "图（解析失败）" };
        }
        try {
          const data = await renderFigure(spec);
          const holder = f.querySelector(".fig-ph");
          if (holder) holder.outerHTML = data.svg || '<div class="fig-ph">图生成失败</div>';
        } catch (e) {
          const holder = f.querySelector(".fig-ph");
          if (holder) holder.textContent = `图生成失败：${e.message}`;
        }
      }),
    );
    
    // 渲染Mermaid图表和LaTeX公式
    renderDiagramsAndFormulas(preview);
  }

  function setActiveTab(name) {
    const tab = name === "edit" ? "source" : name;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.getAttribute("data-tab") === name));
    el("preview").classList.toggle("hidden", tab !== "preview");
    el("source").classList.toggle("hidden", tab !== "source");
  }

  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      setActiveTab(t.getAttribute("data-tab"));
      if (t.getAttribute("data-tab") === "preview") renderPreviewFromSource(el("source").value);
    }),
  );

  function insertAtCursor(text) {
    const ta = el("source");
    if (!ta) return;
    const start = ta.selectionStart || 0;
    const end = ta.selectionEnd || 0;
    const before = ta.value.slice(0, start);
    const after = ta.value.slice(end);
    ta.value = before + text + after;
    const pos = start + text.length;
    ta.setSelectionRange(pos, pos);
    updateWordCount(ta.value);
    renderPreviewFromSource(ta.value);
    saveDebounce(() => saveSource().catch(err => console.warn('[auto-save]', err)), 600);
  }

  function setHeading(level) {
    const ta = el("source");
    if (!ta) return;
    const prefix = "#".repeat(level) + " ";
    const v = ta.value.replace(/\r/g, "");
    const pos = ta.selectionStart || 0;
    const lineStart = v.lastIndexOf("\n", pos - 1) + 1;
    const lineEnd = v.indexOf("\n", pos);
    const end = lineEnd >= 0 ? lineEnd : v.length;
    const line = v.slice(lineStart, end);
    const next = prefix + line.replace(/^#{1,3}\s+/, "");
    ta.value = v.slice(0, lineStart) + next + v.slice(end);
    const newPos = lineStart + prefix.length;
    ta.setSelectionRange(newPos, newPos);
    updateWordCount(ta.value);
    renderPreviewFromSource(ta.value);
    saveDebounce(() => saveSource().catch(err => console.warn('[auto-save]', err)), 600);
  }

  el("tbH1")?.addEventListener("click", () => {
    setActiveTab("source");
    setHeading(1);
  });
  el("tbH2")?.addEventListener("click", () => {
    setActiveTab("source");
    setHeading(2);
  });
  el("tbH3")?.addEventListener("click", () => {
    setActiveTab("source");
    setHeading(3);
  });
  el("tbTable")?.addEventListener("click", () => {
    setActiveTab("source");
    insertAtCursor('\n\n[[TABLE:{"caption":"[待补充]","columns":["列1","列2"],"rows":[["[待补充]","[待补充]"]]}]]\n\n');
  });
  el("tbFigure")?.addEventListener("click", () => {
    setActiveTab("source");
    insertAtCursor('\n\n[[FIGURE:{"type":"flow","caption":"[待补充]","data":{}}]]\n\n');
  });
  el("tbSkeleton")?.addEventListener("click", () => {
    setActiveTab("source");
    const ta = el("source");
    if (!ta) return;
    const skeleton =
      "# [请填写题目]\n\n" +
      "## 摘要\n\n[待补充]：摘要应概括背景、目标、方法、结果与结论。\n\n" +
      "## 关键词\n\n[待补充]：关键词1；关键词2；关键词3\n\n" +
      "## 引言\n\n[待补充]：研究背景与意义、国内外现状、本文工作与结构。\n\n" +
      "## 需求分析\n\n[待补充]：业务场景、功能需求、非功能需求（性能/安全/可用性）、约束与假设。\n\n" +
      "## 总体设计\n\n[待补充]：系统架构、模块划分、数据流与关键流程。\n\n" +
      '[[FIGURE:{"type":"flow","caption":"总体流程图（待补充）","data":{}}]]\n\n' +
      "## 数据库设计\n\n[待补充]：概念模型、逻辑模型、表结构设计与约束。\n\n" +
      '[[FIGURE:{"type":"er","caption":"ER图（待补充）","data":{}}]]\n\n' +
      '[[TABLE:{"caption":"核心数据表（待补充）","columns":["表名","字段","类型","约束","说明"],"rows":[["[待补充]","[待补充]","[待补充]","[待补充]","[待补充]"]]}]]\n\n' +
      "## 详细设计与实现\n\n[待补充]：关键类/接口设计、核心算法、异常处理、权限与审计、接口契约。\n\n" +
      '[[FIGURE:{"type":"sequence","caption":"关键业务时序图（待补充）","data":{}}]]\n\n' +
      "## 测试与结果分析\n\n[待补充]：测试方案、用例、覆盖范围、结果汇总、问题与改进。\n\n" +
      '[[TABLE:{"caption":"测试用例汇总（待补充）","columns":["编号","目标","输入","预期","结果"],"rows":[["[待补充]","[待补充]","[待补充]","[待补充]","[待补充]"]]}]]\n\n' +
      "## 结论与展望\n\n[待补充]：工作总结、贡献、局限与后续工作。\n\n" +
      "## 参考文献\n\n[待补充]\n\n" +
      "## 致谢\n\n[待补充]\n\n" +
      "## 附录\n\n[待补充]\n";

    ta.value = skeleton;
    updateWordCount(ta.value);
    renderPreviewFromSource(ta.value);
    saveDebounce(() => saveSource().catch(err => console.warn('[auto-save]', err)), 600);
    toast("已插入毕业设计骨架", "ok");
  });

  const graph = el("graph");
  function setGraphState(name) {
    Array.from(graph.querySelectorAll(".node")).forEach((n) => n.classList.toggle("active", n.getAttribute("data-state") === name));
  }

  const status = el("docStatus");
  const problemsBox = el("problems");
  function setStatus(text, kind) {
    status.textContent = text;
    status.classList.toggle("ok", kind === "ok");
    status.classList.toggle("bad", kind === "bad");
  }

  function updateWordCount(text) {
    const s = String(text || "");
    const n = s.replace(/\s/g, "").length;
    el("wordCount").textContent = n ? `字数≈${n}` : "";
  }

  const saveDebounce = (() => {
    let t = null;
    return (fn, ms) => {
      if (t) clearTimeout(t);
      t = setTimeout(fn, ms);
    };
  })();

  let currentFormatting = {};
  let currentPrefs = {};
  let settingsApplied = false;
  let generating = false;
  let userEditedDuringGeneration = false;

  async function saveSource() {
    const txt = el("source").value || "";
    await postJson(`/api/doc/${docId}/save`, { text: txt, formatting: currentFormatting, generation_prefs: currentPrefs });
  }

  const sourceEl = el("source");
  if (sourceEl) {
    sourceEl.addEventListener("input", () => {
      updateWordCount(sourceEl.value);
      if (generating) userEditedDuringGeneration = true;
      setStatus("保存中...", "");
      saveDebounce(async () => {
        try {
          await saveSource();
          setStatus("已保存", "ok");
          setTimeout(() => setStatus("就绪", ""), 2000);
        } catch (e) {
          setStatus("保存失败", "bad");
          toast(`保存失败：${e.message}`, "bad");
        }
      }, 500);
    });
  }
  
  // 快捷键
  document.addEventListener("keydown", (e) => {
    // Ctrl+S 保存
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      saveSource().then(() => toast("已保存", "ok")).catch(err => toast(`保存失败：${err.message}`, "bad"));
      return;
    }
    
    // Ctrl+Z 撤销
    if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
      e.preventDefault();
      performUndo();
      return;
    }
    
    // Ctrl+Y 或 Ctrl+Shift+Z 重做
    if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
      e.preventDefault();
      performRedo();
      return;
    }
    
    // Esc 关闭弹窗
    if (e.key === "Escape") {
      const modal = el("modalRoot");
      if (modal && !modal.classList.contains("hidden")) {
        closeModal();
      }
      return;
    }
    
    // Ctrl+B 加粗（仅在编辑区）
    if ((e.ctrlKey || e.metaKey) && e.key === "b" && e.target === sourceEl) {
      e.preventDefault();
      const start = sourceEl.selectionStart;
      const end = sourceEl.selectionEnd;
      const selected = sourceEl.value.substring(start, end);
      sourceEl.setRangeText(`**${selected || '粗体'}**`, start, end, "end");
      sourceEl.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    
    // Ctrl+I 斜体（仅在编辑区）
    if ((e.ctrlKey || e.metaKey) && e.key === "i" && e.target === sourceEl) {
      e.preventDefault();
      const start = sourceEl.selectionStart;
      const end = sourceEl.selectionEnd;
      const selected = sourceEl.value.substring(start, end);
      sourceEl.setRangeText(`*${selected || '斜体'}*`, start, end, "end");
      sourceEl.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    
    // Ctrl+Enter 发送指令
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && e.target === el("instruction")) {
      e.preventDefault();
      const btn = el("btnGenerate");
      if (btn && !btn.disabled) btn.click();
      return;
    }
  });

  async function loadDoc() {
    const resp = await fetch(`/api/doc/${docId}`);
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    el("source").value = String(data.text || "");
    updateWordCount(el("source").value);
    
    // 提取标题
    const text = String(data.text || "");
    const titleMatch = text.match(/^#\s+(.+?)$/m);
    const titleInput = el("docTitle");
    if (titleInput) {
      titleInput.value = titleMatch ? titleMatch[1].trim() : "自动生成文档";
      titleInput.addEventListener("input", () => {
        const oldText = el("source").value;
        const newTitle = titleInput.value.trim() || "自动生成文档";
        const newText = oldText.replace(/^#\s+.+?$/m, `# ${newTitle}`);
        if (newText !== oldText) {
          el("source").value = newText;
          el("source").dispatchEvent(new Event("input", { bubbles: true }));
        }
      });
    }
    
    const info = el("templateInfo");
    if (data.template_name) {
      const hs = Array.isArray(data.required_h2) ? data.required_h2 : [];
      info.textContent = `已加载模板：${data.template_name}${hs.length ? " · 章节：" + hs.join(" / ") : ""}`;
    } else {
      info.textContent = "未加载模板";
    }

    if (data.formatting && typeof data.formatting === "object") currentFormatting = data.formatting || {};
    if (data.generation_prefs && typeof data.generation_prefs === "object") currentPrefs = data.generation_prefs || {};
    settingsApplied = !!(Object.keys(currentFormatting || {}).length || Object.keys(currentPrefs || {}).length);

    // best-effort populate settings UI (if present)
    const purposeEl = el("settingPurpose");
    if (purposeEl && currentPrefs.purpose) purposeEl.value = String(currentPrefs.purpose);
    const fsEl = el("settingFontSize");
    if (fsEl && currentFormatting.font_size_name && currentFormatting.font_size_pt) {
      fsEl.value = `${currentFormatting.font_size_name}|${currentFormatting.font_size_pt}`;
    }
    const lsEl = el("settingLineSpacing");
    if (lsEl && currentFormatting.line_spacing) lsEl.value = String(currentFormatting.line_spacing);
    const coverEl = el("settingCover");
    if (coverEl && typeof currentPrefs.include_cover === "boolean") coverEl.checked = !!currentPrefs.include_cover;
    const tocEl = el("settingToc");
    if (tocEl && typeof currentPrefs.include_toc === "boolean") tocEl.checked = !!currentPrefs.include_toc;
    const headerEl = el("settingHeader");
    if (headerEl && typeof currentPrefs.include_header === "boolean") headerEl.checked = !!currentPrefs.include_header;
    const pageNoEl = el("settingPageNo");
    if (pageNoEl && typeof currentPrefs.page_numbers === "boolean") pageNoEl.checked = !!currentPrefs.page_numbers;
    if (Array.isArray(currentPrefs.figure_types)) {
      const set = new Set(currentPrefs.figure_types.map((x) => String(x)));
      document.querySelectorAll("#figureChips input[type=checkbox]").forEach((c) => {
        c.checked = set.has(String(c.value));
      });
    }
    await renderPreviewFromSource(el("source").value);
  }

  function readSettingsFromUi() {
    const purpose = String(el("settingPurpose")?.value || "").trim() || "毕业设计/课程设计报告";
    const fsRaw = String(el("settingFontSize")?.value || "小四|12");
    const [fsName, fsPtRaw] = fsRaw.split("|");
    const fontSizePt = Number(fsPtRaw || 12);
    const lineSpacing = Number(el("settingLineSpacing")?.value || 1.5);
    const includeCover = !!el("settingCover")?.checked;
    const includeToc = !!el("settingToc")?.checked;
    const includeHeader = !!el("settingHeader")?.checked;
    const pageNumbers = !!el("settingPageNo")?.checked;
    const figureTypes = Array.from(document.querySelectorAll("#figureChips input[type=checkbox]"))
      .filter((c) => c.checked)
      .map((c) => String(c.value));

    currentFormatting = {
      font_name: "Times New Roman",
      font_name_east_asia: "宋体",
      font_size_name: fsName || "小四",
      font_size_pt: Number.isFinite(fontSizePt) ? fontSizePt : 12,
      line_spacing: Number.isFinite(lineSpacing) ? lineSpacing : 1.5,
    };
    currentPrefs = {
      purpose,
      figure_types: figureTypes,
      table_types: ["compare", "summary", "metrics"],
      include_cover: includeCover,
      include_toc: includeToc,
      toc_levels: 3,
      include_header: includeHeader,
      page_numbers: pageNumbers,
      page_margins_cm: 2.54,
    };
    return { formatting: currentFormatting, generation_prefs: currentPrefs };
  }

  async function saveSettings(quiet = false) {
    const payload = readSettingsFromUi();
    await postJson(`/api/doc/${docId}/settings`, payload);
    settingsApplied = true;
    if (!quiet) toast("已应用文档格式", "ok");
  }

  const btnApplySettings = el("btnApplySettings");
  if (btnApplySettings) {
    btnApplySettings.addEventListener("click", async () => {
      try {
        await saveSettings(false);
      } catch (e) {
        toast(`应用失败：${e.message}`, "bad");
      }
    });
  }

  async function ensureSettingsBeforeGenerate() {
    if (settingsApplied) return true;
    if (!el("settingPurpose") && !el("settingFontSize") && !el("settingLineSpacing")) {
      // no settings UI, proceed with defaults
      readSettingsFromUi();
      settingsApplied = true;
      return true;
    }
    const body = document.createElement("div");
    body.innerHTML = `<div class="muted">你的要求可能缺少“用途/字号/行距/图表类型”等信息。可直接使用系统默认，或在右侧“文档格式”里自定义后再生成。</div>`;
    const useDefaults = document.createElement("button");
    useDefaults.className = "btn primary";
    useDefaults.type = "button";
    useDefaults.textContent = "使用默认并继续";
    useDefaults.addEventListener("click", async () => {
      try {
        await saveSettings(true);
        closeModal();
      } catch (e) {
        toast(`应用失败：${e.message}`, "bad");
      }
    });
    const cancel = document.createElement("button");
    cancel.className = "btn ghost";
    cancel.type = "button";
    cancel.textContent = "取消";
    cancel.addEventListener("click", closeModal);
    openModal({ title: "生成前确认", body, actions: [cancel, useDefaults] });

    await new Promise((resolve) => {
      const t = setInterval(() => {
        if (settingsApplied || (modalRoot && modalRoot.classList.contains("hidden"))) {
          clearInterval(t);
          resolve();
        }
      }, 120);
    });
    return settingsApplied;
  }

  el("btnNew")?.addEventListener("click", () => {
    window.location.href = "/";
  });
  el("btnNew")?.addEventListener("contextmenu", (e) => e.preventDefault());
  el("btnNew")?.addEventListener("auxclick", (e) => e.preventDefault());
  el("btnNew")?.addEventListener("mouseup", (e) => e.preventDefault());

  // 工具栏按钮实现
  document.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-action");
      const source = el("source");
      if (!source) return;
      
      const start = source.selectionStart;
      const end = source.selectionEnd;
      const selected = source.value.substring(start, end);
      let before = source.value.substring(0, start);
      let after = source.value.substring(end);
      
      switch (action) {
        case "bold":
          source.setRangeText(`**${selected || '粗体文本'}**`, start, end, "end");
          break;
        case "italic":
          source.setRangeText(`*${selected || '斜体文本'}*`, start, end, "end");
          break;
        case "underline":
          source.setRangeText(`<u>${selected || '下划线文本'}</u>`, start, end, "end");
          break;
        case "strike":
          source.setRangeText(`~~${selected || '删除线文本'}~~`, start, end, "end");
          break;
        case "heading1":
          source.setRangeText(`# ${selected || '一级标题'}`, start, end, "end");
          break;
        case "heading2":
          source.setRangeText(`## ${selected || '二级标题'}`, start, end, "end");
          break;
        case "heading3":
          source.setRangeText(`### ${selected || '三级标题'}`, start, end, "end");
          break;
        case "list-bullet":
          source.setRangeText(`- ${selected || '列表项'}`, start, end, "end");
          break;
        case "list-number":
          source.setRangeText(`1. ${selected || '列表项'}`, start, end, "end");
          break;
        case "quote":
          source.setRangeText(`> ${selected || '引用文本'}`, start, end, "end");
          break;
        case "clear-format":
          if (selected) {
            const cleaned = selected.replace(/[*_~#>`<\[\]]/g, '');
            source.setRangeText(cleaned, start, end, "end");
          }
          break;
        case "insert-table":
          source.setRangeText(`\n| 列1 | 列2 | 列3 |\n|-----|-----|-----|\n| 值1 | 值2 | 值3 |\n`, start, end, "end");
          break;
        case "insert-figure":
          source.setRangeText(`\n![图片描述](图片URL)\n`, start, end, "end");
          break;
        case "insert-chart":
          source.setRangeText(`\n[[FIGURE:图表标题]]\n`, start, end, "end");
          break;
        case "insert-link":
          source.setRangeText(`[${selected || '链接文本'}](URL)`, start, end, "end");
          break;
        case "insert-citation":
          // 插入引用标记
          showCitationPicker((citekey) => {
            source.setRangeText(`[@${citekey}]`, start, end, "end");
            source.dispatchEvent(new Event("input", { bubbles: true }));
            renderPreviewFromSource(source.value);
          });
          return;
        case "word-count":
          // 显示详细统计
          showWordCountModal(source.value);
          return;
        case "find-replace":
          // 查找替换功能
          showFindReplaceModal(source);
          return;
        case "ai-polish":
          // AI润色选中段落
          if (selected) {
            aiPolishText(selected, start, end);
          } else {
            toast("请先选择要润色的文本", "");
          }
          return;
        case "ai-expand":
          // AI扩写选中文本
          if (selected) {
            aiExpandText(selected, start, end);
          } else {
            toast("请先选择要扩写的文本", "");
          }
          return;
        case "ai-summarize":
          // AI总结全文
          aiSummarizeDocument(source.value);
          return;
        case "check-issues":
          // 检查格式问题
          checkDocumentIssues(source.value);
          return;
        case "insert-template":
          // 插入模板片段
          showTemplatePickerModal(source, start, end);
          return;
        default:
          return;
      }
      
      source.dispatchEvent(new Event("input", { bubbles: true }));
      renderPreviewFromSource(source.value);
    });
  });

  // === 增强工具栏功能实现 ===
  
  // 引用选择器
  function showCitationPicker(callback) {
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="citation-picker">
        <input type="text" id="citeKeyInput" class="input" placeholder="输入引用键，如: zhang2020" />
        <div class="muted" style="margin-top: 8px;">提示：引用键应简洁明了，如"作者姓名+年份"</div>
      </div>
    `;
    const insert = document.createElement("button");
    insert.className = "btn primary";
    insert.textContent = "插入";
    insert.addEventListener("click", () => {
      const key = el("citeKeyInput").value.trim();
      if (!key) {
        toast("请输入引用键", "");
        return;
      }
      callback(key);
      closeModal();
    });
    const cancel = document.createElement("button");
    cancel.className = "btn ghost";
    cancel.textContent = "取消";
    cancel.addEventListener("click", closeModal);
    openModal({ title: "插入引用标记", body, actions: [cancel, insert] });
  }

  // 字数统计详情
  function showWordCountModal(text) {
    const chars = text.length;
    const charsNoSpace = text.replace(/\s/g, '').length;
    const words = text.split(/\s+/).filter(w => w.length > 0).length;
    const lines = text.split('\n').length;
    const paragraphs = text.split(/\n\s*\n/).filter(p => p.trim()).length;
    const headings = (text.match(/^#{1,3}\s+/gm) || []).length;
    const citations = (text.match(/\[@[a-zA-Z0-9_-]+\]/g) || []).length;
    
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="stat-grid">
        <div class="stat-item"><strong>总字符数：</strong>${chars}</div>
        <div class="stat-item"><strong>不含空格：</strong>${charsNoSpace}</div>
        <div class="stat-item"><strong>单词数：</strong>${words}</div>
        <div class="stat-item"><strong>行数：</strong>${lines}</div>
        <div class="stat-item"><strong>段落数：</strong>${paragraphs}</div>
        <div class="stat-item"><strong>标题数：</strong>${headings}</div>
        <div class="stat-item"><strong>引用数：</strong>${citations}</div>
      </div>
    `;
    const close = document.createElement("button");
    close.className = "btn primary";
    close.textContent = "关闭";
    close.addEventListener("click", closeModal);
    openModal({ title: "文档统计", body, actions: [close] });
  }

  // 查找替换
  function showFindReplaceModal(source) {
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="find-replace-panel">
        <label>查找：<input type="text" id="findText" class="input" /></label>
        <label>替换为：<input type="text" id="replaceText" class="input" /></label>
        <label><input type="checkbox" id="matchCase" /> 区分大小写</label>
      </div>
    `;
    const replaceAll = document.createElement("button");
    replaceAll.className = "btn primary";
    replaceAll.textContent = "全部替换";
    replaceAll.addEventListener("click", () => {
      const find = el("findText").value;
      const replace = el("replaceText").value;
      const matchCase = el("matchCase").checked;
      if (!find) {
        toast("请输入查找内容", "");
        return;
      }
      const regex = new RegExp(find.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), matchCase ? 'g' : 'gi');
      const newText = source.value.replace(regex, replace);
      const count = (source.value.match(regex) || []).length;
      source.value = newText;
      source.dispatchEvent(new Event("input", { bubbles: true }));
      renderPreviewFromSource(newText);
      toast(`已替换 ${count} 处`, "ok");
      closeModal();
    });
    const cancel = document.createElement("button");
    cancel.className = "btn ghost";
    cancel.textContent = "取消";
    cancel.addEventListener("click", closeModal);
    openModal({ title: "查找与替换", body, actions: [cancel, replaceAll] });
  }

  // AI润色文本
  async function aiPolishText(text, start, end) {
    try {
      toast("AI润色中...", "");
      const resp = await postJson("/api/polish", { text });
      if (resp.polished) {
        const source = el("source");
        source.setRangeText(resp.polished, start, end, "end");
        source.dispatchEvent(new Event("input", { bubbles: true }));
        renderPreviewFromSource(source.value);
        toast("润色完成", "ok");
      } else {
        toast("润色失败", "bad");
      }
    } catch (e) {
      toast(`润色失败：${e.message}`, "bad");
    }
  }

  // AI扩写文本
  async function aiExpandText(text, start, end) {
    try {
      toast("AI扩写中...", "");
      const resp = await postJson("/api/expand", { text });
      if (resp.expanded) {
        const source = el("source");
        source.setRangeText(resp.expanded, start, end, "end");
        source.dispatchEvent(new Event("input", { bubbles: true }));
        renderPreviewFromSource(source.value);
        toast("扩写完成", "ok");
      } else {
        toast("扩写失败", "bad");
      }
    } catch (e) {
      toast(`扩写失败：${e.message}`, "bad");
    }
  }

  // AI总结文档
  async function aiSummarizeDocument(text) {
    try {
      toast("AI总结中...", "");
      const resp = await postJson("/api/summarize", { text });
      if (resp.summary) {
        const body = document.createElement("div");
        body.innerHTML = `<div class="summary-result">${escapeHtml(resp.summary)}</div>`;
        const close = document.createElement("button");
        close.className = "btn primary";
        close.textContent = "关闭";
        close.addEventListener("click", closeModal);
        openModal({ title: "文档摘要", body, actions: [close] });
      } else {
        toast("总结失败", "bad");
      }
    } catch (e) {
      toast(`总结失败：${e.message}`, "bad");
    }
  }

  // 检查文档问题
  function checkDocumentIssues(text) {
    const issues = [];
    
    // 检查标题层级
    const headings = text.match(/^(#{1,3})\s+(.+)$/gm) || [];
    let prevLevel = 0;
    headings.forEach((h, i) => {
      const level = h.match(/^(#{1,3})/)[1].length;
      if (i > 0 && level > prevLevel + 1) {
        issues.push(`标题层级跳跃：第${i+1}个标题从${prevLevel}级跳到${level}级`);
      }
      prevLevel = level;
    });
    
    // 检查引用
    const citations = text.match(/\[@([a-zA-Z0-9_-]+)\]/g) || [];
    if (citations.length > 0 && !text.includes('参考文献') && !text.includes('References')) {
      issues.push(`发现${citations.length}个引用标记，但未找到"参考文献"章节`);
    }
    
    // 检查空段落
    const emptyParas = text.match(/\n\s*\n\s*\n/g) || [];
    if (emptyParas.length > 0) {
      issues.push(`发现${emptyParas.length}处连续空行，建议删除多余空行`);
    }
    
    // 检查待补充标记
    const placeholders = (text.match(/\[待补充\]/g) || []).length;
    if (placeholders > 0) {
      issues.push(`发现${placeholders}处"[待补充]"标记，请补全内容`);
    }
    
    const body = document.createElement("div");
    if (issues.length === 0) {
      body.innerHTML = '<div class="muted">✓ 未发现明显问题</div>';
    } else {
      body.innerHTML = `<ul class="issue-list">${issues.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
    }
    const close = document.createElement("button");
    close.className = "btn primary";
    close.textContent = "关闭";
    close.addEventListener("click", closeModal);
    openModal({ title: `文档检查（${issues.length}个问题）`, body, actions: [close] });
  }

  // 模板片段选择器
  function showTemplatePickerModal(source, start, end) {
    const templates = [
      { name: "实验步骤", content: "## 实验步骤\n\n1. **准备阶段**：[描述准备工作]\n2. **实施阶段**：[描述具体步骤]\n3. **数据收集**：[说明数据收集方法]\n4. **结果分析**：[分析结果]\n" },
      { name: "对比表格", content: "\n| 方案 | 优点 | 缺点 | 适用场景 |\n|------|------|------|----------|\n| 方案A | [优点] | [缺点] | [场景] |\n| 方案B | [优点] | [缺点] | [场景] |\n" },
      { name: "结论模板", content: "## 结论\n\n本研究通过[方法]，针对[问题]展开了系统分析。主要发现包括：\n\n1. [发现一]\n2. [发现二]\n3. [发现三]\n\n研究局限性：[说明]\n\n未来工作：[展望]\n" },
      { name: "文献综述", content: "## 文献综述\n\n在[领域]方面，已有大量研究成果。[@ref1]提出了[观点]，[@ref2]则从[角度]进行了分析。综合来看，现有研究存在以下不足：\n\n1. [不足一]\n2. [不足二]\n\n本研究将在此基础上[创新点]。\n" }
    ];
    
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="template-list">
        ${templates.map((t, i) => `
          <button class="template-item" data-index="${i}">
            <strong>${t.name}</strong>
          </button>
        `).join('')}
      </div>
    `;
    
    body.querySelectorAll(".template-item").forEach((btn, i) => {
      btn.addEventListener("click", () => {
        source.setRangeText(templates[i].content, start, end, "end");
        source.dispatchEvent(new Event("input", { bubbles: true }));
        renderPreviewFromSource(source.value);
        toast(`已插入"${templates[i].name}"模板`, "ok");
        closeModal();
      });
    });
    
    const cancel = document.createElement("button");
    cancel.className = "btn ghost";
    cancel.textContent = "取消";
    cancel.addEventListener("click", closeModal);
    openModal({ title: "选择模板片段", body, actions: [cancel] });
  }

  // === 工具栏增强功能实现结束 ===

  // === 版本树功能 ===
  
  let autoCommitTimer = null;
  
  // 自动提交（3秒无编辑后）
  function scheduleAutoCommit() {
    if (autoCommitTimer) clearTimeout(autoCommitTimer);
    autoCommitTimer = setTimeout(async () => {
      try {
        await postJson(`/api/doc/${docId}/version/commit`, {
          message: "自动保存",
          author: "user"
        });
        console.log("[版本] 自动提交成功");
      } catch (e) {
        console.warn("[版本] 自动提交失败:", e);
      }
    }, 3000);
  }
  
  // 手动提交版本
  async function manualCommitVersion() {
    const body = document.createElement("div");
    body.innerHTML = `
      <label>提交信息：<br/><input type="text" id="commitMessage" class="input" placeholder="描述本次修改内容" style="width: 100%;" /></label>
    `;
    const commit = document.createElement("button");
    commit.className = "btn primary";
    commit.textContent = "提交";
    commit.addEventListener("click", async () => {
      const message = el("commitMessage").value.trim() || "手动保存";
      try {
        const resp = await postJson(`/api/doc/${docId}/version/commit`, {
          message,
          author: "user"
        });
        toast(`已提交版本 ${resp.version_id.slice(0, 7)}`, "ok");
        closeModal();
      } catch (e) {
        toast(`提交失败：${e.message}`, "bad");
      }
    });
    const cancel = document.createElement("button");
    cancel.className = "btn ghost";
    cancel.textContent = "取消";
    cancel.addEventListener("click", closeModal);
    openModal({ title: "提交版本", body, actions: [cancel, commit] });
  }
  
  // 显示版本历史
  async function showVersionHistory() {
    try {
      const resp = await fetch(`/api/doc/${docId}/version/log?branch=main&limit=50`);
      const data = await resp.json();
      
      const body = document.createElement("div");
      if (!data.versions || data.versions.length === 0) {
        body.innerHTML = '<div class="muted">暂无版本历史</div>';
      } else {
        body.innerHTML = `
          <div class="version-list">
            ${data.versions.map(v => `
              <div class="version-item ${v.is_current ? 'current' : ''}" data-id="${v.version_id}">
                <div class="version-header">
                  <strong>${escapeHtml(v.message)}</strong>
                  ${v.is_current ? '<span class="badge">当前</span>' : ''}
                  ${v.tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('')}
                </div>
                <div class="version-meta">
                  <span>${v.author}</span> · 
                  <span>${new Date(v.timestamp * 1000).toLocaleString()}</span> · 
                  <span class="version-id">${v.version_id.slice(0, 7)}</span>
                </div>
                <div class="version-actions">
                  <button class="btn-checkout" data-id="${v.version_id}">切换</button>
                  <button class="btn-diff" data-id="${v.version_id}">对比</button>
                  <button class="btn-tag" data-id="${v.version_id}">标签</button>
                </div>
              </div>
            `).join('')}
          </div>
        `;
        
        // 绑定切换事件
        body.querySelectorAll(".btn-checkout").forEach(btn => {
          btn.addEventListener("click", async () => {
            const vid = btn.getAttribute("data-id");
            if (confirm(`确定切换到版本 ${vid.slice(0, 7)} 吗？当前未保存的修改将丢失。`)) {
              try {
                const resp = await postJson(`/api/doc/${docId}/version/checkout`, { version_id: vid });
                el("source").value = resp.doc_text;
                renderPreviewFromSource(resp.doc_text);
                toast(`已切换到版本 ${vid.slice(0, 7)}`, "ok");
                closeModal();
              } catch (e) {
                toast(`切换失败：${e.message}`, "bad");
              }
            }
          });
        });
        
        // 绑定对比事件
        body.querySelectorAll(".btn-diff").forEach(btn => {
          btn.addEventListener("click", async () => {
            const vid = btn.getAttribute("data-id");
            if (data.versions.length < 2) {
              toast("至少需要2个版本才能对比", "");
              return;
            }
            const current = data.versions.find(v => v.is_current);
            if (!current || current.version_id === vid) {
              toast("请选择不同的版本进行对比", "");
              return;
            }
            showVersionDiff(current.version_id, vid);
          });
        });
        
        // 绑定标签事件
        body.querySelectorAll(".btn-tag").forEach(btn => {
          btn.addEventListener("click", () => {
            const vid = btn.getAttribute("data-id");
            addVersionTag(vid);
          });
        });
      }
      
      const close = document.createElement("button");
      close.className = "btn ghost";
      close.textContent = "关闭";
      close.addEventListener("click", closeModal);
      
      const commitBtn = document.createElement("button");
      commitBtn.className = "btn primary";
      commitBtn.textContent = "提交新版本";
      commitBtn.addEventListener("click", () => {
        closeModal();
        manualCommitVersion();
      });
      
      openModal({ title: "版本历史", body, actions: [close, commitBtn] });
    } catch (e) {
      toast(`加载失败：${e.message}`, "bad");
    }
  }
  
  // 显示版本对比
  async function showVersionDiff(from, to) {
    try {
      const resp = await fetch(`/api/doc/${docId}/version/diff?from_version=${from}&to_version=${to}`);
      const data = await resp.json();
      
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="diff-header">
          <div><strong>From:</strong> ${escapeHtml(data.from_message)} (${from.slice(0, 7)})</div>
          <div><strong>To:</strong> ${escapeHtml(data.to_message)} (${to.slice(0, 7)})</div>
        </div>
        <pre class="diff-content">${data.diff.map(line => escapeHtml(line)).join('\n')}</pre>
      `;
      
      const close = document.createElement("button");
      close.className = "btn primary";
      close.textContent = "关闭";
      close.addEventListener("click", closeModal);
      
      openModal({ title: "版本对比", body, actions: [close] });
    } catch (e) {
      toast(`对比失败：${e.message}`, "bad");
    }
  }
  
  // 添加标签
  async function addVersionTag(versionId) {
    const body = document.createElement("div");
    body.innerHTML = `<label>标签名：<br/><input type="text" id="tagInput" class="input" placeholder="如: stable, v1.0" style="width: 100%;" /></label>`;
    
    const add = document.createElement("button");
    add.className = "btn primary";
    add.textContent = "添加";
    add.addEventListener("click", async () => {
      const tag = el("tagInput").value.trim();
      if (!tag) {
        toast("请输入标签名", "");
        return;
      }
      try {
        await postJson(`/api/doc/${docId}/version/tag`, { version_id: versionId, tag });
        toast(`已添加标签"${tag}"`, "ok");
        closeModal();
      } catch (e) {
        toast(`添加失败：${e.message}`, "bad");
      }
    });
    
    const cancel = document.createElement("button");
    cancel.className = "btn ghost";
    cancel.textContent = "取消";
    cancel.addEventListener("click", closeModal);
    
    openModal({ title: "添加标签", body, actions: [cancel, add] });
  }
  
  // 监听文本变化，触发自动提交
  el("source")?.addEventListener("input", () => {
    scheduleAutoCommit();
  });
  
  // 绑定版本历史按钮
  el("btnVersionHistory")?.addEventListener("click", showVersionHistory);
  
  // 绑定Undo/Redo按钮和快捷键
  el("btnUndo")?.addEventListener("click", performUndo);
  el("btnRedo")?.addEventListener("click", performRedo);
  
  // === 版本树功能结束 ===

  // === Undo/Redo撤销重做功能 ===
  
  let undoStack = [];
  let redoStack = [];
  let lastSavedText = "";
  const MAX_UNDO_STACK = 100;
  
  function pushUndoState(text) {
    if (text === lastSavedText) return; // 去重
    undoStack.push(lastSavedText);
    if (undoStack.length > MAX_UNDO_STACK) {
      undoStack.shift();
    }
    redoStack = []; // 清空redo栈
    lastSavedText = text;
    updateUndoRedoButtons();
  }
  
  function performUndo() {
    if (undoStack.length === 0) {
      toast("无可撤销操作", "");
      return;
    }
    
    const current = el("source").value;
    redoStack.push(current);
    const previous = undoStack.pop();
    
    el("source").value = previous;
    lastSavedText = previous;
    el("source").dispatchEvent(new Event("input", { bubbles: true }));
    renderPreviewFromSource(previous);
    updateUndoRedoButtons();
  }
  
  function performRedo() {
    if (redoStack.length === 0) {
      toast("无可重做操作", "");
      return;
    }
    
    const next = redoStack.pop();
    undoStack.push(lastSavedText);
    
    el("source").value = next;
    lastSavedText = next;
    el("source").dispatchEvent(new Event("input", { bubbles: true }));
    renderPreviewFromSource(next);
    updateUndoRedoButtons();
  }
  
  function updateUndoRedoButtons() {
    const undoBtn = el("btnUndo");
    const redoBtn = el("btnRedo");
    if (undoBtn) undoBtn.disabled = undoStack.length === 0;
    if (redoBtn) redoBtn.disabled = redoStack.length === 0;
  }
  
  // 监听文本变化，记录undo状态
  let undoTimer = null;
  el("source")?.addEventListener("input", (e) => {
    if (undoTimer) clearTimeout(undoTimer);
    undoTimer = setTimeout(() => {
      pushUndoState(e.target.value);
    }, 500); // 500ms防抖
  });
  
  // 初始化undo状态
  if (el("source")) {
    lastSavedText = el("source").value;
  }
  
  // === Undo/Redo功能结束 ===
  
  // === 多格式导出功能 ===
  
  function showExportFormatsModal() {
    const formats = [
      { id: 'md', name: 'Markdown', desc: '纯文本格式，带YAML元数据，适合版本控制' },
      { id: 'html', name: 'HTML', desc: '网页格式，带样式，可在浏览器打开' },
      { id: 'tex', name: 'LaTeX', desc: '学术排版格式，可编译为PDF' },
      { id: 'txt', name: '纯文本', desc: '无格式文本，去除所有Markdown标记' },
      { id: 'docx', name: 'Word文档', desc: '当前默认格式' },
      { id: 'pdf', name: 'PDF', desc: '需安装LibreOffice' }
    ];
    
    const html = `
      <h3 style="margin-top:0">选择导出格式</h3>
      <div style="display:grid;gap:12px;margin-top:16px;">
        ${formats.map(fmt => `
          <div class="export-format-item" data-format="${fmt.id}" style="
            padding:12px;
            border:1px solid var(--border);
            border-radius:4px;
            cursor:pointer;
            transition:all 0.2s;
          ">
            <div style="font-weight:600;margin-bottom:4px;">${fmt.name}</div>
            <div style="font-size:0.9em;opacity:0.7;">${fmt.desc}</div>
          </div>
        `).join('')}
      </div>
    `;
    
    openModal(html);
    
    // 绑定点击事件
    document.querySelectorAll('.export-format-item').forEach(item => {
      item.addEventListener('mouseenter', () => {
        item.style.borderColor = 'var(--accent)';
        item.style.background = 'var(--bg-3)';
      });
      item.addEventListener('mouseleave', () => {
        item.style.borderColor = 'var(--border)';
        item.style.background = 'var(--bg-2)';
      });
      item.addEventListener('click', () => {
        const format = item.getAttribute('data-format');
        downloadFormat(format);
        closeModal();
      });
    });
  }
  
  function downloadFormat(format) {
    let url;
    if (format === 'docx') {
      url = `/download/${docId}.docx`;
    } else if (format === 'pdf') {
      url = `/download/${docId}.pdf`;
    } else {
      url = `/export/${docId}/${format}`;
    }
    
    // 创建隐藏的a标签触发下载
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    toast(`正在导出 ${format.toUpperCase()} 格式...`, "ok");
  }
  
  el("btnExportMore")?.addEventListener("click", showExportFormatsModal);
  
  // === 多格式导出功能结束 ===
  
  // === 图表和公式渲染功能 ===
  
  // 初始化Mermaid
  if (typeof mermaid !== 'undefined') {
    mermaid.initialize({ 
      startOnLoad: false, 
      theme: 'default',
      securityLevel: 'loose'
    });
  }
  
  // 初始化MathJax
  if (window.MathJax) {
    MathJax.typesetPromise = MathJax.typesetPromise || (() => Promise.resolve());
  }
  
  function renderDiagramsAndFormulas(containerEl) {
    if (!containerEl) return;
    
    // 渲染Mermaid图表
    // 支持格式：```mermaid ... ``` 或 [[FIGURE:xxx]]内嵌mermaid代码
    const mermaidBlocks = containerEl.querySelectorAll('pre code.language-mermaid, .mermaid-diagram');
    if (mermaidBlocks.length > 0 && typeof mermaid !== 'undefined') {
      mermaidBlocks.forEach((block, idx) => {
        const code = block.textContent;
        const container = document.createElement('div');
        container.className = 'mermaid-container';
        container.style.textAlign = 'center';
        container.style.margin = '16px 0';
        
        const id = `mermaid-${Date.now()}-${idx}`;
        container.id = id;
        
        mermaid.render(id + '-svg', code).then(result => {
          container.innerHTML = result.svg;
        }).catch(err => {
          container.innerHTML = `<div style="color:red;padding:12px;border:1px dashed red;">
            Mermaid渲染失败：${err.message}
          </div>`;
        });
        
        block.parentElement.replaceWith(container);
      });
    }
    
    // 处理[[FIGURE:xxx]]占位符
    const figurePattern = /\[\[FIGURE:([^\]]+)\]\]/g;
    const textNodes = getAllTextNodes(containerEl);
    textNodes.forEach(node => {
      const text = node.textContent;
      if (figurePattern.test(text)) {
        const span = document.createElement('span');
        span.innerHTML = text.replace(figurePattern, (match, title) => {
          return `<div class="figure-placeholder" style="
            padding:24px;
            margin:16px 0;
            border:2px dashed var(--border);
            border-radius:4px;
            text-align:center;
            background:var(--bg-3);
          ">
            <div style="font-weight:600;margin-bottom:8px;">📊 图表占位符</div>
            <div style="opacity:0.7;">${title}</div>
            <button class="insert-diagram-btn" data-title="${title}" style="
              margin-top:12px;
              padding:6px 12px;
              background:var(--accent);
              color:white;
              border:none;
              border-radius:4px;
              cursor:pointer;
            ">插入Mermaid图表</button>
          </div>`;
        });
        node.parentElement.replaceChild(span, node);
      }
    });
    
    // 绑定插入Mermaid按钮
    containerEl.querySelectorAll('.insert-diagram-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const title = btn.getAttribute('data-title');
        showMermaidInsertModal(title);
      });
    });
    
    // 渲染LaTeX公式
    // 支持行内公式 $...$ 和块级公式 $$...$$
    if (window.MathJax) {
      MathJax.typesetPromise([containerEl]).catch(err => {
        console.warn('MathJax渲染失败:', err);
      });
    }
  }
  
  function getAllTextNodes(element) {
    const nodes = [];
    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_TEXT,
      null
    );
    let node;
    while (node = walker.nextNode()) {
      if (node.textContent.trim()) nodes.push(node);
    }
    return nodes;
  }
  
  function showMermaidInsertModal(title) {
    const templates = {
      'flowchart': `graph TD
    A[开始] --> B{判断}
    B -->|是| C[处理1]
    B -->|否| D[处理2]
    C --> E[结束]
    D --> E`,
      'sequence': `sequenceDiagram
    participant A as 用户
    participant B as 系统
    A->>B: 请求数据
    B-->>A: 返回结果`,
      'gantt': `gantt
    title 项目进度
    section 阶段1
    任务1 :a1, 2024-01-01, 7d
    任务2 :a2, after a1, 5d`,
      'pie': `pie
    title 分布图
    "类别A" : 45
    "类别B" : 30
    "类别C" : 25`
    };
    
    const html = `
      <h3 style="margin-top:0">插入Mermaid图表：${title}</h3>
      <div style="margin:16px 0;">
        <label style="display:block;margin-bottom:8px;font-weight:600;">选择模板：</label>
        <select id="mermaidTemplate" style="
          width:100%;
          padding:8px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
        ">
          <option value="flowchart">流程图</option>
          <option value="sequence">时序图</option>
          <option value="gantt">甘特图</option>
          <option value="pie">饼图</option>
        </select>
      </div>
      <div style="margin:16px 0;">
        <label style="display:block;margin-bottom:8px;font-weight:600;">Mermaid代码：</label>
        <textarea id="mermaidCode" rows="10" style="
          width:100%;
          padding:8px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
          font-family:monospace;
        ">${templates.flowchart}</textarea>
      </div>
      <div style="margin-top:16px;text-align:right;">
        <button class="btn ghost" onclick="closeModal()">取消</button>
        <button id="btnInsertMermaid" class="btn primary" style="margin-left:8px;">插入</button>
      </div>
    `;
    
    openModal(html);
    
    // 模板切换
    el("mermaidTemplate")?.addEventListener('change', (e) => {
      el("mermaidCode").value = templates[e.target.value];
    });
    
    // 插入
    el("btnInsertMermaid")?.addEventListener('click', () => {
      const code = el("mermaidCode").value.trim();
      if (!code) {
        toast("请输入Mermaid代码", "bad");
        return;
      }
      
      // 替换[[FIGURE:xxx]]为mermaid代码块
      const source = el("source").value;
      const updated = source.replace(
        new RegExp(`\\[\\[FIGURE:${title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\]\\]`),
        `\`\`\`mermaid\n${code}\n\`\`\``
      );
      
      el("source").value = updated;
      el("source").dispatchEvent(new Event("input", { bubbles: true }));
      renderPreviewFromSource(updated);
      closeModal();
      toast("Mermaid图表已插入", "ok");
    });
  }
  
  // === 图表和公式渲染功能结束 ===
  
  // === 智能内容建议功能 ===
  
  function analyzeDocumentIssues(text) {
    const issues = [];
    const lines = text.split('\n');
    
    // 1. 引用缺失检测
    const citationPattern = /\[@([a-zA-Z0-9_-]+)\]/g;
    const allCitations = new Set();
    let match;
    while ((match = citationPattern.exec(text)) !== null) {
      allCitations.add(match[1]);
    }
    
    // 检查是否有"参考文献"章节
    const hasRefSection = /^##?\s*(参考文献|References)/m.test(text);
    if (allCitations.size > 0 && !hasRefSection) {
      issues.push({
        type: 'missing-ref-section',
        severity: 'warning',
        message: `文档中有${allCitations.size}处引用标记，但缺少"参考文献"章节`,
        line: -1
      });
    }
    
    // 2. 观点/数据陈述缺乏引用
    const claimPatterns = [
      /研究(表明|显示|指出|发现|证明)/g,
      /根据(调查|统计|分析|研究)/g,
      /(数据|结果|实验)(表明|显示|证明)/g,
      /已(证明|验证|确认)/g
    ];
    
    lines.forEach((line, idx) => {
      if (line.trim().length < 10) return;
      if (/^##?#?\s+/.test(line)) return; // 跳过标题
      
      for (const pattern of claimPatterns) {
        if (pattern.test(line) && !citationPattern.test(line)) {
          issues.push({
            type: 'missing-citation',
            severity: 'suggestion',
            message: '此句陈述观点/数据，建议添加引用标记[@key]',
            line: idx + 1,
            lineText: line.substring(0, 60) + (line.length > 60 ? '...' : '')
          });
          break; // 每行只报一次
        }
      }
    });
    
    // 3. 连续空行检测
    for (let i = 0; i < lines.length - 2; i++) {
      if (!lines[i].trim() && !lines[i+1].trim() && !lines[i+2].trim()) {
        issues.push({
          type: 'excessive-newlines',
          severity: 'info',
          message: '存在连续3行以上空行，建议简化',
          line: i + 1
        });
        i += 2; // 跳过已检查的行
      }
    }
    
    // 4. 标题层级跳跃
    const headings = lines.map((line, idx) => {
      const m = line.match(/^(#{1,3})\s+(.+)/);
      if (m) return { level: m[1].length, text: m[2], line: idx + 1 };
      return null;
    }).filter(Boolean);
    
    for (let i = 1; i < headings.length; i++) {
      const prev = headings[i-1];
      const curr = headings[i];
      if (curr.level - prev.level > 1) {
        issues.push({
          type: 'heading-skip',
          severity: 'warning',
          message: `标题层级跳跃：从${prev.level}级跳到${curr.level}级`,
          line: curr.line,
          lineText: curr.text
        });
      }
    }
    
    // 5. [待补充]标记检测
    const todoPattern = /\[待补充\]/g;
    let todoCount = 0;
    let todoMatch;
    while ((todoMatch = todoPattern.exec(text)) !== null) {
      todoCount++;
    }
    if (todoCount > 0) {
      issues.push({
        type: 'todo-markers',
        severity: 'info',
        message: `文档中有${todoCount}处待补充标记`,
        line: -1
      });
    }
    
    // 6. 被动语态检测（简化版）
    const passivePatterns = [
      /被(认为|视为|证明|发现|观察到)/g,
      /得到了/g,
      /已被/g
    ];
    
    lines.forEach((line, idx) => {
      if (line.trim().length < 10) return;
      for (const pattern of passivePatterns) {
        if (pattern.test(line)) {
          issues.push({
            type: 'passive-voice',
            severity: 'suggestion',
            message: '建议使用主动语态以增强表达力',
            line: idx + 1,
            lineText: line.substring(0, 60) + (line.length > 60 ? '...' : '')
          });
          break;
        }
      }
    });
    
    return issues;
  }
  
  function showContentSuggestionsModal(text) {
    const issues = analyzeDocumentIssues(text);
    
    if (issues.length === 0) {
      toast("文档质量良好，未发现明显问题", "ok");
      return;
    }
    
    const grouped = {
      warning: issues.filter(i => i.severity === 'warning'),
      suggestion: issues.filter(i => i.severity === 'suggestion'),
      info: issues.filter(i => i.severity === 'info')
    };
    
    const html = `
      <h3 style="margin-top:0">智能内容建议（共${issues.length}条）</h3>
      <div style="max-height:500px;overflow-y:auto;">
        ${grouped.warning.length > 0 ? `
          <div style="margin-bottom:16px;">
            <h4 style="color:#f39c12;margin-bottom:8px;">⚠️ 警告（${grouped.warning.length}）</h4>
            ${grouped.warning.map(issue => `
              <div style="
                padding:10px;
                margin-bottom:8px;
                border-left:3px solid #f39c12;
                background:var(--bg-3);
                border-radius:4px;
              ">
                <div style="font-weight:600;margin-bottom:4px;">${issue.message}</div>
                ${issue.line > 0 ? `<div style="font-size:0.9em;opacity:0.7;">第${issue.line}行</div>` : ''}
                ${issue.lineText ? `<div style="font-size:0.9em;font-family:monospace;opacity:0.7;margin-top:4px;">${escapeHtml(issue.lineText)}</div>` : ''}
              </div>
            `).join('')}
          </div>
        ` : ''}
        
        ${grouped.suggestion.length > 0 ? `
          <div style="margin-bottom:16px;">
            <h4 style="color:#3498db;margin-bottom:8px;">💡 建议（${grouped.suggestion.length}）</h4>
            ${grouped.suggestion.slice(0, 10).map(issue => `
              <div style="
                padding:10px;
                margin-bottom:8px;
                border-left:3px solid #3498db;
                background:var(--bg-3);
                border-radius:4px;
              ">
                <div style="font-weight:600;margin-bottom:4px;">${issue.message}</div>
                ${issue.line > 0 ? `<div style="font-size:0.9em;opacity:0.7;">第${issue.line}行</div>` : ''}
                ${issue.lineText ? `<div style="font-size:0.9em;font-family:monospace;opacity:0.7;margin-top:4px;">${escapeHtml(issue.lineText)}</div>` : ''}
              </div>
            `).join('')}
            ${grouped.suggestion.length > 10 ? `<div style="opacity:0.7;margin-top:8px;">...还有${grouped.suggestion.length - 10}条建议</div>` : ''}
          </div>
        ` : ''}
        
        ${grouped.info.length > 0 ? `
          <div style="margin-bottom:16px;">
            <h4 style="color:#95a5a6;margin-bottom:8px;">ℹ️ 提示（${grouped.info.length}）</h4>
            ${grouped.info.map(issue => `
              <div style="
                padding:10px;
                margin-bottom:8px;
                border-left:3px solid #95a5a6;
                background:var(--bg-3);
                border-radius:4px;
              ">
                <div style="font-weight:600;">${issue.message}</div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
      <div style="margin-top:16px;text-align:right;">
        <button class="btn primary" onclick="closeModal()">关闭</button>
      </div>
    `;
    
    openModal(html);
  }
  
  // 增强原有check-issues功能
  const originalCheckIssues = document.querySelector('[data-action="check-issues"]');
  if (originalCheckIssues) {
    originalCheckIssues.addEventListener('click', () => {
      const text = el("source").value || "";
      showContentSuggestionsModal(text);
    });
  }
  
  // === 智能内容建议功能结束 ===
  
  // === 版本树可视化（Mermaid分支图）===
  
  async function showVersionTreeVisualization() {
    try {
      const resp = await fetch(`/api/doc/${docId}/version/tree`);
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || '获取版本树失败');
      
      const { nodes, edges } = data;
      if (nodes.length === 0) {
        toast("版本树为空，先提交版本吧", "");
        return;
      }
      
      // 生成Mermaid图
      let mermaidCode = 'graph TD\n';
      nodes.forEach(node => {
        const label = `${node.message.substring(0, 15)}\\n${new Date(node.timestamp * 1000).toLocaleString('zh-CN').substring(5)}`;
        const style = node.is_current ? ':::current' : '';
        mermaidCode += `  ${node.version_id}["${label}"]${style}\n`;
      });
      
      edges.forEach(edge => {
        mermaidCode += `  ${edge.from} --> ${edge.to}\n`;
      });
      
      mermaidCode += '\n  classDef current fill:#3498db,stroke:#2980b9,color:#fff\n';
      
      const html = `
        <h3 style="margin-top:0">版本树可视化</h3>
        <div id="versionTreeGraph" style="text-align:center;padding:20px;"></div>
        <div style="margin-top:16px;text-align:right;">
          <button class="btn ghost" onclick="closeModal()">关闭</button>
        </div>
      `;
      
      openModal(html);
      
      // 渲染Mermaid
      if (typeof mermaid !== 'undefined') {
        mermaid.render('version-tree-svg', mermaidCode).then(result => {
          document.getElementById('versionTreeGraph').innerHTML = result.svg;
        }).catch(err => {
          document.getElementById('versionTreeGraph').innerHTML = `<div style="color:red;">渲染失败：${err.message}</div>`;
        });
      } else {
        document.getElementById('versionTreeGraph').innerHTML = '<div style="color:red;">Mermaid库未加载</div>';
      }
    } catch (err) {
      toast(`版本树可视化失败：${err.message}`, "bad");
    }
  }
  
  // 在版本历史modal中添加"查看分支图"按钮（修改showVersionHistory函数）
  
  // === 版本树可视化结束 ===
  
  // === 模板市场功能 ===
  
  const templateLibrary = {
    '论文': [
      {
        name: '学术论文标准结构',
        content: `# [论文标题]

## 摘要

[待补充]

## 关键词

关键词1；关键词2；关键词3

## 1. 引言

### 1.1 研究背景

### 1.2 研究现状

### 1.3 研究内容

## 2. 相关工作

## 3. 方法

## 4. 实验

### 4.1 实验设置

### 4.2 实验结果

## 5. 讨论

## 6. 结论

## 参考文献

[1] ...`
      },
      {
        name: '毕业论文开题报告',
        content: `# [课题名称]

## 一、选题背景与意义

### （一）选题背景

### （二）研究意义

## 二、国内外研究现状

### （一）国外研究现状

### （二）国内研究现状

## 三、研究内容与方法

### （一）研究内容

### （二）研究方法

## 四、预期成果

## 五、进度安排

## 六、参考文献`
      }
    ],
    '报告': [
      {
        name: '项目设计报告',
        content: `# [项目名称]设计报告

## 1. 需求分析

### 1.1 业务需求

### 1.2 功能需求

### 1.3 非功能需求

## 2. 总体设计

### 2.1 系统架构

### 2.2 模块划分

## 3. 详细设计

## 4. 数据库设计

## 5. 测试方案

## 6. 总结`
      },
      {
        name: '实验报告',
        content: `# [实验名称]

## 一、实验目的

## 二、实验原理

## 三、实验步骤

## 四、实验数据

## 五、数据分析

## 六、实验结论

## 七、思考题`
      }
    ],
    '商业': [
      {
        name: '商业计划书',
        content: `# [项目名称]商业计划书

## 执行摘要

## 一、项目概述

## 二、市场分析

### 2.1 目标市场

### 2.2 竞争分析

### 2.3 市场机会

## 三、产品与服务

## 四、营销策略

## 五、运营计划

## 六、财务预测

## 七、风险分析

## 八、团队介绍`
      },
      {
        name: '年度工作总结',
        content: `# {{年份}}年度工作总结

## 一、工作概述

## 二、主要工作成果

### 2.1 完成项目

### 2.2 关键数据

## 三、不足与改进

## 四、明年计划

## 五、个人成长`
      }
    ]
  };
  
  function showTemplateMarket() {
    const categories = Object.keys(templateLibrary);
    
    const html = `
      <h3 style="margin-top:0">模板市场</h3>
      <div style="margin:16px 0;">
        <select id="templateCategory" style="
          width:100%;
          padding:8px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
        ">
          ${categories.map(cat => `<option value="${cat}">${cat}</option>`).join('')}
        </select>
      </div>
      <div id="templateList" style="max-height:400px;overflow-y:auto;"></div>
      <div style="margin-top:16px;text-align:right;">
        <button class="btn ghost" onclick="closeModal()">取消</button>
      </div>
    `;
    
    openModal(html);
    
    function renderTemplateList(category) {
      const templates = templateLibrary[category] || [];
      const listHtml = templates.map((tmpl, idx) => `
        <div class="template-item" data-idx="${idx}" style="
          padding:12px;
          margin-bottom:8px;
          border:1px solid var(--border);
          border-radius:4px;
          cursor:pointer;
          transition:all 0.2s;
        ">
          <div style="font-weight:600;margin-bottom:4px;">${tmpl.name}</div>
          <div style="font-size:0.9em;opacity:0.7;">${tmpl.content.split('\n').slice(0, 3).join(' ')}</div>
        </div>
      `).join('');
      
      el("templateList").innerHTML = listHtml;
      
      document.querySelectorAll('.template-item').forEach(item => {
        item.addEventListener('mouseenter', () => {
          item.style.borderColor = 'var(--accent)';
          item.style.background = 'var(--bg-3)';
        });
        item.addEventListener('mouseleave', () => {
          item.style.borderColor = 'var(--border)';
          item.style.background = 'transparent';
        });
        item.addEventListener('click', () => {
          const idx = parseInt(item.getAttribute('data-idx'));
          const category = el("templateCategory").value;
          const tmpl = templateLibrary[category][idx];
          applyTemplate(tmpl);
        });
      });
    }
    
    function applyTemplate(tmpl) {
      // 替换变量{{年份}}等
      let content = tmpl.content;
      content = content.replace(/\{\{年份\}\}/g, new Date().getFullYear());
      content = content.replace(/\{\{作者\}\}/g, 'user');
      content = content.replace(/\{\{日期\}\}/g, new Date().toLocaleDateString('zh-CN'));
      
      el("source").value = content;
      el("source").dispatchEvent(new Event("input", { bubbles: true }));
      renderPreviewFromSource(content);
      closeModal();
      toast(`已应用模板：${tmpl.name}`, "ok");
    }
    
    renderTemplateList(categories[0]);
    
    el("templateCategory")?.addEventListener('change', (e) => {
      renderTemplateList(e.target.value);
    });
  }
  
  // 绑定工具栏按钮
  document.querySelector('[data-action="insert-template"]')?.addEventListener('click', showTemplateMarket);
  
  // === 模板市场功能结束 ===
  
  // === 快捷键自定义面板 ===
  
  const defaultKeyBindings = {
    'save': 'Ctrl+S',
    'undo': 'Ctrl+Z',
    'redo': 'Ctrl+Y',
    'bold': 'Ctrl+B',
    'italic': 'Ctrl+I',
    'find': 'Ctrl+F',
    'generate': 'Ctrl+Enter'
  };
  
  let customKeyBindings = {...defaultKeyBindings};
  
  function showKeyBindingsPanel() {
    const actions = Object.keys(defaultKeyBindings);
    
    const html = `
      <h3 style="margin-top:0">快捷键设置</h3>
      <div style="max-height:400px;overflow-y:auto;">
        ${actions.map(action => `
          <div style="
            display:flex;
            align-items:center;
            justify-content:space-between;
            padding:12px;
            margin-bottom:8px;
            border:1px solid var(--border);
            border-radius:4px;
          ">
            <div style="flex:1;">
              <div style="font-weight:600;margin-bottom:4px;">${action}</div>
              <div style="font-size:0.9em;opacity:0.7;">默认：${defaultKeyBindings[action]}</div>
            </div>
            <input 
              type="text" 
              class="keybinding-input" 
              data-action="${action}"
              value="${customKeyBindings[action]}"
              placeholder="按下快捷键..."
              readonly
              style="
                width:120px;
                padding:6px 12px;
                border:1px solid var(--border);
                border-radius:4px;
                background:var(--bg-3);
                text-align:center;
                cursor:pointer;
              "
            />
          </div>
        `).join('')}
      </div>
      <div style="margin-top:16px;text-align:right;">
        <button id="btnResetKeys" class="btn ghost">恢复默认</button>
        <button id="btnSaveKeys" class="btn primary" style="margin-left:8px;">保存</button>
      </div>
    `;
    
    openModal(html);
    
    // 绑定快捷键录制
    document.querySelectorAll('.keybinding-input').forEach(input => {
      input.addEventListener('click', () => {
        input.style.borderColor = 'var(--accent)';
        input.value = '按下快捷键...';
      });
      
      input.addEventListener('keydown', (e) => {
        e.preventDefault();
        const parts = [];
        if (e.ctrlKey || e.metaKey) parts.push('Ctrl');
        if (e.shiftKey) parts.push('Shift');
        if (e.altKey) parts.push('Alt');
        if (e.key && !['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
          parts.push(e.key.toUpperCase());
        }
        
        if (parts.length > 1) {
          input.value = parts.join('+');
          input.style.borderColor = 'var(--border)';
        }
      });
    });
    
    el("btnResetKeys")?.addEventListener('click', () => {
      customKeyBindings = {...defaultKeyBindings};
      document.querySelectorAll('.keybinding-input').forEach(input => {
        const action = input.getAttribute('data-action');
        input.value = defaultKeyBindings[action];
      });
      toast("已恢复默认快捷键", "ok");
    });
    
    el("btnSaveKeys")?.addEventListener('click', () => {
      document.querySelectorAll('.keybinding-input').forEach(input => {
        const action = input.getAttribute('data-action');
        customKeyBindings[action] = input.value;
      });
      
      // 保存到localStorage
      localStorage.setItem('keyBindings', JSON.stringify(customKeyBindings));
      closeModal();
      toast("快捷键设置已保存", "ok");
    });
  }
  
  // 加载用户设置的快捷键
  const savedKeys = localStorage.getItem('keyBindings');
  if (savedKeys) {
    try {
      customKeyBindings = JSON.parse(savedKeys);
    } catch (e) {
      console.warn('加载快捷键设置失败:', e);
    }
  }
  
  // === 快捷键自定义功能结束 ===
  
  // === 引用管理器集成（BibTeX/DOI）===
  
  function showCitationManager() {
    const html = `
      <h3 style="margin-top:0">引用管理器</h3>
      <div class="tabs" style="margin-bottom:16px;border-bottom:1px solid var(--border);">
        <button class="citation-tab active" data-tab="import" style="padding:8px 16px;border:none;background:transparent;cursor:pointer;">导入</button>
        <button class="citation-tab" data-tab="doi" style="padding:8px 16px;border:none;background:transparent;cursor:pointer;">DOI查询</button>
        <button class="citation-tab" data-tab="manual" style="padding:8px 16px;border:none;background:transparent;cursor:pointer;">手动添加</button>
      </div>
      <div id="citationImport" class="citation-panel">
        <label style="display:block;margin-bottom:8px;font-weight:600;">粘贴BibTeX条目：</label>
        <textarea id="bibtexInput" rows="10" style="
          width:100%;
          padding:8px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
          font-family:monospace;
        " placeholder="@article{key2024,
  title={Title},
  author={Author},
  journal={Journal},
  year={2024}
}"></textarea>
        <button id="btnParseBibtex" class="btn primary" style="margin-top:12px;width:100%;">解析并插入</button>
      </div>
      <div id="citationDOI" class="citation-panel hidden">
        <label style="display:block;margin-bottom:8px;font-weight:600;">输入DOI：</label>
        <input type="text" id="doiInput" placeholder="10.1000/xyz123" style="
          width:100%;
          padding:8px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
        " />
        <button id="btnFetchDOI" class="btn primary" style="margin-top:12px;width:100%;">查询元数据</button>
        <div id="doiResult" style="margin-top:16px;"></div>
      </div>
      <div id="citationManual" class="citation-panel hidden">
        <label style="display:block;margin-bottom:8px;font-weight:600;">引用键：</label>
        <input type="text" id="citeKey" placeholder="zhang2024" style="
          width:100%;
          padding:8px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
          margin-bottom:12px;
        " />
        <label style="display:block;margin-bottom:8px;font-weight:600;">完整引用信息：</label>
        <textarea id="citeInfo" rows="3" placeholder="张三, 李四. 论文标题[J]. 期刊名, 2024, 1(1): 1-10." style="
          width:100%;
          padding:8px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
        "></textarea>
        <button id="btnInsertCite" class="btn primary" style="margin-top:12px;width:100%;">插入引用</button>
      </div>
    `;
    
    openModal(html);
    
    // 标签切换
    document.querySelectorAll('.citation-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.citation-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        
        const targetTab = tab.getAttribute('data-tab');
        document.querySelectorAll('.citation-panel').forEach(panel => {
          panel.classList.toggle('hidden', !panel.id.includes(targetTab.charAt(0).toUpperCase() + targetTab.slice(1)));
        });
      });
    });
    
    // BibTeX解析
    el("btnParseBibtex")?.addEventListener('click', () => {
      const bibtex = el("bibtexInput").value.trim();
      if (!bibtex) {
        toast("请输入BibTeX条目", "bad");
        return;
      }
      
      // 简单解析BibTeX
      const keyMatch = bibtex.match(/@\w+\{([^,]+),/);
      if (!keyMatch) {
        toast("BibTeX格式错误", "bad");
        return;
      }
      
      const key = keyMatch[1].trim();
      
      // 插入到"参考文献"章节
      const source = el("source").value;
      let updated = source;
      
      if (!source.includes('## 参考文献')) {
        updated += '\n\n## 参考文献\n\n';
      }
      
      updated += `[${key}] ${bibtex}\n\n`;
      
      el("source").value = updated;
      el("source").dispatchEvent(new Event("input", { bubbles: true }));
      closeModal();
      toast(`已插入引用：${key}`, "ok");
    });
    
    // DOI查询（模拟）
    el("btnFetchDOI")?.addEventListener('click', async () => {
      const doi = el("doiInput").value.trim();
      if (!doi) {
        toast("请输入DOI", "bad");
        return;
      }
      
      el("doiResult").innerHTML = '<div style="text-align:center;padding:20px;">查询中...</div>';
      
      try {
        // 实际应用中应调用CrossRef API
        // const resp = await fetch(`https://api.crossref.org/works/${doi}`);
        // const data = await resp.json();
        
        // 模拟结果
        setTimeout(() => {
          el("doiResult").innerHTML = `
            <div style="padding:12px;border:1px solid var(--border);border-radius:4px;background:var(--bg-3);">
              <div style="font-weight:600;margin-bottom:8px;">模拟结果（实际应用需接入CrossRef API）</div>
              <div style="font-size:0.9em;opacity:0.7;margin-bottom:4px;">DOI: ${doi}</div>
              <button class="btn ghost" style="margin-top:8px;">插入引用</button>
            </div>
          `;
          toast("DOI查询功能需配置API密钥", "");
        }, 1000);
      } catch (err) {
        el("doiResult").innerHTML = `<div style="color:red;">查询失败：${err.message}</div>`;
      }
    });
    
    // 手动插入
    el("btnInsertCite")?.addEventListener('click', () => {
      const key = el("citeKey").value.trim();
      const info = el("citeInfo").value.trim();
      
      if (!key || !info) {
        toast("请填写完整信息", "bad");
        return;
      }
      
      const source = el("source").value;
      let updated = source;
      
      if (!source.includes('## 参考文献')) {
        updated += '\n\n## 参考文献\n\n';
      }
      
      updated += `[${key}] ${info}\n\n`;
      
      el("source").value = updated;
      el("source").dispatchEvent(new Event("input", { bubbles: true }));
      closeModal();
      toast(`已添加引用：${key}`, "ok");
    });
  }
  
  // === 引用管理器功能结束 ===
  
  // === 实时协作冲突检测 ===
  
  let lastKnownVersionId = null;
  let conflictCheckInterval = null;
  
  function startConflictDetection() {
    if (conflictCheckInterval) return;
    
    conflictCheckInterval = setInterval(async () => {
      try {
        const resp = await fetch(`/api/doc/${docId}/version/log?limit=1`);
        const data = await resp.json();
        
        if (data.ok && data.versions.length > 0) {
          const latestVersion = data.versions[0];
          
          if (lastKnownVersionId && latestVersion.version_id !== lastKnownVersionId) {
            // 检测到新版本，可能是并行编辑
            const branches = await checkParallelEdits();
            if (branches > 1) {
              showConflictWarning();
            }
          }
          
          lastKnownVersionId = latestVersion.version_id;
        }
      } catch (err) {
        console.warn('冲突检测失败:', err);
      }
    }, 30000); // 每30秒检查一次
  }
  
  async function checkParallelEdits() {
    try {
      const resp = await fetch(`/api/doc/${docId}/version/tree`);
      const data = await resp.json();
      
      if (!data.ok) return 0;
      
      // 查找有多个子节点的版本（分叉点）
      const childCounts = {};
      data.edges.forEach(edge => {
        childCounts[edge.from] = (childCounts[edge.from] || 0) + 1;
      });
      
      const forkPoints = Object.values(childCounts).filter(count => count > 1);
      return forkPoints.length;
    } catch (err) {
      return 0;
    }
  }
  
  function showConflictWarning() {
    const html = `
      <h3 style="margin-top:0;color:#f39c12;">⚠️ 检测到并行编辑</h3>
      <div style="padding:16px;border-left:4px solid #f39c12;background:var(--bg-3);margin-bottom:16px;">
        <div style="font-weight:600;margin-bottom:8px;">版本树出现分支</div>
        <div style="opacity:0.8;">可能有其他用户同时编辑了此文档，建议查看版本历史并合并更改。</div>
      </div>
      <div style="text-align:right;">
        <button class="btn ghost" onclick="closeModal()">稍后处理</button>
        <button class="btn primary" style="margin-left:8px;" onclick="showVersionHistory()">查看版本历史</button>
      </div>
    `;
    
    openModal(html);
  }
  
  // 启动冲突检测
  startConflictDetection();
  
  // === 实时协作冲突检测结束 ===
  
  // === 性能监控面板 ===
  
  const perfStats = {
    generateCount: 0,
    totalGenerateTime: 0,
    ragQueryCount: 0,
    totalRagTime: 0,
    versionCount: 0,
    tokenUsage: 0,
    startTime: Date.now()
  };
  
  function showPerformanceMonitor() {
    const uptime = Math.floor((Date.now() - perfStats.startTime) / 1000);
    const avgGenTime = perfStats.generateCount > 0 ? (perfStats.totalGenerateTime / perfStats.generateCount).toFixed(1) : 0;
    const avgRagTime = perfStats.ragQueryCount > 0 ? (perfStats.totalRagTime / perfStats.ragQueryCount).toFixed(1) : 0;
    
    const html = `
      <h3 style="margin-top:0">性能监控</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
        <div style="padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-3);">
          <div style="font-size:2em;font-weight:700;color:var(--accent);">${perfStats.generateCount}</div>
          <div style="opacity:0.7;margin-top:4px;">生成次数</div>
        </div>
        <div style="padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-3);">
          <div style="font-size:2em;font-weight:700;color:var(--accent);">${avgGenTime}s</div>
          <div style="opacity:0.7;margin-top:4px;">平均生成速度</div>
        </div>
        <div style="padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-3);">
          <div style="font-size:2em;font-weight:700;color:var(--accent);">${perfStats.ragQueryCount}</div>
          <div style="opacity:0.7;margin-top:4px;">RAG检索次数</div>
        </div>
        <div style="padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-3);">
          <div style="font-size:2em;font-weight:700;color:var(--accent);">${perfStats.versionCount}</div>
          <div style="opacity:0.7;margin-top:4px;">版本提交数</div>
        </div>
      </div>
      <div style="padding:16px;border:1px solid var(--border);border-radius:8px;background:var(--bg-3);margin-bottom:16px;">
        <div style="font-weight:600;margin-bottom:12px;">系统状态</div>
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
          <span>运行时间</span>
          <span>${Math.floor(uptime / 60)}分${uptime % 60}秒</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
          <span>Token消耗（估算）</span>
          <span>${perfStats.tokenUsage.toLocaleString()}</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span>内存占用（估算）</span>
          <span>${(perfStats.versionCount * 0.5).toFixed(1)} MB</span>
        </div>
      </div>
      <div style="text-align:right;">
        <button class="btn ghost" onclick="closeModal()">关闭</button>
        <button class="btn primary" style="margin-left:8px;" onclick="location.reload()">重置统计</button>
      </div>
    `;
    
    openModal(html);
  }
  
  // 拦截生成事件来统计
  const originalGenerate = el("btnGenerate");
  if (originalGenerate) {
    originalGenerate.addEventListener('click', () => {
      const startTime = Date.now();
      perfStats.generateCount++;
      
      // 估算耗时（实际应用需要监听SSE流结束）
      setTimeout(() => {
        perfStats.totalGenerateTime += (Date.now() - startTime) / 1000;
        perfStats.tokenUsage += 1500; // 估算值
      }, 5000);
    });
  }
  
  // === 性能监控功能结束 ===
  
  // === 绑定所有新增功能的入口 ===
  
  el("btnSettings")?.addEventListener("click", () => {
    const html = `
      <h3 style="margin-top:0">设置</h3>
      <div style="display:grid;gap:12px;">
        <button class="setting-item" data-action="keybindings" style="
          padding:16px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
          text-align:left;
          cursor:pointer;
          transition:all 0.2s;
        ">
          <div style="font-weight:600;margin-bottom:4px;">⌨️ 快捷键设置</div>
          <div style="font-size:0.9em;opacity:0.7;">自定义快捷键绑定</div>
        </button>
        <button class="setting-item" data-action="citation" style="
          padding:16px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
          text-align:left;
          cursor:pointer;
          transition:all 0.2s;
        ">
          <div style="font-weight:600;margin-bottom:4px;">📚 引用管理器</div>
          <div style="font-size:0.9em;opacity:0.7;">导入BibTeX、查询DOI</div>
        </button>
        <button class="setting-item" data-action="template" style="
          padding:16px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
          text-align:left;
          cursor:pointer;
          transition:all 0.2s;
        ">
          <div style="font-weight:600;margin-bottom:4px;">📄 模板市场</div>
          <div style="font-size:0.9em;opacity:0.7;">浏览和应用文档模板</div>
        </button>
        <button class="setting-item" data-action="versionTree" style="
          padding:16px;
          border:1px solid var(--border);
          border-radius:4px;
          background:var(--bg-2);
          text-align:left;
          cursor:pointer;
          transition:all 0.2s;
        ">
          <div style="font-weight:600;margin-bottom:4px;">🌳 版本树可视化</div>
          <div style="font-size:0.9em;opacity:0.7;">查看Git-style分支图</div>
        </button>
      </div>
    `;
    
    openModal(html);
    
    document.querySelectorAll('.setting-item').forEach(item => {
      item.addEventListener('mouseenter', () => {
        item.style.borderColor = 'var(--accent)';
        item.style.background = 'var(--bg-3)';
      });
      item.addEventListener('mouseleave', () => {
        item.style.borderColor = 'var(--border)';
        item.style.background = 'var(--bg-2)';
      });
      item.addEventListener('click', () => {
        const action = item.getAttribute('data-action');
        closeModal();
        
        if (action === 'keybindings') showKeyBindingsPanel();
        else if (action === 'citation') showCitationManager();
        else if (action === 'template') showTemplateMarket();
        else if (action === 'versionTree') showVersionTreeVisualization();
      });
    });
  });
  
  el("btnPerf")?.addEventListener("click", showPerformanceMonitor);
  
  // === 功能入口绑定结束 ===

  const templateFile = el("templateFile");
  if (templateFile) {
    templateFile.addEventListener("change", async () => {
      const file = templateFile.files && templateFile.files[0];
      if (!file) return;
      try {
        setStatus("上传模板中…");
        const form = new FormData();
        form.append("file", file);
        const resp = await fetch(`/api/doc/${docId}/template`, { method: "POST", body: form });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        toast("模板已加载", "ok");
        el("templateInfo").textContent = `已加载模板：${data.template_name}${(data.required_h2 || []).length ? " · 章节：" + data.required_h2.join(" / ") : ""}`;
        setStatus("就绪", "ok");
      } catch (e) {
        toast(`模板上传失败：${e.message}`, "bad");
        setStatus("模板失败", "bad");
      } finally {
        templateFile.value = "";
      }
    });
  }

  function parseSseBlock(block) {
    const lines = String(block || "").replace(/\r/g, "").split("\n");
    let event = "message";
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice("event:".length).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trim());
    }
    const dataText = dataLines.join("\n");
    let data = {};
    try {
      data = dataText ? JSON.parse(dataText) : {};
    } catch {
      data = { raw: dataText };
    }
    return { event, data };
  }

  async function streamSsePost(url, payload, handlers, signal) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
    if (!resp.ok) throw new Error(await resp.text());
    if (!resp.body) throw new Error("当前环境不支持流式输出");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx = buf.indexOf("\n\n");
      while (idx >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        if (block.trim()) {
          const { event, data } = parseSseBlock(block);
          handlers(event, data);
        }
        idx = buf.indexOf("\n\n");
      }
    }
  }

  function escapeRe(s) {
    return String(s || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function ensureSkeletonInText(text, title, sections) {
    let t = String(text || "").replace(/\r/g, "");
    const hasH1 = /^#\s+/m.test(t);
    if (!hasH1) t = `# ${title || "自动生成文档"}\n\n` + t.trimStart();
    for (const s of sections || []) {
      const re = new RegExp(`^##\\s+${escapeRe(s)}\\s*$`, "m");
      if (!re.test(t)) t = (t.trimEnd() + "\n\n## " + s + "\n\n").replace(/\n{4,}/g, "\n\n");
    }
    return t;
  }

  function computeSectionRanges(text) {
    const src = String(text || "").replace(/\r/g, "");
    const lines = src.split("\n");
    const offsets = [];
    let off = 0;
    for (const line of lines) {
      offsets.push(off);
      off += line.length + 1;
    }
    const headings = [];
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.startsWith("## ")) headings.push({ name: line.slice(3).trim(), lineIndex: i, start: offsets[i], lineText: line });
    }
    const ranges = new Map();
    for (let k = 0; k < headings.length; k++) {
      const h = headings[k];
      const next = headings[k + 1];
      const contentStart = h.start + h.lineText.length + 1;
      const contentEnd = next ? next.start : src.length;
      ranges.set(h.name, { contentStart, contentEnd });
    }
    return { src, ranges };
  }

  function insertTextAt(textarea, index, insertText) {
    const v = textarea.value;
    const selStart = textarea.selectionStart || 0;
    const selEnd = textarea.selectionEnd || 0;
    textarea.value = v.slice(0, index) + insertText + v.slice(index);
    const delta = insertText.length;
    const nextStart = index <= selStart ? selStart + delta : selStart;
    const nextEnd = index <= selEnd ? selEnd + delta : selEnd;
    textarea.setSelectionRange(nextStart, nextEnd);
  }

  function appendDeltaToSection(section, delta) {
    const ta = el("source");
    if (!ta || !section || !delta) return;
    let t = ta.value.replace(/\r/g, "");
    const ensured = ensureSkeletonInText(t, "", [section]);
    if (ensured !== t) {
      ta.value = ensured;
      t = ensured;
    }
    const { src, ranges } = computeSectionRanges(t);
    const r = ranges.get(section);
    if (!r) return;
    let ins = String(delta);
    const insertion = r.contentEnd;
    if (insertion > 0 && src[insertion - 1] !== "\n" && !ins.startsWith("\n")) ins = "\n" + ins;
    insertTextAt(ta, insertion, ins);
  }

  function stripBodyLen(text) {
    const s = String(text || "")
      .replace(/\r/g, "")
      .replace(/^#{1,3}\s+.*$/gm, "")
      .replace(/\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]/gi, "")
      .trim();
    return s.length;
  }

  let aborter = null;

  const btnStop = el("btnStop");
  if (btnStop) {
    btnStop.addEventListener("click", () => {
      if (aborter) aborter.abort();
    });
  }

  const btnGenerate = el("btnGenerate");
  if (btnGenerate) {
    btnGenerate.addEventListener("click", async () => {
    const inst = String(el("instruction").value || "").trim();
    if (!inst) {
      const body = document.createElement("div");
      body.innerHTML = `<div class="muted">请输入你的要求后再开始生成。</div>`;
      const ok = document.createElement("button");
      ok.className = "btn primary";
      ok.textContent = "知道了";
      ok.type = "button";
      ok.addEventListener("click", closeModal);
      openModal({ title: "缺少要求", body, actions: [ok] });
      return;
    }

    const okSettings = await ensureSettingsBeforeGenerate();
    if (!okSettings) return;

    btnGenerate.disabled = true;
    btnStop.disabled = false;
    problemsBox.classList.add("hidden");
    problemsBox.textContent = "";
    setStatus("生成中…");
    setGraphState("PLAN");

    // 自动切换到预览标签页，让用户实时看到生成内容
    setActiveTab("preview");

    generating = true;
    userEditedDuringGeneration = false;

    aborter = new AbortController();

    const pending = new Map();
    let flushScheduled = false;
    let lastFlushTime = 0;
    const MIN_FLUSH_INTERVAL = 50; // 降低到50ms，提升实时性

    const flush = () => {
      flushScheduled = false;
      lastFlushTime = Date.now();

      for (const [sec, text] of pending.entries()) {
        appendDeltaToSection(sec, text);
      }
      pending.clear();
      updateWordCount(el("source").value);

      // 实时更新预览区
      renderPreviewFromSource(el("source").value);
    };

    const scheduleFlush = () => {
      if (flushScheduled) return;

      const now = Date.now();
      const timeSinceLastFlush = now - lastFlushTime;

      // 如果距离上次flush超过MIN_FLUSH_INTERVAL，立即flush
      if (timeSinceLastFlush >= MIN_FLUSH_INTERVAL) {
        flush();
      } else {
        // 否则延迟到MIN_FLUSH_INTERVAL后
        flushScheduled = true;
        setTimeout(flush, MIN_FLUSH_INTERVAL - timeSinceLastFlush);
      }
    };

    try {
      await streamSsePost(
        `/api/doc/${docId}/generate/stream`,
        { instruction: inst, text: el("source").value || "" },
         (event, data) => {
           if (event === "state") {
             setGraphState(String(data.name || ""));
             return;
           }
           if (event === "delta") {
             // optional status text from backend; do not touch document
             return;
           }
           if (event === "targets") {
             return;
           }
           if (event === "plan") {
             const title = String(data.title || "自动生成文档");
             const sections = Array.isArray(data.sections) ? data.sections.map((x) => String(x)) : [];
             const next = ensureSkeletonInText(el("source").value || "", title, sections);
             if (next !== el("source").value) {
               el("source").value = next;
               updateWordCount(next);
               renderPreviewFromSource(next);
             }
             return;
           }
           if (event === "section") {
             const sec = String(data.section || "");
             const phase = String(data.phase || "");
             if (phase === "start") {
               const title = String(data.title || "");
               if (title) setStatus("正在写作：" + title);
             } else if (phase === "delta") {
               const delta = String(data.delta || "");
               const prev = String(pending.get(sec) || "");
               pending.set(sec, prev + delta);
               scheduleFlush();
             }
             return;
           }
           if (event === "progress") {
             const percent = parseInt(data.percent) || 0;
             const current = parseInt(data.current) || 0;
             const total = parseInt(data.total) || 1;
             const elapsed = parseInt(data.elapsed_s) || 0;
                       
             const bar = el("progressBar");
             const fill = el("progressFill");
             const text = el("progressText");
                       
             if (bar) bar.classList.remove("hidden");
             if (fill) fill.style.width = `${percent}%`;
             if (text) {
               text.textContent = `${percent}% (${current}/${total})`;
               if (elapsed > 0) {
                 const eta = Math.round((elapsed / current) * (total - current));
                 if (eta > 0) text.textContent += ` ~${eta}s`;
               }
             }
             return;
           }
           if (event === "final") {
             flush();
             const txt = String(data.text || "");
             const probs = Array.isArray(data.problems) ? data.problems : [];

             const cur = String(el("source").value || "");
             const tooShort = stripBodyLen(txt) < stripBodyLen(cur) * 0.75;

             const applyFinal = () => {
               el("source").value = txt;
               updateWordCount(txt);
               renderPreviewFromSource(txt);
               if (probs.length) {
                 problemsBox.classList.remove("hidden");
                 problemsBox.textContent = "校验问题：\n- " + probs.join("\n- ");
                 setStatus("完成（需完善）", "bad");
               } else {
                 setStatus("完成", "ok");
               }
               showSystemNameModal();
             };

             if (userEditedDuringGeneration || tooShort) {
               const body = document.createElement("div");
               body.innerHTML =
                 `<div class="muted">修订稿已生成。${userEditedDuringGeneration ? "你在生成过程中修改了文档，系统不会自动覆盖。" : ""}${
                   tooShort ? "修订稿明显更短，建议先检查再覆盖。" : ""
                 }</div>`;
               const keep = document.createElement("button");
               keep.className = "btn ghost";
               keep.type = "button";
               keep.textContent = "保留当前";
               keep.addEventListener("click", () => {
                 closeModal();
                 if (probs.length) {
                   problemsBox.classList.remove("hidden");
                   problemsBox.textContent = "校验问题：\n- " + probs.join("\n- ");
                   setStatus("完成（保留本地）", "bad");
                 } else {
                   setStatus("完成（保留本地）", "ok");
                 }
                 showSystemNameModal();
               });
               const view = document.createElement("button");
               view.className = "btn ghost";
               view.type = "button";
               view.textContent = "查看修订稿";
               view.addEventListener("click", () => {
                 const ta = document.createElement("textarea");
                 ta.className = "input";
                 ta.style.minHeight = "260px";
                 ta.value = txt;
                 const ok = document.createElement("button");
                 ok.className = "btn primary";
                 ok.type = "button";
                 ok.textContent = "关闭";
                 ok.addEventListener("click", closeModal);
                 openModal({ title: "修订稿", body: ta, actions: [ok] });
               });
               const overwrite = document.createElement("button");
               overwrite.className = "btn primary";
               overwrite.type = "button";
               overwrite.textContent = "覆盖为修订稿";
               overwrite.addEventListener("click", () => {
                 closeModal();
                 applyFinal();
               });
               openModal({ title: "应用修订？", body, actions: [keep, view, overwrite] });
             } else {
               applyFinal();
             }
             return;
           }
           if (event === "error") {
             toast(String(data.message || "生成失败"), "bad");
             setStatus("生成失败", "bad");
           }
         },
        aborter.signal,
      );
    } catch (e) {
      if (String(e.name || "") === "AbortError") {
        toast("已停止生成", "");
        setStatus("已停止");
      } else {
        toast(`生成失败：${e.message}`, "bad");
        setStatus("生成失败", "bad");
      }
    } finally {
      btnGenerate.disabled = false;
      btnStop.disabled = true;
      aborter = null;
      generating = false;
      
      // 隐藏进度条
      const bar = el("progressBar");
      if (bar) bar.classList.add("hidden");
      
      saveSource().catch(err => console.warn('[final-save]', err));
    }
    });
  }

  // 文档列表
  const btnDocList = el("btnDocList");
  if (btnDocList) {
    btnDocList.addEventListener("click", async () => {
      try {
        const resp = await fetch("/api/docs/list");
        const data = await resp.json();
        const docs = data.docs || [];
        
        const listHtml = docs.length === 0
          ? '<div class="muted" style="padding: 40px; text-align: center;">暂无文档</div>'
          : docs.map(doc => `
            <div class="doc-card" data-doc-id="${doc.doc_id}">
              <div class="doc-card-info" onclick="window.location.href='/workbench/${doc.doc_id}'">
                <div class="doc-card-title">${doc.title}</div>
                <div class="doc-card-meta">
                  <span>${doc.char_count} 字</span>
                  <span>${doc.updated_at ? new Date(doc.updated_at).toLocaleDateString() : ''}</span>
                </div>
                <div class="doc-card-preview">${doc.text}</div>
              </div>
              <button class="doc-card-del" onclick="event.stopPropagation(); deleteDoc('${doc.doc_id}')">删除</button>
            </div>
          `).join('');
        
        const body = document.createElement("div");
        body.innerHTML = listHtml;
        body.className = "doc-list-body";
        
        const ok = document.createElement("button");
        ok.className = "btn primary";
        ok.textContent = "关闭";
        ok.addEventListener("click", closeModal);
        
        openModal({ title: "文档列表", body, actions: [ok] });
      } catch (e) {
        toast(`加载失败：${e.message}`, "bad");
      }
    });
  }
  
  window.deleteDoc = async (docId) => {
    if (!confirm("确定删除此文档？")) return;
    try {
      await fetch(`/api/doc/${docId}`, { method: "DELETE" });
      toast("已删除", "ok");
      closeModal();
      if (btnDocList) btnDocList.click();
    } catch (e) {
      toast(`删除失败：${e.message}`, "bad");
    }
  };

  loadDoc().catch((e) => {
    toast(`加载失败：${e.message}`, "bad");
    setStatus("加载失败", "bad");
  });
}

  if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", init);
  else init();
})();
