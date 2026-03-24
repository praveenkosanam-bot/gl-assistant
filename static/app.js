const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const chatLog = document.getElementById("chat-log");
const template = document.getElementById("message-template");
const statusStrip = document.getElementById("status-strip");
const hierarchyAutocomplete = document.getElementById("hierarchy-autocomplete");
const hierarchyAutocompleteLabel = document.getElementById("hierarchy-autocomplete-label");
const hierarchyAutocompleteList = document.getElementById("hierarchy-autocomplete-list");

const history = [];
let pendingHierarchySelection = null;

function normalizeText(text) {
  return (text || "").trim().toLowerCase();
}

function resolveHierarchySelection(followUpText) {
  if (!pendingHierarchySelection) {
    return null;
  }

  const normalized = normalizeText(followUpText);
  if (!normalized) {
    return null;
  }

  const exact = pendingHierarchySelection.options.find((opt) => normalizeText(opt.name) === normalized);
  if (exact) {
    return exact;
  }

  const contains = pendingHierarchySelection.options.find((opt) => {
    const name = normalizeText(opt.name);
    return normalized.includes(name) || name.includes(normalized);
  });
  if (contains) {
    return contains;
  }

  const keywords = normalized
    .replace(/^use\s+(the\s+)?(one\s+)?(with\s+)?/, "")
    .split(/[^a-z0-9]+/)
    .filter(Boolean);

  if (!keywords.length) {
    return null;
  }

  return pendingHierarchySelection.options.find((opt) => {
    const name = normalizeText(opt.name);
    return keywords.every((keyword) => name.includes(keyword));
  }) || null;
}

function getHierarchyMatches(inputText) {
  if (!pendingHierarchySelection) {
    return [];
  }

  const normalized = normalizeText(inputText);
  if (!normalized) {
    return pendingHierarchySelection.options.slice(0, 8);
  }

  return pendingHierarchySelection.options
    .filter((opt) => {
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
  if (!pendingHierarchySelection) {
    clearHierarchyAutocomplete();
    return;
  }

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

function addMessage(role, text) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".message-role").textContent = role;
  node.querySelector(".message-body").textContent = text;
  chatLog.appendChild(node);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderStatus(health) {
  const items = [
    `Dynamic API: configured`,
    `Model: ${health.openai_model}`,
    `DB: ${health.db_connected ? "connected" : "unavailable"}`,
  ];

  if (health.db_error) {
    items.push(`DB error: ${health.db_error}`);
  }

  // Update provider key status in pills
  if (health.openai_key_set) items.push("OpenAI Key: Server-side");
  if (health.anthropic_key_set) items.push("Claude Key: Server-side");
  if (health.gemini_key_set) items.push("Gemini Key: Server-side");

  statusStrip.innerHTML = items
    .map((item) => `<span class="status-pill">${item}</span>`)
    .join("");

  // Update input placeholder based on current provider
  const providerSelect = document.getElementById("provider");
  const apiKeyInput = document.getElementById("api_key");
  
  const updatePlaceholder = () => {
    const p = providerSelect.value;
    const isSet = (p === "openai" && health.openai_key_set) ||
                  (p === "anthropic" && health.anthropic_key_set) ||
                  (p === "gemini" && health.gemini_key_set);
    apiKeyInput.placeholder = isSet ? "Using server-side key (optional override)" : `Enter ${p.charAt(0).toUpperCase() + p.slice(1)} API Key`;
  };

  providerSelect.onchange = updatePlaceholder;
  updatePlaceholder();
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    renderStatus(health);
  } catch (error) {
    statusStrip.innerHTML = `<span class="status-pill">Health check failed</span>`;
  }
}

async function sendMessage(prompt, hierarchyId = null) {
  const provider = document.getElementById("provider") ? document.getElementById("provider").value : "openai";
  const apiKey = document.getElementById("api_key") ? document.getElementById("api_key").value : "";
  const selectedHierarchy = !hierarchyId ? resolveHierarchySelection(prompt) : null;
  const effectiveHierarchyId = hierarchyId ?? selectedHierarchy?.id ?? null;
  const effectivePrompt = effectiveHierarchyId && pendingHierarchySelection ? pendingHierarchySelection.originalPrompt : prompt;

  addMessage("user", prompt);
  // Don't push hierarchy follow-up text into history; resend the original question with hierarchy_id.
  if (!effectiveHierarchyId) {
    history.push({ role: "user", content: prompt });
  }
  messageInput.value = "";
  clearHierarchyAutocomplete();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        message: effectivePrompt, 
        history, 
        provider: provider, 
        api_key: apiKey,
        hierarchy_id: effectiveHierarchyId
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Request failed.");
    }

    addMessage("assistant", payload.reply);
    
    // If the server asked to pick a hierarchy, show buttons
    if (payload.options) {
      pendingHierarchySelection = {
        originalPrompt: effectivePrompt,
        options: payload.options,
      };
      renderHierarchyAutocomplete("");
      const optionsContainer = document.createElement("div");
      optionsContainer.style.marginTop = "10px";
      optionsContainer.style.display = "flex";
      optionsContainer.style.gap = "8px";
      optionsContainer.style.flexWrap = "wrap";
      
      payload.options.forEach(opt => {
        const btn = document.createElement("button");
        btn.textContent = opt.name;
        btn.className = "prompt-chip"; // reuse styles
        btn.onclick = () => sendMessage(opt.name, opt.id);
        optionsContainer.appendChild(btn);
      });
      
      const lastMessage = chatLog.lastElementChild;
      lastMessage.querySelector(".message-body").appendChild(optionsContainer);
    } else {
      pendingHierarchySelection = null;
      clearHierarchyAutocomplete();
      history.push({ role: "assistant", content: payload.reply });
    }
  } catch (error) {
    addMessage("assistant", `Request failed: ${error.message}`);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = messageInput.value.trim();
  if (!prompt) {
    return;
  }
  await sendMessage(prompt);
});

messageInput.addEventListener("input", () => {
  if (!pendingHierarchySelection) {
    return;
  }
  renderHierarchyAutocomplete(messageInput.value);
});

document.querySelectorAll(".prompt-chip").forEach((button) => {
  button.addEventListener("click", async () => {
    const prompt = button.dataset.prompt;
    await sendMessage(prompt);
  });
});

loadHealth();
