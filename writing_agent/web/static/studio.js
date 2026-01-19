async function postJson(url, payload) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`请求失败（HTTP ${resp.status}）：${txt}`);
  }
  return await resp.json();
}

const SYSTEM_NAME = "写作 Agent 工作台";
function showSystemNameModal() {
  window.alert(SYSTEM_NAME);
}

function appendMessageEl(role, content) {
  const log = document.getElementById("chatLog");
  if (!log) return null;
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function appendMessage(role, content) {
  appendMessageEl(role, content);
}

function getSelectionText() {
  const sel = window.getSelection();
  if (!sel) return "";
  return String(sel.toString() || "").trim();
}

function setStatus(text) {
  const el = document.getElementById("status");
  if (el) el.textContent = text || "";
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function wireRibbonTabs() {
  const ribbon = document.getElementById("ribbon");
  if (!ribbon) return;
  const tabs = Array.from(ribbon.querySelectorAll(".tab[data-tab]"));
  const panels = Array.from(ribbon.querySelectorAll(".panel[data-panel]"));
  if (!tabs.length || !panels.length) return;

  const activate = (name) => {
    tabs.forEach((t) => {
      const on = t.getAttribute("data-tab") === name;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    panels.forEach((p) => p.classList.toggle("active", p.getAttribute("data-panel") === name));
  };

  tabs.forEach((t) => t.addEventListener("click", () => activate(t.getAttribute("data-tab"))));
}

function wireToolbar(editor) {
  const on = (id, event, fn) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener(event, fn);
    return el;
  };

  const cmd = (c, v) => document.execCommand(c, false, v);

  const applySpanStyleToSelection = (styleObj) => {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return false;
    const range = selection.getRangeAt(0);
    if (range.collapsed) return false;
    const content = range.extractContents();
    const span = document.createElement("span");
    Object.entries(styleObj || {}).forEach(([k, v]) => {
      if (v) span.style[k] = v;
    });
    span.appendChild(content);
    range.insertNode(span);
    selection.removeAllRanges();
    const r = document.createRange();
    r.selectNodeContents(span);
    selection.addRange(r);
    return true;
  };

  const findBlock = (node) => {
    let cur = node;
    while (cur && cur !== editor) {
      const tag = (cur.nodeName || "").toLowerCase();
      if (["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div"].includes(tag)) return cur;
      cur = cur.parentNode;
    }
    return null;
  };

  const applyBlockStyle = (cssProp, value) => {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    const node = sel.anchorNode;
    const blk = findBlock(node);
    if (!blk) return false;
    blk.style[cssProp] = value;
    return true;
  };

  on("btnUndo", "click", () => cmd("undo"));
  on("btnRedo", "click", () => cmd("redo"));
  on("btnBold", "click", () => cmd("bold"));
  on("btnItalic", "click", () => cmd("italic"));
  on("btnUnderline", "click", () => cmd("underline"));
  on("btnClear", "click", () => {
    cmd("removeFormat");
    cmd("unlink");
    setStatus("已清除格式（部分样式可能保留）");
  });

  on("btnH1", "click", () => cmd("formatBlock", "H1"));
  on("btnH2", "click", () => cmd("formatBlock", "H2"));
  on("btnH3", "click", () => cmd("formatBlock", "H3"));
  on("btnP", "click", () => cmd("formatBlock", "P"));
  on("btnUL", "click", () => cmd("insertUnorderedList"));
  on("btnOL", "click", () => cmd("insertOrderedList"));

  const fontSizeSelect = document.getElementById("fontSizeSelect");
  const applyFontSize = (pt) => applySpanStyleToSelection({ fontSize: `${pt}pt` });
  on("btnFontSize", "click", () => {
    const v = String(fontSizeSelect.value || "").trim();
    if (!v) return;
    const pt = Number(v);
    if (!Number.isFinite(pt) || pt <= 0) return;
    const ok = applyFontSize(pt);
    if (!ok) setStatus("请先选中文字再应用字号");
    else setStatus(`已应用字号：${pt}pt`);
  });
  if (fontSizeSelect) fontSizeSelect.addEventListener("change", () => {
    const v = String(fontSizeSelect.value || "").trim();
    if (!v) return;
    const pt = Number(v);
    if (!Number.isFinite(pt) || pt <= 0) return;
    applyFontSize(pt);
  });

  const fontFamilySelect = document.getElementById("fontFamilySelect");
  on("btnFontFamily", "click", () => {
    const fam = String(fontFamilySelect.value || "").trim();
    if (!fam) return;
    const ok = applySpanStyleToSelection({ fontFamily: fam });
    if (!ok) setStatus("请先选中文字再应用字体");
    else setStatus(`已应用字体：${fam}`);
  });
  if (fontFamilySelect) fontFamilySelect.addEventListener("change", () => {
    const fam = String(fontFamilySelect.value || "").trim();
    if (!fam) return;
    const ok = applySpanStyleToSelection({ fontFamily: fam });
    if (!ok) setStatus("请先选中文字再应用字体");
    else setStatus(`已应用字体：${fam}`);
  });

  const colorPicker = document.getElementById("colorPicker");
  on("btnColor", "click", () => {
    const c = String(colorPicker.value || "").trim();
    if (!c) return;
    const ok = applySpanStyleToSelection({ color: c });
    if (!ok) setStatus("请先选中文字再应用字色");
    else setStatus("已应用字色");
  });
  if (colorPicker) colorPicker.addEventListener("input", () => {
    const c = String(colorPicker.value || "").trim();
    if (!c) return;
    const ok = applySpanStyleToSelection({ color: c });
    if (!ok) setStatus("请先选中文字再应用字色");
  });

  const hlPicker = document.getElementById("hlPicker");
  on("btnHighlight", "click", () => {
    const c = String(hlPicker.value || "").trim();
    if (!c) return;
    const ok = applySpanStyleToSelection({ backgroundColor: c });
    if (!ok) setStatus("请先选中文字再应用高亮");
    else setStatus("已应用高亮");
  });
  if (hlPicker) hlPicker.addEventListener("input", () => {
    const c = String(hlPicker.value || "").trim();
    if (!c) return;
    const ok = applySpanStyleToSelection({ backgroundColor: c });
    if (!ok) setStatus("请先选中文字再应用高亮");
  });

  on("btnAlignLeft", "click", () => applyBlockStyle("textAlign", "left"));
  on("btnAlignCenter", "click", () => applyBlockStyle("textAlign", "center"));
  on("btnAlignRight", "click", () => applyBlockStyle("textAlign", "right"));
  on("btnAlignJustify", "click", () => applyBlockStyle("textAlign", "justify"));

  const lineHeightSelect = document.getElementById("lineHeightSelect");
  on("btnLineHeight", "click", () => {
    const v = String(lineHeightSelect.value || "").trim();
    if (!v) return;
    const ok = applyBlockStyle("lineHeight", v);
    if (!ok) setStatus("请将光标放在要设置的段落里");
    else setStatus(`已设置行距：${v}`);
  });
  if (lineHeightSelect) lineHeightSelect.addEventListener("change", () => {
    const v = String(lineHeightSelect.value || "").trim();
    if (!v) return;
    const ok = applyBlockStyle("lineHeight", v);
    if (!ok) setStatus("请将光标放在要设置的段落里");
    else setStatus(`已设置行距：${v}`);
  });

  on("btnLink", "click", () => {
    const url = prompt("链接地址（http/https）");
    if (!url) return;
    cmd("createLink", url);
  });
  on("btnUnlink", "click", () => cmd("unlink"));

  on("btnTable", "click", () => {
    const r = Number(prompt("表格行数", "3"));
    const c = Number(prompt("表格列数", "3"));
    if (!Number.isFinite(r) || !Number.isFinite(c) || r <= 0 || c <= 0) return;
    const rows = Math.min(12, Math.floor(r));
    const cols = Math.min(8, Math.floor(c));
    let html = '<table class="tbl"><tbody>';
    for (let i = 0; i < rows; i++) {
      html += "<tr>";
      for (let j = 0; j < cols; j++) html += "<td> </td>";
      html += "</tr>";
    }
    html += "</tbody></table>";
    document.execCommand("insertHTML", false, html);
    setStatus("表格已插入");
  });

  on("btnImage", "click", async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      setStatus("上传图片中…");
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(`/api/studio/${editor.getAttribute("data-doc-id")}/upload-image`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) {
        const txt = await resp.text();
        setStatus(`上传失败：${txt}`);
        return;
      }
      const data = await resp.json();
      document.execCommand("insertHTML", false, `<p><img src="${data.url}" alt="image" /></p>`);
      setStatus("图片已插入");
    };
    input.click();
  });

  async function insertDiagram(type) {
    const promptText =
      type === "er"
        ? "描述你要画的 ER 图（实体/属性/关系），例如：用户-订单 一对多"
        : "描述你要画的流程图步骤，例如：开始->输入->处理->输出";
    const instruction = prompt(promptText);
    if (!instruction) return;
    setStatus("生成图表中…");
    try {
      const res = await postJson(`/api/studio/${editor.getAttribute("data-doc-id")}/diagram`, {
        type,
        instruction,
      });
      document.execCommand("insertHTML", false, res.html || "");
      setStatus("图表已插入");
      showSystemNameModal();
    } catch (e) {
      setStatus(`图表生成失败：${e.message}`);
    }
  }

  on("btnFlow", "click", () => insertDiagram("flowchart"));
  on("btnER", "click", () => insertDiagram("er"));
}

function stripHtmlToPreviewText(html) {
  const s = String(html || "");
  return s
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<\/(p|h1|h2|h3|h4|h5|h6|li|tr|div)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/\[\[(FLOW|ER|IMG)\s*:\s*([\s\S]{1,80}?)\]\]/gi, (_m, t, d) => `[${String(t).toUpperCase()}: ${String(d).trim()}]`)
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function captureEditorRange(editor) {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return null;
  const r = sel.getRangeAt(0);
  const node = r.commonAncestorContainer;
  if (!node) return null;
  if (editor.contains(node)) return r.cloneRange();
  return null;
}

function restoreEditorRange(editor, range) {
  if (!range) return false;
  try {
    editor.focus();
    const sel = window.getSelection();
    if (!sel) return false;
    sel.removeAllRanges();
    sel.addRange(range);
    return true;
  } catch {
    return false;
  }
}

function insertStreamPlaceholder(editor, range) {
  const id = `s${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`;
  const html = `<div class="ai-stream" data-stream-id="${id}">AI 生成中…</div>`;

  const restored = restoreEditorRange(editor, range);
  if (restored) {
    document.execCommand("insertHTML", false, html);
    const el = editor.querySelector(`[data-stream-id="${id}"]`);
    if (el) return el;
  }

  editor.insertAdjacentHTML("beforeend", `<p></p>${html}<p></p>`);
  return editor.querySelector(`[data-stream-id="${id}"]`);
}

async function streamSsePost(url, payload, handlers) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`请求失败（HTTP ${resp.status}）：${txt}`);
  }
  if (!resp.body) throw new Error("当前环境不支持流式输出");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  const handleBlock = (block) => {
    const lines = String(block || "").replace(/\r/g, "").split("\n");
    let event = "message";
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice("event:".length).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice("data:".length).trim());
    }
    const dataText = dataLines.join("\n");
    let data = null;
    try {
      data = dataText ? JSON.parse(dataText) : {};
    } catch {
      data = { raw: dataText };
    }
    if (handlers && handlers.onEvent) handlers.onEvent(event, data);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx = buf.indexOf("\n\n");
    while (idx >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (block.trim()) handleBlock(block);
      idx = buf.indexOf("\n\n");
    }
  }
}

