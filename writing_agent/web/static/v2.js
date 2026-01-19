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
    if (!src.trim()) return { title: "", blocks: [] };
    const lines = src.split("\n");
    const blocks = [];
    let title = "未命名文档";
    let sawH1 = false;

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
    return { title, blocks: explodeMarkers(blocks) };
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
    const htmlParts = ['<div class="sheet">'];
    if (!parsed.blocks.length) {
      htmlParts.push('<p class="muted">空白文档：在右侧输入要求生成，或切到“源文本”自行编写。</p>');
      htmlParts.push("</div>");
      preview.innerHTML = htmlParts.join("");
      return;
    }
    for (const b of parsed.blocks) {
      if (b.type === "heading") {
        const level = Math.max(1, Math.min(3, Number(b.level || 1)));
        htmlParts.push(`<h${level}>${escapeHtml(b.text || "")}</h${level}>`);
      } else if (b.type === "paragraph") {
        htmlParts.push(`<p>${escapeHtml(b.text || "").replace(/\n/g, "<br/>")}</p>`);
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
  }

  function setActiveTab(name) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.getAttribute("data-tab") === name));
    el("preview").classList.toggle("hidden", name !== "preview");
    el("source").classList.toggle("hidden", name !== "source");
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
    saveDebounce(() => saveSource().catch(() => {}), 600);
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
    saveDebounce(() => saveSource().catch(() => {}), 600);
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
    saveDebounce(() => saveSource().catch(() => {}), 600);
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

  el("source").addEventListener("input", () => {
    updateWordCount(el("source").value);
    if (generating) userEditedDuringGeneration = true;
    saveDebounce(async () => {
      try {
        await saveSource();
        setStatus("已保存", "ok");
      } catch (e) {
        setStatus("保存失败", "bad");
        toast(`保存失败：${e.message}`, "bad");
      }
    }, 500);
  });

  async function loadDoc() {
    const resp = await fetch(`/api/doc/${docId}`);
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    el("source").value = String(data.text || "");
    updateWordCount(el("source").value);
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

  el("btnNew").addEventListener("click", () => {
    window.location.href = "/";
  });
  el("btnNew").addEventListener("contextmenu", (e) => e.preventDefault());
  el("btnNew").addEventListener("auxclick", (e) => e.preventDefault());
  el("btnNew").addEventListener("mouseup", (e) => e.preventDefault());

  const templateFile = el("templateFile");
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
    if (!hasH1) t = `# ${title || "未命名报告"}\n\n` + t.trimStart();
    for (const s of sections || []) {
      const re = new RegExp(`^##\\s+${escapeRe(s)}\\s*$`, "m");
      if (!re.test(t)) t = (t.trimEnd() + `\n\n## ${s}\n\n`).replace(/\n{4,}/g, "\n\n");
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

  const btnGenerate = el("btnGenerate");
  const btnStop = el("btnStop");
  let aborter = null;

  btnStop.addEventListener("click", () => {
    if (aborter) aborter.abort();
  });

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
    setActiveTab("source");

    generating = true;
    userEditedDuringGeneration = false;

    aborter = new AbortController();

    const pending = new Map();
    let flushScheduled = false;
    const flush = () => {
      flushScheduled = false;
      for (const [sec, text] of pending.entries()) {
        appendDeltaToSection(sec, text);
      }
      pending.clear();
      updateWordCount(el("source").value);
      renderPreviewFromSource(el("source").value);
    };
    const scheduleFlush = () => {
      if (flushScheduled) return;
      flushScheduled = true;
      setTimeout(flush, 120);
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
             const title = String(data.title || "未命名报告");
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
             if (phase === "delta") {
               const delta = String(data.delta || "");
               const prev = String(pending.get(sec) || "");
               pending.set(sec, prev + delta);
               scheduleFlush();
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
      saveSource().catch(() => {});
    }
  });

    loadDoc().catch((e) => {
      toast(`加载失败：${e.message}`, "bad");
      setStatus("加载失败", "bad");
    });
  }

  if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", init);
  else init();
})();
