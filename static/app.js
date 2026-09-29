/**
 * AI Document Assistant -- frontend logic.
 *
 * Talks to the FastAPI backend (main.py) at /api/ingest, /api/ask/stream
 * (server-sent events), /api/summary, /api/suggestions, /api/remove and
 * /api/session. All dynamic content
 * (questions, answers, document text, filenames) is inserted with
 * textContent / text nodes, never innerHTML, so nothing from a document or
 * the model can inject markup into the page.
 */

const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

const uploadView = document.getElementById("upload-view");
const indexingView = document.getElementById("indexing-view");
const chatView = document.getElementById("chat-view");

const fileInput = document.getElementById("file-input");
const dropzone = document.getElementById("dropzone");
const uploadError = document.getElementById("upload-error");

const docList = document.getElementById("doc-list");
const addFileInput = document.getElementById("add-file-input");
const addBtn = document.getElementById("add-btn");
const addStatus = document.getElementById("add-status");
const removeBtn = document.getElementById("remove-btn");

const messagesEl = document.getElementById("messages");
const askForm = document.getElementById("ask-form");
const questionInput = document.getElementById("question-input");
const askBtn = document.getElementById("ask-btn");
const stopBtn = document.getElementById("stop-btn");
const attachBtn = document.getElementById("attach-btn");
const scopeLabel = document.getElementById("scope-label");
const exportBtn = document.getElementById("export-btn");

const docItemTemplate = document.getElementById("doc-item-template");
const sourceItemTemplate = document.getElementById("source-item-template");

function showView(view) {
  const changed = document.body.dataset.view !== view;
  document.body.dataset.view = view;
  const views = { upload: uploadView, indexing: indexingView, chat: chatView };
  for (const [name, el] of Object.entries(views)) {
    el.hidden = name !== view;
    // Fade the newly shown view in; restart the animation on every switch.
    el.classList.remove("view-enter");
    if (changed && name === view) {
      void el.offsetWidth;
      el.classList.add("view-enter");
    }
  }
}

/**
 * fetch + JSON that never throws. A proxy in front of the app (e.g. Nginx
 * returning an HTML 413/502 page) or a dropped connection becomes
 * {error: "..."} instead of an exception that would leave the UI stuck.
 */
async function api(url, body) {
  const options = { method: body === undefined ? "GET" : "POST" };
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(url, options);
  } catch (err) {
    return { error: "Couldn't reach the server. Check your connection and try again." };
  }

  let data;
  try {
    data = await response.json();
  } catch (err) {
    if (response.status === 413) return { error: "That file is over the 25MB limit." };
    return { error: `The server sent an unexpected response (HTTP ${response.status}). Try again in a moment.` };
  }
  if (!response.ok && !data.error) {
    data.error = `The request failed (HTTP ${response.status}). Try again in a moment.`;
  }
  return data;
}

// ---------- Messages ----------

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/**
 * Scroll the conversation so `el` sits at the top of the pane. Used when an
 * answer arrives: jumping to the bottom would skip past the start of a long
 * answer, so the view stops at the question and the answer reads top-down.
 */
function scrollToStart(el) {
  const offset = el.getBoundingClientRect().top - messagesEl.getBoundingClientRect().top;
  messagesEl.scrollTop += offset - 8;
}