async function main() {
  const editor = document.getElementById("editor");
  const docId = editor.getAttribute("data-doc-id");

  wireRibbonTabs();
  wireToolbar(editor);

  let isStreaming = false;
  let lastEditorRange = null;
  const updateRange = () => {
    const r = captureEditorRange(editor);
    if (r) lastEditorRange = r;
  };
  editor.addEventListener("mouseup", updateRange);
  editor.addEventListener("keyup", updateRange);
  editor.addEventListener("focus", updateRange);

  const save = debounce(async () => {
    if (isStreaming) return;
    try {
      await postJson(`/api/studio/${docId}/save`, { html: editor.innerHTML });
      setStatus("已保存");
    } catch (e) {
      setStatus(`保存失败：${e.message}`);
    }
  }, 500);

  editor.addEventListener("input", () => {
    if (isStreaming) return;
    setStatus("保存中…");
    save();
  });

  const sendBtn = document.getElementById("sendBtn");
  const input = document.getElementById("chatInput");
  sendBtn.addEventListener("click", async () => {
    const instruction = String(input.value || "").trim();
    if (!instruction) return;

    appendMessage("user", instruction);
    input.value = "";
    setStatus("生成中…");
    sendBtn.disabled = true;

    try {
      const m = instruction.match(/^\/(flow|er)\s+([\s\S]+)$/i);
      if (m) {
        const type = m[1].toLowerCase() === "er" ? "er" : "flowchart";
        const desc = String(m[2] || "").trim();
        const res = await postJson(`/api/studio/${docId}/diagram`, { type, instruction: desc });
        editor.innerHTML = (editor.innerHTML || "") + (res.html || "");
        setStatus("图表已插入");
        await postJson(`/api/studio/${docId}/save`, { html: editor.innerHTML });
        showSystemNameModal();
        return;
      }

      const selection = getSelectionText();

      isStreaming = true;
      const htmlBefore = editor.innerHTML;
      const placeholder = insertStreamPlaceholder(editor, lastEditorRange);
      editor.setAttribute("contenteditable", "false");

      const streamingEl = appendMessageEl("assistant", "正在生成并应用到左侧…");
      if (streamingEl) streamingEl.classList.add("streaming");

      let rawHtml = "";
      let lastPaint = 0;

      await streamSsePost(
        `/api/studio/${docId}/chat/stream`,
        { instruction, html: htmlBefore, selection },
        {
          onEvent: (event, data) => {
            if (event === "delta") {
              const delta = String((data && data.delta) || "");
              rawHtml += delta;
              const now = Date.now();
              if (placeholder && (now - lastPaint > 60 || delta.includes("\n"))) {
                lastPaint = now;
                placeholder.textContent = stripHtmlToPreviewText(rawHtml) || "AI 生成中…";
              }
              return;
            }
            if (event === "error") {
              const msg = String((data && data.message) || "发生错误");
              if (streamingEl) streamingEl.textContent = msg;
              if (placeholder) placeholder.textContent = msg;
              setStatus("出错");
              return;
            }
            if (event === "final") {
              const assistant = String((data && data.assistant) || "完成");
              const html = String((data && data.html) || "");
              if (streamingEl) {
                streamingEl.classList.remove("streaming");
                streamingEl.textContent = assistant;
              } else {
                appendMessage("assistant", assistant);
              }
              if (html) editor.innerHTML = html;
              setStatus("完成");
              showSystemNameModal();
              return;
            }
          },
        },
      );
    } catch (e) {
      appendMessage("assistant", `发生错误：${e.message}`);
      setStatus("出错");
    } finally {
      sendBtn.disabled = false;
      isStreaming = false;
      editor.setAttribute("contenteditable", "true");
    }
  });
}

window.addEventListener("DOMContentLoaded", main);
