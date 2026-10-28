// School Docs Assistant UI: plain JavaScript, no build step.
// Every API response uses the envelope {status, data, error}; see docs/API_STANDARDS.md.

const $ = (sel) => document.querySelector(sel);
const SUGGESTIONS = [
  "What is the late fee for tuition?",
  "What documents are needed for admission?",
  "When does the winter break start?",
  "What happens if a student is caught cheating?",
];

async function api(path, options = {}) {
  const res = await fetch(path, options);
  let body;
  try { body = await res.json(); } catch { throw new Error(`Unexpected response (${res.status})`); }
  if (body.status !== "success") throw new Error(body.error?.message || "Request failed");
  return body.data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => (k === "class" ? (node.className = v) : node.setAttribute(k, v)));
  children.flat().forEach((c) => node.append(c instanceof Node ? c : document.createTextNode(String(c))));
  return node;
}

function setStatus(text, kind = "") {
  const s = $("#upload-status");
  s.textContent = text;
  s.className = `status ${kind}`;
}

async function loadHealth() {
  try {
    const h = await api("/health");
    $("#provider-badge").textContent = `provider: ${h.provider}`;
  } catch { $("#provider-badge").textContent = "offline"; }
}

async function loadDocuments() {
  const docs = await api("/documents");
  const list = $("#doc-list");
  list.replaceChildren();
  $("#doc-empty").style.display = docs.length ? "none" : "block";
  for (const d of docs) {
    const del = el("button", { class: "icon-btn", title: `Delete ${d.filename}`, "aria-label": `Delete ${d.filename}` }, "🗑");
    del.addEventListener("click", async () => {
      if (!confirm(`Delete ${d.filename}?`)) return;
      try { await api(`/documents/${d.id}`, { method: "DELETE" }); setStatus(`Deleted ${d.filename}`, "ok"); }
      catch (e) { setStatus(e.message, "err"); }
      loadDocuments();
    });
    const pages = d.content_type === "application/pdf" ? `${d.pages} page${d.pages > 1 ? "s" : ""} · ` : "";
    list.append(el("li", {},
      el("div", {}, el("div", { class: "doc-name" }, d.filename),
        el("div", { class: "doc-meta" }, `${pages}${d.chunks} chunk${d.chunks > 1 ? "s" : ""}`)),
      del));
  }
}

async function uploadFiles(files) {
  for (const file of files) {
    setStatus(`Uploading ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    try {
      const d = await api("/documents", { method: "POST", body: form });
      setStatus(`Added ${d.filename} (${d.chunks} chunks)`, "ok");
    } catch (e) { setStatus(e.message, "err"); }
  }
  loadDocuments();
}

function addMessage(role, content, extraClass = "") {
  const bubble = el("div", { class: "bubble" }, content);
  const msg = el("div", { class: `msg ${role} ${extraClass}`.trim() }, bubble);
  $("#messages").append(msg);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return bubble;
}

function renderSources(bubble, sources) {
  if (!sources.length) return;
  bubble.append(el("div", { class: "sources-label" }, `Sources (${sources.length}) · click to expand`));
  const box = el("div", { class: "sources" });
  sources.forEach((s, i) => {
    const where = s.page ? ` · page ${s.page}` : "";
    const card = el("div", { class: "source", title: "Click to expand" },
      el("div", { class: "source-head" }, `[${i + 1}] ${s.document_name}${where}`, el("span", {}, `score ${s.score.toFixed(2)}`)),
      el("p", {}, s.snippet));
    card.addEventListener("click", () => card.classList.toggle("open"));
    box.append(card);
  });
  bubble.append(box);
}

async function ask(question) {
  addMessage("user", question);
  const pending = addMessage("bot", el("span", { class: "typing" }, "Searching the documents…"));
  $("#send-btn").disabled = true;
  try {
    const data = await api("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    pending.replaceChildren(data.answer);
    if (!data.grounded) pending.parentElement.classList.add("refused");
    renderSources(pending, data.sources);
  } catch (e) {
    pending.replaceChildren(`⚠️ ${e.message}`);
    pending.parentElement.classList.add("refused");
  } finally {
    $("#send-btn").disabled = false;
    $("#messages").scrollTop = $("#messages").scrollHeight;
  }
}

function init() {
  $("#chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#question").value.trim();
    if (!q) return;
    $("#question").value = "";
    ask(q);
  });
  $("#file-input").addEventListener("change", (e) => uploadFiles(e.target.files));
  const zone = $("#upload-form");
  ["dragenter", "dragover"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.remove("drag"); }));
  zone.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));
  SUGGESTIONS.forEach((q) => {
    const b = el("button", { type: "button" }, q);
    b.addEventListener("click", () => ask(q));
    $("#suggestions").append(b);
  });
  loadHealth();
  loadDocuments().catch((e) => setStatus(e.message, "err"));
}

init();