function append(el) {
  el.classList.add("msg-enter");
  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function addUser(text) {
  const el = document.createElement("p");
  el.className = "msg msg-user";
  el.textContent = text;
  return append(el);
}

function addNote(text) {
  const el = document.createElement("div");
  el.className = "msg msg-assistant msg-note";
  const p = document.createElement("p");
  p.className = "msg-text";
  p.textContent = text;
  el.appendChild(p);
  return append(el);
}

function addPending(text) {
  const el = addNote(text);
  el.classList.add("msg-pending");
  return el;
}

function addError(text) {
  const el = document.createElement("p");
  el.className = "msg msg-error";
  el.setAttribute("role", "alert");
  el.textContent = text;
  return append(el);
}

// Models often wrap key phrases in **bold**. Text is shown as plain text (no
// markdown rendering, by design), so drop the markers instead of showing
// literal asterisks.
function plain(text) {
  return delatex(text)
    .replace(/\*\*(.+?)\*\*/g, "$1")
    // Markdown list markers ("* item", "- item") become real bullets.
    .replace(/^([ \t]*)[*-][ \t]+/gm, "$1• ");
}

// The prompt asks for plain text, but models (especially smaller fallback
// ones) still write LaTeX for formulas. Turn the common pieces into readable
// text rather than showing backslashes.
function delatex(text) {
  const symbols = { times: "×", cdot: "·", dots: "…", ldots: "…", approx: "≈", leq: "≤", geq: "≥", infty: "∞", to: "→", in: "∈" };
  let out = text
    .replace(/\\\(|\\\)|\\\[|\\\]/g, "")
    .replace(/\\(?:text|mathrm|mathbf|operatorname)\{([^{}]*)\}/g, "$1")
    .replace(/\\sqrt\{([^{}]*)\}/g, "√$1")
    .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, "($1)/($2)")
    .replace(/\\([a-zA-Z]+)/g, (m, name) => symbols[name] ?? m);
  // x_{i} -> x_i, x^{2} -> x^2 (braces only add noise in plain text);
  // repeated so nested braces unwrap from the inside out.
  for (let previous = ""; previous !== out; ) {
    previous = out;
    out = out.replace(/([_^])\{([^{}]*)\}/g, "$1$2");
  }
  return out;
}

// Citations the model writes, e.g. 【report.pdf, Page 3】, [Page 3],
// (Page 3), (see Pages 3 and 4) or (report.pdf, Page 3). The model isn't
// consistent about which form it uses, so all are turned into page tabs.
const PAGE_REF = String.raw`(?:[^()\[\]\n]*?,\s*)?Pages?\s*(?:[\d\s,–-]|and|&)+`;
const CITATION = new RegExp(
  String.raw`【([^】]*)】|\[(${PAGE_REF})\]|\((?:see\s+)?(${PAGE_REF})\)`,
  "gi",
);

function citedPages(inner) {
  const at = inner.search(/Pages?\s*\d/i);
  if (at < 0) return { doc: "", pages: [] };
  // Everything before the comma preceding "Page" is the document name; only
  // numbers after "Page" are pages (so "report2024.pdf" isn't page 2024).
  const comma = inner.lastIndexOf(",", at);
  const doc = comma > 0 ? inner.slice(0, comma).trim() : "";
  const pages = [...inner.slice(at).matchAll(/\d+/g)].map((m) => Number(m[0]));
  return { doc: /page/i.test(doc) ? "" : doc, pages: [...new Set(pages)] };
}

/**
 * Fill `container` with the answer text, replacing citations with page tabs.
 * A tab whose page is among this answer's sources becomes a button that
 * opens the sources and highlights that passage.
 */
function renderAnswerText(container, text, notes) {
  text = plain(text);
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const inner = match[1] ?? match[2] ?? match[3];
    const { doc, pages } = citedPages(inner);
    if (pages.length === 0) continue;

    container.append(text.slice(last, match.index).replace(/\s+$/, ""));
    for (const page of pages) {
      const slip = findSlip(notes, page, doc);
      const tab = document.createElement(slip ? "button" : "span");
      tab.className = "cite";
      tab.textContent = `p. ${page}`;
      tab.title = doc ? `${doc}, page ${page}` : `Page ${page}`;
      if (slip) {
        tab.type = "button";
        tab.setAttribute("aria-label", `Show the passage from ${tab.title}`);
        tab.addEventListener("click", () => markSlip(notes, slip));
      }
      container.append(tab);
    }
    last = match.index + match[0].length;
  }
  container.append(text.slice(last));
}

function findSlip(notes, page, doc) {
  if (!notes) return null;
  const slips = [...notes.list.querySelectorAll(".slip")];
  return (
    slips.find((s) => Number(s.dataset.page) === page && (!doc || s.dataset.doc === doc)) ||
    slips.find((s) => Number(s.dataset.page) === page) ||
    null
  );
}

