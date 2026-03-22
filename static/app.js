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
    `OpenAI key: ${health.openai_configured ? "configured" : "missing"}`,
    `Model: ${health.openai_model}`,
    `DB: ${health.db_connected ? "connected" : "unavailable"}`,
  ];

  if (health.db_error) {
    items.push(`DB error: ${health.db_error}`);
  }

  statusStrip.innerHTML = items
    .map((item) => `<span class="status-pill">${item}</span>`)
    .join("");
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

async function sendMessage(prompt) {
  addMessage("user", prompt);
  history.push({ role: "user", content: prompt });
  messageInput.value = "";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: prompt, history }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Request failed.");
    }

    addMessage("assistant", payload.reply);
    history.push({ role: "assistant", content: payload.reply });
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
