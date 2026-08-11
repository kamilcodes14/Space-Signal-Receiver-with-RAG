/**
 * Signal Receiver research assistant widget.
 * Drop-in: <script src="/static/chat_widget.js"></script>
 * Talks to POST /api/chat  ->  { message } => { answer, sources }
 *
 * Single file (style injected) so it's a one-line embed in the
 * existing Vercel-hosted page.
 */
(function () {
  const STYLE = `
  .sr-chat-toggle {
    position: fixed; bottom: 24px; right: 24px; z-index: 9999;
    width: 56px; height: 56px; border-radius: 50%;
    background: #0b1220; border: 1px solid #1f3a4d;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; box-shadow: 0 4px 18px rgba(0,0,0,0.45);
  }
  .sr-chat-toggle .sr-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: #4fd1c5; box-shadow: 0 0 0 rgba(79,209,197,0.6);
    animation: sr-pulse 2.2s ease-out infinite;
  }
  @keyframes sr-pulse {
    0%   { box-shadow: 0 0 0 0 rgba(79,209,197,0.55); }
    70%  { box-shadow: 0 0 0 12px rgba(79,209,197,0); }
    100% { box-shadow: 0 0 0 0 rgba(79,209,197,0); }
  }
  .sr-chat-panel {
    position: fixed; bottom: 92px; right: 24px; z-index: 9999;
    width: 340px; max-height: 460px; display: none; flex-direction: column;
    background: #0b1220; border: 1px solid #1f3a4d; border-radius: 10px;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    color: #d7e6ea; overflow: hidden;
  }
  .sr-chat-panel.sr-open { display: flex; }
  .sr-chat-header {
    padding: 10px 14px; border-bottom: 1px solid #1f3a4d;
    font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase;
    color: #4fd1c5;
  }
  .sr-chat-log {
    flex: 1; overflow-y: auto; padding: 12px 14px;
    display: flex; flex-direction: column; gap: 10px; font-size: 13px;
  }
  .sr-msg-user { color: #d7e6ea; }
  .sr-msg-agent { color: #9fb8bf; }
  .sr-msg-user .sr-tag { color: #4fd1c5; }
  .sr-msg-agent .sr-tag { color: #6b8e94; }
  .sr-tag { font-size: 10px; display: block; margin-bottom: 2px; opacity: 0.8; }
  .sr-sources {
    font-size: 10px; color: #587177; margin-top: 4px;
  }
  .sr-chat-input {
    display: flex; border-top: 1px solid #1f3a4d;
  }
  .sr-chat-input input {
    flex: 1; background: transparent; border: none; outline: none;
    padding: 10px 12px; color: #d7e6ea; font: inherit; font-size: 13px;
  }
  .sr-chat-input button {
    background: transparent; border: none; color: #4fd1c5;
    padding: 0 14px; cursor: pointer; font: inherit; font-size: 13px;
  }
  `;

  const styleEl = document.createElement("style");
  styleEl.textContent = STYLE;
  document.head.appendChild(styleEl);

  const toggle = document.createElement("div");
  toggle.className = "sr-chat-toggle";
  toggle.innerHTML = '<div class="sr-dot"></div>';
  document.body.appendChild(toggle);

  const panel = document.createElement("div");
  panel.className = "sr-chat-panel";
  panel.innerHTML = `
    <div class="sr-chat-header">signal // research assistant</div>
    <div class="sr-chat-log"></div>
    <div class="sr-chat-input">
      <input type="text" placeholder="ask about a paper or a run..." />
      <button type="button">send</button>
    </div>
  `;
  document.body.appendChild(panel);

  const log = panel.querySelector(".sr-chat-log");
  const input = panel.querySelector("input");
  const sendBtn = panel.querySelector("button");

  toggle.addEventListener("click", () => {
    panel.classList.toggle("sr-open");
    if (panel.classList.contains("sr-open")) input.focus();
  });

  function appendMessage(role, text, sources) {
    const div = document.createElement("div");
    div.className = role === "user" ? "sr-msg-user" : "sr-msg-agent";
    const tag = document.createElement("span");
    tag.className = "sr-tag";
    tag.textContent = role === "user" ? "you" : "assistant";
    div.appendChild(tag);
    div.appendChild(document.createTextNode(text));
    if (sources && sources.length) {
      const src = document.createElement("div");
      src.className = "sr-sources";
      src.textContent = "sources: " + sources.join(", ");
      div.appendChild(src);
    }
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  async function send() {
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    appendMessage("user", message);

    const thinking = document.createElement("div");
    thinking.className = "sr-msg-agent";
    thinking.textContent = "searching...";
    log.appendChild(thinking);
    log.scrollTop = log.scrollHeight;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      thinking.remove();
      if (data.error) {
        appendMessage("agent", "error: " + data.error);
      } else {
        appendMessage("agent", data.answer, data.sources);
      }
    } catch (err) {
      thinking.remove();
      appendMessage("agent", "connection error - is the server running?");
    }
  }

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });
})();