function setNotesOpen(notes, open) {
  notes.panel.classList.toggle("open", open);
  notes.toggle.setAttribute("aria-expanded", String(open));
  notes.toggle.textContent = `${open ? "Hide" : "Show"} ${notes.label.toLowerCase()} (${notes.count})`;
}

function markSlip(notes, slip) {
  setNotesOpen(notes, true);
  for (const s of notes.list.querySelectorAll(".slip.marked")) s.classList.remove("marked");
  // Restart the highlighter animation even when the same tab is clicked twice.
  void slip.offsetWidth;
  slip.classList.add("marked");
  slip.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

/**
 * Source passages as margin notes. On a wide conversation they sit beside
 * the answer (CSS container query); on a narrow one they fold under it
 * behind a Show/Hide button.
 */
function buildNotes(sources, label) {
  if (!sources || sources.length === 0) return null;

  // Only name the document when more than one is loaded -- otherwise it's noise.
  const multiDoc = new Set(sources.map((s) => s.doc)).size > 1 || docList.children.length > 1;

  const panel = document.createElement("aside");
  panel.className = "notes";
  panel.setAttribute("aria-label", label);
  const list = document.createElement("ol");
  list.className = "slips";
  panel.appendChild(list);

  for (const [i, src] of sources.entries()) {
    const node = sourceItemTemplate.content.cloneNode(true);
    const slip = node.querySelector(".slip");
    slip.style.setProperty("--i", i);
    slip.dataset.page = src.page;
    slip.dataset.doc = src.doc || "";
    node.querySelector(".slip-page").textContent =
      multiDoc && src.doc ? `${src.doc}, p. ${src.page}` : `Page ${src.page}`;
    node.querySelector(".slip-score").textContent =
      typeof src.score === "number" ? `similarity ${src.score.toFixed(2)}` : "";
    // PDF extraction keeps the page's hard line breaks; rejoin them so the
    // passage reads as prose (blank lines between paragraphs are kept).
    node.querySelector(".slip-text").textContent = src.text.replace(/(?<!\n)\n(?!\n)/g, " ");
    // In the margin, notes are clipped to a few lines; clicking one opens it.
    slip.addEventListener("click", () => slip.classList.toggle("expanded"));
    list.appendChild(node);
  }

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "btn btn-text notes-toggle";
  const notes = { panel, list, toggle, label, count: sources.length };
  toggle.addEventListener("click", () => setNotesOpen(notes, !panel.classList.contains("open")));
  setNotesOpen(notes, false);
  return notes;
}

/** Turn a pending message into a finished answer (or add a new one). */
const REFUSAL = "I could not find the answer";
const FOLLOW_UPS = [
  ["Explain more simply", "Explain that more simply, in plain words for someone new to the topic, still using only what the passages say."],
  // Asking for "more" invites padding from outside knowledge (seen in testing
  // on a short document), so the instruction repeats the grounding rule.
  ["Go deeper", "Give more detail on that, using only details that appear in the passages. If the documents say nothing more, say so."],
];

function buildActions(answer, { followUps }) {
  const bar = document.createElement("div");
  bar.className = "answer-actions";
  if (followUps) {
    for (const [label, question] of FOLLOW_UPS) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-text follow-up";
      button.textContent = label;
      button.addEventListener("click", () => askQuestion(question, label));
      bar.appendChild(button);
    }
  }
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "btn btn-text copy-answer";
  copy.textContent = "Copy";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(answerAsText(answer));
      copy.textContent = "Copied";
    } catch (err) {
      copy.textContent = "Couldn't copy";
    }
    setTimeout(() => (copy.textContent = "Copy"), 1600);
  });
  bar.appendChild(copy);
  return bar;
}

/** The answer as plain text, with its sources listed underneath. */
function answerAsText(answer) {
  const lines = [plain(answer.text).trim()];
  if (answer.sources.length) {
    lines.push("", "Sources:");
    for (const src of answer.sources) {
      const where = src.doc ? `${src.doc}, page ${src.page}` : `Page ${src.page}`;
      const excerpt = src.text.replace(/\s+/g, " ").trim();
      lines.push(`- ${where}: "${excerpt.length > 160 ? excerpt.slice(0, 160) + "…" : excerpt}"`);
    }
  }
  return lines.join("\n");
}

