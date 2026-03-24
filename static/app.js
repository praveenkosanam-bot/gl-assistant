const form = document.getElementById("chat-form");
const messageInput = document.getElementById("message");
const chatLog = document.getElementById("chat-log");
const template = document.getElementById("message-template");
const statusStrip = document.getElementById("status-strip");

const history = [];

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

  addMessage("user", prompt);
  // Don't push to history if it's a retry with hierarchyId
  if (!hierarchyId) {
    history.push({ role: "user", content: prompt });
  }
  messageInput.value = "";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        message: prompt, 
        history, 
        provider: provider, 
        api_key: apiKey,
        hierarchy_id: hierarchyId // Pass the selected hierarchy if we have it
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Request failed.");
    }

    addMessage("assistant", payload.reply);
    
    // If the server asked to pick a hierarchy, show buttons
    if (payload.options) {
      const optionsContainer = document.createElement("div");
      optionsContainer.style.marginTop = "10px";
      optionsContainer.style.display = "flex";
      optionsContainer.style.gap = "8px";
      optionsContainer.style.flexWrap = "wrap";
      
      payload.options.forEach(opt => {
        const btn = document.createElement("button");
        btn.textContent = opt.name;
        btn.className = "prompt-chip"; // reuse styles
        btn.onclick = () => sendMessage(prompt, opt.id);
        optionsContainer.appendChild(btn);
      });
      
      const lastMessage = chatLog.lastElementChild;
      lastMessage.querySelector(".message-body").appendChild(optionsContainer);
    } else {
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

document.querySelectorAll(".prompt-chip").forEach((button) => {
  button.addEventListener("click", async () => {
    const prompt = button.dataset.prompt;
    await sendMessage(prompt);
  });
});

loadHealth();
