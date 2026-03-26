const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const chatLog = document.getElementById("chat-log");
const template = document.getElementById("message-template");
const statusStrip = document.getElementById("status-strip");
const sendBtn = document.getElementById("send-btn");
const hierarchyAutocomplete = document.getElementById("hierarchy-autocomplete");
const hierarchyAutocompleteLabel = document.getElementById("hierarchy-autocomplete-label");
const hierarchyAutocompleteList = document.getElementById("hierarchy-autocomplete-list");

const setupBtn = document.getElementById("setup-btn");
const sessionContextDisplay = document.getElementById("session-context-display");
const sessionRespPill = document.getElementById("session-resp-pill");
const sessionLedgerPill = document.getElementById("session-ledger-pill");
const sessionHierarchyPill = document.getElementById("session-hierarchy-pill");

const history = [];
let pendingHierarchySelection = null;
let isLoading = false;
let sessionContext = { role_id: null, role_name: null, ledger_id: null, ledger_name: null, hierarchy_id: null, hierarchy_name: null };

// ── Chat-based setup flow ──
let setupPhase = null; // null | 'responsibility' | 'ledger'
let setupSelectedResp = null;

function startSetupFlow() {
  setupPhase = 'responsibility';
  setupSelectedResp = null;
  addMessage("assistant", "Type a responsibility name to search:");
  renderSetupAutocomplete("");
  messageInput.focus();
}

function getSetupMatches(inputText) {
  const normalized = normalizeText(inputText);
  if (setupPhase === 'responsibility') {
    const items = window.LEDGER_DATA?.responsibilities || [];
    if (!normalized) return items.slice(0, 8);
    return items.filter(r => normalizeText(r.name).includes(normalized)).slice(0, 8);
  }
  if (setupPhase === 'ledger' && setupSelectedResp) {
    const items = setupSelectedResp.ledgers || [];
    if (!normalized) return items.slice(0, 8);
    return items.filter(l => normalizeText(l.name).includes(normalized)).slice(0, 8);
  }
  return [];
}

function renderSetupAutocomplete(inputText) {
  if (!setupPhase) { clearHierarchyAutocomplete(); return; }
  const matches = getSetupMatches(inputText);
  hierarchyAutocompleteLabel.textContent = setupPhase === 'responsibility'
    ? "Select a responsibility"
    : "Select a ledger";
  hierarchyAutocompleteList.innerHTML = "";

  if (!matches.length) {
    hierarchyAutocomplete.hidden = false;
    const empty = document.createElement("p");
    empty.className = "autocomplete-label";
    empty.textContent = "No matches found.";
    hierarchyAutocompleteList.appendChild(empty);
    return;
  }

  matches.forEach((item, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = item.name;
    btn.className = `autocomplete-option${index === 0 ? " active" : ""}`;
    btn.onclick = () => selectSetupItem(item);
    hierarchyAutocompleteList.appendChild(btn);
  });
  hierarchyAutocomplete.hidden = false;
}

function selectSetupItem(item) {
  clearHierarchyAutocomplete();
  messageInput.value = "";
  if (setupPhase === 'responsibility') {
    setupSelectedResp = item;
    addMessage("user", item.name);
    setupPhase = 'ledger';
    addMessage("assistant", `Got it. Now type a ledger name for "${item.name}":`);
    renderSetupAutocomplete("");
  } else if (setupPhase === 'ledger') {
    addMessage("user", item.name);
    sessionContext = { role_id: setupSelectedResp.id, role_name: setupSelectedResp.name, ledger_id: item.id, ledger_name: item.name };
    setupPhase = null;
    setupSelectedResp = null;
    updateSessionDisplay();
    addMessage("assistant", `All set! Using ${sessionContext.role_name} / ${item.name}. You can now ask your questions.`);
  }
  messageInput.focus();
}

function updateSessionDisplay() {
  if (sessionContext.ledger_id) {
    sessionRespPill.textContent = sessionContext.role_name || "Role selected";
    sessionLedgerPill.textContent = sessionContext.ledger_name || "Ledger selected";
    sessionContextDisplay.hidden = false;
    setupBtn.classList.add("setup-btn-active");
  } else {
    sessionContextDisplay.hidden = true;
    setupBtn.classList.remove("setup-btn-active");
  }
  if (sessionContext.hierarchy_id && sessionHierarchyPill) {
    sessionHierarchyPill.textContent = sessionContext.hierarchy_name || `Hierarchy ${sessionContext.hierarchy_id}`;
    sessionHierarchyPill.hidden = false;
  } else if (sessionHierarchyPill) {
    sessionHierarchyPill.hidden = true;
  }
}

setupBtn.addEventListener("click", startSetupFlow);

// ── Auto-grow textarea ──
messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
  if (setupPhase) {
    renderSetupAutocomplete(messageInput.value);
  } else if (pendingHierarchySelection) {
    renderHierarchyAutocomplete(messageInput.value);
  }
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

  // Allow user to reset hierarchy by saying "change hierarchy" etc.
  const changeHierarchyRequest = /change\s+(account\s+)?hierarchy|switch\s+(account\s+)?hierarchy|reset\s+hierarchy/i.test(prompt);
  if (changeHierarchyRequest) {
    sessionContext.hierarchy_id = null;
    sessionContext.hierarchy_name = null;
  }

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
        session_hierarchy_id: sessionContext.hierarchy_id,
        session_ledger_id: sessionContext.ledger_id,
        session_ledger_name: sessionContext.ledger_name,
        session_role_id: sessionContext.role_id,
        session_role_name: sessionContext.role_name,
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
      // If a hierarchy was just selected, persist it in session context
      if (effectiveHierarchyId && !sessionContext.hierarchy_id) {
        const selected = pendingHierarchySelection?.options?.find(o => o.id === effectiveHierarchyId)
          || (selectedHierarchy) || { id: effectiveHierarchyId, name: `Hierarchy ${effectiveHierarchyId}` };
        sessionContext.hierarchy_id = effectiveHierarchyId;
        sessionContext.hierarchy_name = selected.name || `Hierarchy ${effectiveHierarchyId}`;
        updateSessionDisplay();
      }
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
  if (!prompt) return;
  if (setupPhase) {
    const matches = getSetupMatches(prompt);
    if (matches.length > 0) selectSetupItem(matches[0]);
    messageInput.value = "";
    return;
  }
  await sendMessage(prompt);
});

loadHealth();