/** Lay out an answer (text + margin notes) inside `el`; the text is filled in
 *  by updateAnswer, repeatedly while streaming. */
function startAnswer(el, sources, { heading, sourcesLabel = "Sources" } = {}) {
  el.className = "msg msg-assistant answer msg-enter";
  el.removeAttribute("role");
  el.replaceChildren();

  const main = document.createElement("div");
  main.className = "answer-main";
  if (heading) {
    const h = document.createElement("p");
    h.className = "msg-heading";
    h.textContent = heading;
    main.appendChild(h);
  }
  const notes = buildNotes(sources, sourcesLabel);
  const body = document.createElement("p");
  body.className = "msg-text";
  main.appendChild(body);
  el.appendChild(main);
  if (notes) {
    el.classList.add("has-notes");
    el.appendChild(notes.panel);
  }
  return { el, main, body, notes, sources: sources || [], text: "" };
}

function updateAnswer(answer) {
  answer.body.replaceChildren();
  renderAnswerText(answer.body, answer.text, answer.notes);
}

function finishAnswer(answer, { followUps = false, stopped = false } = {}) {
  answer.body.classList.remove("streaming");
  updateAnswer(answer);
  if (stopped) {
    const note = document.createElement("p");
    note.className = "answer-stopped";
    note.textContent = "Stopped. This partial answer isn't used for follow-up questions.";
    answer.main.appendChild(note);
  }
  const refused = answer.text.trim().startsWith(REFUSAL);
  if (!stopped && answer.text) answer.main.appendChild(buildActions(answer, { followUps: followUps && !refused }));
  if (answer.notes) answer.main.appendChild(answer.notes.toggle);
}

function showAnswer(el, text, sources, { heading, sourcesLabel = "Sources", followUps = false } = {}) {
  const answer = startAnswer(el, sources, { heading, sourcesLabel });
  answer.text = text;
  finishAnswer(answer, { followUps });
  return answer;
}

function showFailure(el, text) {
  el.className = "msg msg-error";
  el.setAttribute("role", "alert");
  el.textContent = text;
}

// ---------- Documents ----------

let shownDocIds = new Set();

// Documents the reader has unticked; questions search all the others.
const excludedDocIds = new Set();
let loadedDocs = [];

function includedDocIds() {
  return loadedDocs.map((d) => d.id).filter((id) => !excludedDocIds.has(id));
}

function syncScope() {
  const total = loadedDocs.length;
  const included = includedDocIds().length;
  if (total === 0) scopeLabel.textContent = "";
  else if (included === 0) scopeLabel.textContent = "Tick a document to search";
  else if (total === 1) scopeLabel.textContent = "Searching 1 document";
  else if (included === total) scopeLabel.textContent = `Searching all ${total} documents`;
  else scopeLabel.textContent = `Searching ${included} of ${total} documents`;
  scopeLabel.classList.toggle("scope-empty", total > 0 && included === 0);
  syncQuestionState();
}

function renderDocuments(documents) {
  loadedDocs = documents;
  for (const id of [...excludedDocIds]) if (!documents.some((d) => d.id === id)) excludedDocIds.delete(id);
  docList.replaceChildren();
  for (const doc of documents) {
    const node = docItemTemplate.content.cloneNode(true);
    if (!shownDocIds.has(doc.id)) node.querySelector(".doc-item").classList.add("doc-enter");
    const include = node.querySelector(".doc-include");
    include.checked = !excludedDocIds.has(doc.id);
    include.setAttribute("aria-label", `Search ${doc.filename}`);
    include.addEventListener("change", () => {
      if (include.checked) excludedDocIds.delete(doc.id);
      else excludedDocIds.add(doc.id);
      syncScope();
    });
    node.querySelector(".doc-name").textContent = doc.filename;
    node.querySelector(".doc-name").title = doc.filename;
    node.querySelector(".doc-meta").textContent =
      `${doc.num_pages} ${doc.num_pages === 1 ? "page" : "pages"}`;
    node.querySelector(".doc-summary").addEventListener("click", (e) => summarizeDoc(doc, e.currentTarget));
    const remove = node.querySelector(".doc-remove");
    remove.setAttribute("aria-label", `Remove ${doc.filename}`);
    remove.title = "Remove";
    remove.addEventListener("click", () => removeDoc(doc.id));
    docList.appendChild(node);
  }
  shownDocIds = new Set(documents.map((d) => d.id));
  syncScope();
  if (documents.length === 0) {
    transcript.length = 0;
    syncExport();
    messagesEl.replaceChildren();
    fileInput.value = "";
    showView("upload");
  }
}

function validateFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) return "That isn't a PDF. Choose a file ending in .pdf.";
  if (file.size > MAX_UPLOAD_BYTES) return "That file is over the 25MB limit.";
  return null;
}

async function ingest(file) {
  const formData = new FormData();
  formData.append("file", file);
  return api("/api/ingest", formData);
}

// First document: full-screen upload -> indexing -> chat.
async function uploadFirst(file) {
  uploadError.hidden = true;
  const problem = validateFile(file);
  if (problem) {
    uploadError.textContent = problem;
    uploadError.hidden = false;
    return;
  }

  document.getElementById("reading-name").textContent = `Reading ${file.name}…`;
  showView("indexing");
  const data = await ingest(file);
  fileInput.value = "";

  if (data.error) {
    showView("upload");
    uploadError.textContent = data.error;
    uploadError.hidden = false;
    return;
  }

  messagesEl.replaceChildren();
  showView("chat");
  renderDocuments(data.documents);
  addNote(`${data.filename} is ready. Ask anything about it.`);
  showSuggestions(data.id);
  questionInput.value = "";
  questionInput.focus();
}

// Further documents: read inline, conversation stays.
async function uploadAdditional(file) {
  const problem = validateFile(file);
  if (problem) {
    addError(problem);
    return;
  }

  addStatus.hidden = false;
  addBtn.hidden = true;
  const data = await ingest(file);
  addStatus.hidden = true;
  addBtn.hidden = false;
  addFileInput.value = "";

  if (data.error) {
    addError(`Couldn't add ${file.name}: ${data.error}`);
    return;
  }
  renderDocuments(data.documents);
  addNote(`Added ${data.filename}. Questions now search all ${data.documents.length} documents.`);
}

/** The LLM reads a sample of the document and proposes starter questions.
 *  Best-effort: on any error the conversation simply starts without them. */
async function showSuggestions(docId) {
  const data = await api("/api/suggestions", { id: docId });
  if (data.error || !data.questions || data.questions.length === 0) return;

  const box = document.createElement("div");
  box.className = "msg suggestions";
  const label = document.createElement("p");
  label.className = "suggestions-label";
  label.textContent = "Try asking";
  box.appendChild(label);
  for (const question of data.questions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion";
    button.textContent = question;
    button.addEventListener("click", () => askQuestion(question));
    box.appendChild(button);
  }
  append(box);
}

async function summarizeDoc(doc, button) {
  button.disabled = true;
  const pending = addPending(`Summarizing ${doc.filename}…`);
  const data = await api("/api/summary", { id: doc.id });
  button.disabled = false;

  if (data.error) {
    showFailure(pending, data.error);
    return;
  }
  // The heading already says "Summary of …"; drop the model's own "Summary:" lead-in.
  const summary = data.summary.replace(/^\s*\**(?:document\s+)?summary\**:?\**\s*/i, "");
  const answer = showAnswer(pending, summary, data.sources, {
    heading: `Summary of ${data.filename}`,
    sourcesLabel: "Passages used",
  });
  transcript.push({ question: `Summary of ${data.filename}`, answer: answer.text, sources: answer.sources });
  syncExport();
  scrollToStart(pending);
}

async function removeDoc(id) {
  const data = await api("/api/remove", { id });
  if (data.error) {
    addError(data.error);
    return;
  }
  renderDocuments(data.documents);
}

