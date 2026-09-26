/* ============================================================
   GameVault — Vault Chatbot
   Floating assistant widget — talks to /api/chat
   ============================================================ */

(function () {
  "use strict";

  const SESSION_KEY = "gv_chat_history";
  const MAX_HISTORY = 40; // max messages kept in sessionStorage

  // ── DOM refs (set once DOMContentLoaded) ────────────────────
  let fab, panel, messagesEl, inputEl, sendBtn, closeBtn;

  // ── Helpers ─────────────────────────────────────────────────

  /** Convert simple markdown-ish text to HTML (bold, strikethrough, line breaks) */
  function renderMarkdown(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")   // **bold**
      .replace(/~~(.+?)~~/g, "<del>$1</del>")              // ~~strikethrough~~
      .replace(/`(.+?)`/g, "<code>$1</code>")              // `code`
      .replace(/\n/g, "<br>");
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ── Session storage ─────────────────────────────────────────

  function loadHistory() {
    try {
      return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "[]");
    } catch (_) {
      return [];
    }
  }

  function saveHistory(history) {
    try {
      sessionStorage.setItem(
        SESSION_KEY,
        JSON.stringify(history.slice(-MAX_HISTORY))
      );
    } catch (_) {}
  }

  // ── Rendering ───────────────────────────────────────────────

  function createBubble(role, html, links) {
    const wrap = document.createElement("div");
    wrap.className = `gv-msg gv-msg--${role}`;

    const bubble = document.createElement("div");
    bubble.className = "gv-bubble";
    bubble.innerHTML = html;
    wrap.appendChild(bubble);

    if (links && links.length) {
      const chipWrap = document.createElement("div");
      chipWrap.className = "gv-chips";
      links.forEach((lnk) => {
        const a = document.createElement("a");
        a.className = "gv-chip";
        a.href = lnk.url;
        a.textContent = lnk.label;
        chipWrap.appendChild(a);
      });
      wrap.appendChild(chipWrap);
    }

    return wrap;
  }

  function appendMessage(role, text, links) {
    const el = createBubble(role, renderMarkdown(text), links);
    messagesEl.appendChild(el);
    // Animate in
    requestAnimationFrame(() => el.classList.add("gv-msg--visible"));
    scrollToBottom();
    return el;
  }

  function showTyping() {
    const el = document.createElement("div");
    el.className = "gv-msg gv-msg--bot gv-msg--typing gv-msg--visible";
    el.innerHTML = `<div class="gv-bubble"><span class="gv-dot"></span><span class="gv-dot"></span><span class="gv-dot"></span></div>`;
    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
  }

  // ── Restore history ─────────────────────────────────────────

  function restoreHistory() {
    const history = loadHistory();
    history.forEach(({ role, text, links }) => {
      const el = createBubble(role, renderMarkdown(text), links);
      el.classList.add("gv-msg--visible");
      messagesEl.appendChild(el);
    });
    scrollToBottom();
  }

  // ── Send a message ──────────────────────────────────────────

  async function sendMessage() {
    const raw = inputEl.value.trim();
    if (!raw) return;

    inputEl.value = "";
    inputEl.disabled = true;
    sendBtn.disabled = true;

    // User bubble
    appendMessage("user", raw, []);

    // Snapshot prior turns (before this message) to give the AI conversation context
    const priorHistory = loadHistory().slice(-8).map(({ role, text }) => ({ role, text }));

    // Save user turn to history
    const history = loadHistory();
    history.push({ role: "user", text: raw, links: [] });
    saveHistory(history);

    // Typing indicator
    const typingEl = showTyping();

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: raw, history: priorHistory }),
      });

      typingEl.remove();

      if (!res.ok) throw new Error("Server error");

      const data = await res.json();
      const reply = data.reply || "Sorry, I got an empty response!";
      const links = data.links || [];

      appendMessage("bot", reply, links);

      // Save bot turn
      history.push({ role: "bot", text: reply, links });
      saveHistory(history);
    } catch (err) {
      typingEl.remove();
      const errText =
        "⚠️ Couldn't reach the server. Check your connection and try again.";
      appendMessage("bot", errText, []);
    } finally {
      inputEl.disabled = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  // ── Open / close ────────────────────────────────────────────

  function openPanel() {
    panel.classList.add("gv-chat--open");
    fab.classList.add("gv-fab--hidden");
    inputEl.focus();

    // Show welcome only if empty
    if (!messagesEl.children.length) {
      const welcome =
        "👋 Hi! I'm **Vault**, your GameVault assistant.\n" +
        "Ask me about deals, free games, trending titles, or type a game name to look it up!";
      appendMessage("bot", welcome, [
        { label: "🔥 Best Deals", url: "/deals" },
        { label: "🆓 Free Games", url: "/deals/free" },
      ]);
    }
  }

  function closePanel() {
    panel.classList.remove("gv-chat--open");
    fab.classList.remove("gv-fab--hidden");
  }

  // ── Init ─────────────────────────────────────────────────────

  function init() {
    fab = document.getElementById("gvChatFab");
    panel = document.getElementById("gvChatPanel");
    messagesEl = document.getElementById("gvChatMessages");
    inputEl = document.getElementById("gvChatInput");
    sendBtn = document.getElementById("gvChatSend");
    closeBtn = document.getElementById("gvChatClose");

    if (!fab) return; // widget not on page

    restoreHistory();

    fab.addEventListener("click", openPanel);
    closeBtn.addEventListener("click", closePanel);

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
