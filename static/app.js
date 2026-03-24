const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const chatLog = document.getElementById("chat-log");
const template = document.getElementById("message-template");
const statusStrip = document.getElementById("status-strip");
const sendBtn = document.getElementById("send-btn");
const hierarchyAutocomplete = document.getElementById("hierarchy-autocomplete");
const hierarchyAutocompleteLabel = document.getElementById("hierarchy-autocomplete-label");
const hierarchyAutocompleteList = document.getElementById("hierarchy-autocomplete-list");

const history = [];
let pendingHierarchySelection = null;
let isLoading = false;

// ── Auto-grow textarea ──
messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
  if (pendingHierarchySelection) renderHierarchyAutocomplete(messageInput.value);
});

// ── Send on Enter (Shift+Enter for newline) ──
messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

// ── Hierarchy helpers ──
function normalizeText(text) {
  return (text || "").trim().toLowerCase();
}

function resolveHierarchySelection(followUpText) {
  if (!pendingHierarchySelection) return null;
  const normalized = normalizeText(followUpText);
  if (!normalized) return null;

  const exact = pendingHierarchySelection.options.find(opt => normalizeText(opt.name) === normalized);
  if (exact) return exact;

  const contains = pendingHierarchySelection.options.find(opt => {
    const name = normalizeText(opt.name);
    return normalized.includes(name) || name.includes(normalized);
  });
  if (contains) return contains;

  const keywords = normalized
    .replace(/^use\s+(the\s+)?(one\s+)?(with\s+)?/, "")
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
  if (!keywords.length) return null;

  return pendingHierarchySelection.options.find(opt => {
    const name = normalizeText(opt.name);
    return keywords.every(k => name.includes(k));
  }) || null;
}

function getHierarchyMatches(inputText) {
  if (!pendingHierarchySelection) return [];
  const normalized = normalizeText(inputText);
  if (!normalized) return pendingHierarchySelection.options.slice(0, 8);
  return pendingHierarchySelection.options
    .filter(opt => {
      const name = normalizeText(opt.name);
      return name.includes(normalized) || normalized.includes(name);
    })
    .slice(0, 8);
}

function clearHierarchyAutocomplete() {
  hierarchyAutocomplete.hidden = true;
  hierarchyAutocompleteList.innerHTML = "";
}

function renderHierarchyAutocomplete(inputText = "") {
  if (!pendingHierarchySelection) { clearHierarchyAutocomplete(); return; }
  const matches = getHierarchyMatches(inputText);
  hierarchyAutocompleteLabel.textContent = "Select a hierarchy or keep typing to filter";
  hierarchyAutocompleteList.innerHTML = "";

  if (!matches.length) {
    hierarchyAutocomplete.hidden = false;
    const empty = document.createElement("p");
    empty.className = "autocomplete-label";
    empty.textContent = "No matching hierarchy names.";
    hierarchyAutocompleteList.appendChild(empty);
    return;
  }

  matches.forEach((opt, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = opt.name;
    btn.className = `autocomplete-option${index === 0 ? " active" : ""}`;
    btn.onclick = () => {
      messageInput.value = opt.name;
      sendMessage(opt.name, opt.id);
    };
    hierarchyAutocompleteList.appendChild(btn);
  });
  hierarchyAutocomplete.hidden = false;
}

// ── Message rendering ──
function addMessage(role, text) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".message-meta").textContent = role === "user" ? "You" : "GL Connect";
  node.querySelector(".message-bubble").textContent = text;
  chatLog.appendChild(node);
  chatLog.scrollTop = chatLog.scrollHeight;
  return node;
}

function addThinking() {
  const node = template.content.firstElementChild.cloneNode(true);
  node.classList.add("assistant");
  node.querySelector(".message-meta").textContent = "GL Connect";
  node.querySelector(".message-bubble").innerHTML =
    `<div class="thinking-dots"><span></span><span></span><span></span></div>`;
  node.id = "thinking-indicator";
  chatLog.appendChild(node);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function removeThinking() {
  const el = document.getElementById("thinking-indicator");
  if (el) el.remove();
}

function addHierarchyButtons(options, originalPrompt) {
  const last = chatLog.lastElementChild;
  if (!last) return;
  const container = document.createElement("div");
  container.style.cssText = "margin-top:12px; display:flex; flex-wrap:wrap; gap:8px;";
  options.forEach(opt => {
    const btn = document.createElement("button");
    btn.textContent = opt.name;
    btn.className = "prompt-chip";
    btn.onclick = () => sendMessage(opt.name, opt.id);
    container.appendChild(btn);
  });
  last.querySelector(".message-bubble").appendChild(container);
}

// ── Status strip ──
function renderStatus(health) {
  const pills = [];
  if (health.db_connected) {
    pills.push(`<span class="status-pill ok">DB connected</span>`);
  } else {
    pills.push(`<span class="status-pill warn">DB unavailable</span>`);
  }
  if (health.gemini_key_set) {
    pills.push(`<span class="status-pill ok">Gemini ✓</span>`);
  } else {
    pills.push(`<span class="status-pill warn">Gemini key missing</span>`);
  }
  pills.push(`<span class="status-pill">${health.rag_documents_indexed} docs indexed</span>`);
  pills.push(`<span class="status-pill">${health.gemini_model}</span>`);
  statusStrip.innerHTML = pills.join("");
}

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    renderStatus(await res.json());
  } catch {
    statusStrip.innerHTML = `<span class="status-pill warn">Health check failed</span>`;
  }
}

// ── Send ──
function setLoading(on) {
  isLoading = on;
  sendBtn.disabled = on;
  messageInput.disabled = on;
}

async function sendMessage(prompt, hierarchyId = null) {
  if (isLoading) return;

  const selectedHierarchy = !hierarchyId ? resolveHierarchySelection(prompt) : null;
  const effectiveHierarchyId = hierarchyId ?? selectedHierarchy?.id ?? null;
  const effectivePrompt = effectiveHierarchyId && pendingHierarchySelection
    ? pendingHierarchySelection.originalPrompt
    : prompt;

  addMessage("user", prompt);
  if (!effectiveHierarchyId) history.push({ role: "user", content: prompt });

  messageInput.value = "";
  messageInput.style.height = "auto";
  clearHierarchyAutocomplete();
  setLoading(true);
  addThinking();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: effectivePrompt,
        history,
        hierarchy_id: effectiveHierarchyId,
      }),
    });
    const payload = await res.json();
    removeThinking();

    if (!res.ok) throw new Error(payload.error || "Request failed.");

    addMessage("assistant", payload.reply);

    if (payload.options) {
      pendingHierarchySelection = { originalPrompt: effectivePrompt, options: payload.options };
      renderHierarchyAutocomplete("");
      addHierarchyButtons(payload.options, effectivePrompt);
    } else {
      pendingHierarchySelection = null;
      clearHierarchyAutocomplete();
      history.push({ role: "assistant", content: payload.reply });
    }
  } catch (err) {
    removeThinking();
    addMessage("assistant", `Something went wrong: ${err.message}`);
  } finally {
    setLoading(false);
    messageInput.focus();
  }
}

// ── Form submit ──
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const prompt = messageInput.value.trim();
  if (prompt) await sendMessage(prompt);
});

loadHealth();