// ---------- Events ----------

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) uploadFirst(fileInput.files[0]);
});

addFileInput.addEventListener("change", () => {
  if (addFileInput.files.length > 0) uploadAdditional(addFileInput.files[0]);
});

// The upload labels are focusable; let Enter/Space open the file picker like a button.
function openPickerOnKey(label, input) {
  label.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      input.click();
    }
  });
}
openPickerOnKey(addBtn, addFileInput);
openPickerOnKey(attachBtn, addFileInput);
openPickerOnKey(dropzone, fileInput);

// Drag-and-drop on the dropzone, with a visual hover state.
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragging");
});
dropzone.addEventListener("dragleave", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragging");
});
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragging");
  const file = e.dataTransfer.files[0];
  if (file) uploadFirst(file);
});

removeBtn.addEventListener("click", async () => {
  await api("/api/remove", {});
  renderDocuments([]);
});

let busy = false;
let activeStream = null; // AbortController of the answer being streamed

// Question/answer pairs of this page view, for Export conversation.
const transcript = [];

function setBusy(on) {
  busy = on;
  document.body.classList.toggle("busy", on);
  stopBtn.hidden = !on;
  askBtn.hidden = on;
  questionInput.disabled = on;
  if (!on) {
    syncQuestionState();
    questionInput.focus({ preventScroll: true });
  }
}

/** Read a server-sent-events body, calling onEvent(name, data) per event. */
async function readEvents(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let name = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) onEvent(name, JSON.parse(data));
    }
  }
}

/** `shown` is what appears in the conversation when it differs from the
 *  instruction sent (the follow-up buttons send a fuller instruction). */
async function askQuestion(question, shown = question) {
  question = question.trim();
  if (!question || busy) return;
  const docIds = includedDocIds();
  if (docIds.length === 0) {
    syncScope();
    return;
  }

  const asked = addUser(shown);
  questionInput.value = "";
  autoGrow();
  setBusy(true);
  const pending = addPending("Searching your documents…");

  const controller = new AbortController();
  activeStream = controller;
  const body = { question };
  if (docIds.length < loadedDocs.length) body.doc_ids = docIds;

  let answer = null;
  let failed = null;
  let frame = 0;
  const render = () => {
    frame = 0;
    if (answer) updateAnswer(answer);
  };

  try {
    const response = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok || !(response.headers.get("content-type") || "").startsWith("text/event-stream")) {
      let data = {};
      try {
        data = await response.json();
      } catch (err) {
        data = {};
      }
      failed = data.error || `The request failed (HTTP ${response.status}). Try again in a moment.`;
    } else {
      await readEvents(response, (name, data) => {
        if (name === "sources") {
          answer = startAnswer(pending, data);
          answer.body.classList.add("streaming");
          scrollToStart(asked);
        } else if (name === "token" && answer) {
          answer.text += data.text;
          if (!frame) frame = requestAnimationFrame(render);
        } else if (name === "error") {
          failed = data.error;
        }
      });
    }
  } catch (err) {
    if (err.name !== "AbortError") failed = "Couldn't reach the server. Check your connection and try again.";
  }
  if (frame) cancelAnimationFrame(frame);

  const stopped = controller.signal.aborted;
  if (answer && (answer.text || stopped)) {
    finishAnswer(answer, { followUps: true, stopped });
    if (failed) addError(failed);
    else if (!stopped) {
      transcript.push({ question: shown, answer: answer.text, sources: answer.sources });
      syncExport();
    }
  } else if (stopped) {
    pending.remove();
  } else {
    showFailure(pending, failed || "Something went wrong. Please try again.");
  }
  scrollToStart(asked);
  activeStream = null;
  setBusy(false);
}

function stopAnswer() {
  if (activeStream) activeStream.abort();
}

askForm.addEventListener("submit", (e) => {
  e.preventDefault();
  askQuestion(questionInput.value);
});

// Enter submits, Shift+Enter inserts a newline.
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    askForm.requestSubmit();
  }
});

// Minimal auto-grow so multi-line questions are easier to write on mobile.
function autoGrow() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${questionInput.scrollHeight}px`;
}
questionInput.addEventListener("input", autoGrow);

const charCount = document.getElementById("char-count");
const MAX_QUESTION_CHARS = Number(questionInput.maxLength) || 1000;

function syncQuestionState() {
  const length = questionInput.value.length;
  askBtn.disabled = questionInput.value.trim() === "" || (loadedDocs.length > 0 && includedDocIds().length === 0);
  charCount.hidden = length < MAX_QUESTION_CHARS * 0.8;
  charCount.textContent = `${length} / ${MAX_QUESTION_CHARS}`;
  charCount.classList.toggle("at-limit", length >= MAX_QUESTION_CHARS);
}
questionInput.addEventListener("input", syncQuestionState);

// Restore documents and conversation after a page reload (the session
// cookie outlives the page). Sources aren't kept server-side, so restored
// answers show their citations without the passage list.
(async function restoreSession() {
  const data = await api("/api/session");
  if (data.error || !data.documents || data.documents.length === 0) return;
  showView("chat");
  renderDocuments(data.documents);
  let lastQuestion = null;
  for (const turn of data.history) {
    lastQuestion = addUser(turn.question);
    showAnswer(addNote(""), turn.answer, []);
    transcript.push({ question: turn.question, answer: turn.answer, sources: [] });
  }
  syncExport();
  if (lastQuestion) scrollToStart(lastQuestion);
  else addNote("Your documents are still loaded. Ask anything about them.");
})();

// ---------- v2: stop, export, keyboard, drop anywhere ----------

stopBtn.addEventListener("click", stopAnswer);

function syncExport() {
  exportBtn.disabled = transcript.length === 0;
}

/** Download the conversation as Markdown, each answer with its sources. */
function exportConversation() {
  const date = new Date().toISOString().slice(0, 10);
  const lines = [
    "# Conversation — AI Document Assistant",
    "",
    `Exported ${date}. Documents: ${loadedDocs.map((d) => d.filename).join(", ") || "none"}.`,
  ];
  for (const turn of transcript) {
    lines.push("", `## ${turn.question}`, "", plain(turn.answer).trim());
    if (turn.sources.length) {
      lines.push("", "**Sources**", "");
      for (const src of turn.sources) {
        const where = src.doc ? `${src.doc}, page ${src.page}` : `Page ${src.page}`;
        const excerpt = src.text.replace(/\s+/g, " ").trim();
        lines.push(`- ${where}: "${excerpt.length > 200 ? excerpt.slice(0, 200) + "…" : excerpt}"`);
      }
    }
  }
  const blob = new Blob([lines.join("\n") + "\n"], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `conversation-${date}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
exportBtn.addEventListener("click", exportConversation);

// "/" jumps to the question box (unless already typing); Esc stops an answer.
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && busy) {
    stopAnswer();
    return;
  }
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if (e.key === "/" && !typing && document.body.dataset.view === "chat" && !questionInput.disabled) {
    e.preventDefault();
    questionInput.focus();
  }
});

// Drop a PDF anywhere on the page. On the start screen it becomes the first
// document; in the conversation it's added. Dropping elsewhere never makes the
// browser navigate away to the PDF.
let dragDepth = 0;
function hasFiles(e) {
  return [...(e.dataTransfer?.types || [])].includes("Files");
}
window.addEventListener("dragenter", (e) => {
  if (!hasFiles(e)) return;
  dragDepth += 1;
  if (document.body.dataset.view === "chat") document.body.classList.add("drop-target");
});
window.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) document.body.classList.remove("drop-target");
});
window.addEventListener("dragover", (e) => {
  if (hasFiles(e)) e.preventDefault();
});
window.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("drop-target");
  if (e.target.closest && e.target.closest("#dropzone")) return; // handled by the dropzone itself
  const file = e.dataTransfer.files[0];
  if (!file) return;
  if (document.body.dataset.view === "chat") uploadAdditional(file);
  else if (document.body.dataset.view === "upload") uploadFirst(file);
});
