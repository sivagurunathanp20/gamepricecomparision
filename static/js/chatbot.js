/* ============================================================
   GameVault — Vault Chatbot 2.0
   Advanced Assistant Widget — Rich Cards, Multi-Prompt NLP & AI
   ============================================================ */

(function () {
  "use strict";

  const SESSION_KEY = "gv_chat_history_v2";
  const MAX_HISTORY = 40;

  // ── DOM refs ────────────────────────────────────────────────
  let fab, badgeEl, panel, messagesEl, suggestionsEl, inputEl, sendBtn, closeBtn, clearBtn, expandBtn;
  let isMuted = false;

  // ── Subtle Audio Synthesizer (Zero asset dependency) ────────
  function playBeep(type) {
    if (isMuted) return;
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      if (type === "send") {
        osc.frequency.setValueAtTime(440, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.08);
        gain.gain.setValueAtTime(0.04, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
        osc.start();
        osc.stop(ctx.currentTime + 0.08);
      } else if (type === "receive") {
        osc.frequency.setValueAtTime(600, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(900, ctx.currentTime + 0.12);
        gain.gain.setValueAtTime(0.05, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.14);
        osc.start();
        osc.stop(ctx.currentTime + 0.14);
      }
    } catch (_) {}
  }

  // ── Markdown Parser ─────────────────────────────────────────
  function renderMarkdown(text) {
    if (!text) return "";
    let parsed = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/~~(.+?)~~/g, "<del>$1</del>")
      .replace(/`(.+?)`/g, "<code>$1</code>")
      .replace(/\[(.+?)\]\((https?:\/\/[^\s]+|\/[^\s]*)\)/g, '<a href="$2" target="_blank" rel="noopener" class="gv-chat-inline-link">$1</a>');

    // Convert bullet lists
    parsed = parsed.replace(/^• (.+)$/gm, '<li class="gv-bullet">$1</li>');
    parsed = parsed.replace(/^(<li class="gv-bullet">.+<\/li>(\n|$))+/gm, '<ul class="gv-list">$&</ul>');

    // Convert newlines
    parsed = parsed.replace(/\n/g, "<br>");
    return parsed;
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  // ── Session Storage ─────────────────────────────────────────
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

  // ── Rich Game Card Creator ──────────────────────────────────
  function createGameCard(game) {
    const card = document.createElement("div");
    card.className = "gv-game-card";

    const imageSrc = game.image || "/static/img/placeholder.svg";
    const discountBadge = game.discount_percent > 0
      ? `<span class="gv-card-badge-discount">-${game.discount_percent}%</span>`
      : "";

    const freeBadge = game.is_free
      ? `<span class="gv-card-badge-free">FREE</span>`
      : "";

    let priceHtml = "";
    if (game.is_free) {
      priceHtml = `<span class="gv-card-price gv-card-price--free">FREE</span>`;
    } else if (game.discount_percent > 0 && game.formatted_original_price) {
      priceHtml = `
        <div class="gv-card-price-group">
          <span class="gv-card-price-old">${game.formatted_original_price}</span>
          <span class="gv-card-price-now">${game.formatted_price}</span>
        </div>
      `;
    } else {
      priceHtml = `<span class="gv-card-price-now">${game.formatted_price || "Check Store"}</span>`;
    }

    const ratingHtml = game.rating
      ? `<span class="gv-card-rating"><i class="fa-solid fa-star"></i> ${game.rating}</span>`
      : "";

    const metacriticHtml = game.metacritic
      ? `<span class="gv-card-metacritic" title="Metacritic Score">${game.metacritic}</span>`
      : "";

    const storeBadge = game.store
      ? `<span class="gv-card-store" style="--store-color: ${game.store_color || '#00f5ff'}">${game.store}</span>`
      : "";

    card.innerHTML = `
      <div class="gv-card-thumb">
        <img src="${imageSrc}" alt="${game.title}" loading="lazy" onerror="this.src='/static/img/placeholder.svg'">
        ${discountBadge}
        ${freeBadge}
      </div>
      <div class="gv-card-body">
        <div class="gv-card-header">
          <a href="${game.details_url || '#'}" class="gv-card-title" title="${game.title}">${game.title}</a>
          <div class="gv-card-meta">
            ${storeBadge}
            ${ratingHtml}
            ${metacriticHtml}
          </div>
        </div>
        <div class="gv-card-footer">
          ${priceHtml}
          <div class="gv-card-buttons">
            <a href="${game.details_url || '#'}" class="gv-card-btn gv-card-btn--primary">
              Details <i class="fa-solid fa-arrow-right"></i>
            </a>
            ${game.store_url && game.store_url !== '#' && game.store_url !== game.details_url ? `
              <a href="${game.store_url}" target="_blank" rel="noopener" class="gv-card-btn gv-card-btn--store" title="Go to ${game.store}">
                <i class="fa-solid fa-up-right-from-square"></i>
              </a>
            ` : ''}
          </div>
        </div>
      </div>
    `;

    return card;
  }

  // ── Message Bubbles ─────────────────────────────────────────
  function createBubble(role, html, links, games) {
    const wrap = document.createElement("div");
    wrap.className = `gv-msg gv-msg--${role}`;

    const bubble = document.createElement("div");
    bubble.className = "gv-bubble";
    bubble.innerHTML = html;
    wrap.appendChild(bubble);

    // Render Rich Game Cards if available
    if (games && games.length) {
      const cardsWrap = document.createElement("div");
      cardsWrap.className = "gv-cards-grid";
      games.forEach((g) => {
        if (g && g.title) {
          cardsWrap.appendChild(createGameCard(g));
        }
      });
      wrap.appendChild(cardsWrap);
    }

    // Render Links / Chips
    if (links && links.length) {
      const chipWrap = document.createElement("div");
      chipWrap.className = "gv-chips";
      links.forEach((lnk) => {
        if (!lnk.url) return;
        const a = document.createElement("a");
        a.className = "gv-chip";
        a.href = lnk.url;
        a.textContent = lnk.label || "View";
        chipWrap.appendChild(a);
      });
      wrap.appendChild(chipWrap);
    }

    return wrap;
  }

  function appendMessage(role, text, links, games) {
    const el = createBubble(role, renderMarkdown(text), links, games);
    messagesEl.appendChild(el);
    requestAnimationFrame(() => el.classList.add("gv-msg--visible"));
    scrollToBottom();
    return el;
  }

  function showTyping() {
    const el = document.createElement("div");
    el.className = "gv-msg gv-msg--bot gv-msg--typing gv-msg--visible";
    el.innerHTML = `
      <div class="gv-bubble">
        <span class="gv-dot"></span>
        <span class="gv-dot"></span>
        <span class="gv-dot"></span>
      </div>
    `;
    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
  }

  // ── Suggestions Management ──────────────────────────────────
  function updateSuggestions(prompts) {
    if (!suggestionsEl) return;
    if (!prompts || !prompts.length) {
      prompts = ["🔥 Best Deals", "🆓 Free Games", "💰 Under $10", "⭐ Top Rated", "🎯 My Wishlist", "🎲 Surprise Me"];
    }

    suggestionsEl.innerHTML = "";
    prompts.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "gv-sug-btn";
      btn.textContent = p;
      btn.setAttribute("data-query", p);
      btn.addEventListener("click", () => {
        inputEl.value = p;
        sendMessage();
      });
      suggestionsEl.appendChild(btn);
    });
  }

  // ── Restore History ─────────────────────────────────────────
  function restoreHistory() {
    const history = loadHistory();
    if (!history.length) {
      showWelcome();
      return;
    }

    history.forEach(({ role, text, links, games }) => {
      const el = createBubble(role, renderMarkdown(text), links, games);
      el.classList.add("gv-msg--visible");
      messagesEl.appendChild(el);
    });
    scrollToBottom();
  }

  function showWelcome() {
    messagesEl.innerHTML = "";
    const welcome =
      "👋 **Hi! I'm Vault**, your AI deal-hunting assistant.\n" +
      "Ask me anything about game deals, check prices under a budget, compare titles, or see what's trending!";
    appendMessage("bot", welcome, [
      { label: "🔥 Top Deals", url: "/deals" },
      { label: "🆓 Freebies", url: "/deals/free" },
      { label: "📊 Compare", url: "/compare" },
    ]);
    updateSuggestions([
      "🔥 Best Deals",
      "🆓 Free Games",
      "💰 Games under $10",
      "⭐ Top Rated Games",
      "🎯 Check My Wishlist",
      "🎲 Surprise Me with a Game"
    ]);
  }

  // ── Send Message ────────────────────────────────────────────
  async function sendMessage() {
    const raw = inputEl.value.trim();
    if (!raw) return;

    inputEl.value = "";
    inputEl.disabled = true;
    sendBtn.disabled = true;
    playBeep("send");

    // User bubble
    appendMessage("user", raw, [], []);

    // Snapshot prior history for conversation context
    const priorHistory = loadHistory().slice(-8).map(({ role, text }) => ({ role, text }));

    // Save user turn
    const history = loadHistory();
    history.push({ role: "user", text: raw, links: [], games: [] });
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

      if (!res.ok) throw new Error("Server response was not ok");

      const data = await res.json();
      const reply = data.reply || "I couldn't find any information for that.";
      const links = data.links || [];
      const games = data.games || [];
      const suggestedPrompts = data.suggested_prompts || [];

      playBeep("receive");
      appendMessage("bot", reply, links, games);

      // Save bot turn
      history.push({ role: "bot", text: reply, links, games });
      saveHistory(history);

      // Update suggestion pills
      if (suggestedPrompts.length) {
        updateSuggestions(suggestedPrompts);
      }
    } catch (err) {
      typingEl.remove();
      const errText = "⚠️ Unable to connect to Vault right now. Please check your network and try again!";
      appendMessage("bot", errText, [
        { label: "🔥 Browse Deals Directly", url: "/deals" }
      ]);
    } finally {
      inputEl.disabled = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  // ── Open / Close / Toggle ───────────────────────────────────
  function openPanel() {
    panel.classList.add("gv-chat--open");
    fab.classList.add("gv-fab--hidden");
    if (badgeEl) badgeEl.style.display = "none";
    inputEl.focus();
    scrollToBottom();
  }

  function closePanel() {
    panel.classList.remove("gv-chat--open");
    fab.classList.remove("gv-fab--hidden");
  }

  function toggleExpand() {
    const isExpanded = panel.classList.toggle("gv-chat--expanded");
    const icon = expandBtn.querySelector("i");
    if (icon) {
      icon.className = isExpanded ? "fa-solid fa-compress" : "fa-solid fa-expand";
    }
    scrollToBottom();
  }

  function clearChat() {
    sessionStorage.removeItem(SESSION_KEY);
    showWelcome();
  }

  // ── Init ─────────────────────────────────────────────────────
  function init() {
    fab = document.getElementById("gvChatFab");
    badgeEl = document.getElementById("gvChatBadge");
    panel = document.getElementById("gvChatPanel");
    messagesEl = document.getElementById("gvChatMessages");
    suggestionsEl = document.getElementById("gvChatSuggestions");
    inputEl = document.getElementById("gvChatInput");
    sendBtn = document.getElementById("gvChatSend");
    closeBtn = document.getElementById("gvChatClose");
    clearBtn = document.getElementById("gvChatClear");
    expandBtn = document.getElementById("gvChatExpand");

    if (!fab || !panel) return;

    restoreHistory();

    fab.addEventListener("click", openPanel);
    closeBtn.addEventListener("click", closePanel);
    if (clearBtn) clearBtn.addEventListener("click", clearChat);
    if (expandBtn) expandBtn.addEventListener("click", toggleExpand);

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      } else if (e.key === "Escape") {
        closePanel();
      }
    });

    // Handle suggestion buttons click (event delegation)
    if (suggestionsEl) {
      suggestionsEl.addEventListener("click", (e) => {
        const btn = e.target.closest(".gv-sug-btn");
        if (btn) {
          const query = btn.getAttribute("data-query");
          if (query) {
            inputEl.value = query;
            sendMessage();
          }
        }
      });
    }

    // Keyboard shortcut to close on Escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && panel.classList.contains("gv-chat--open")) {
        closePanel();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
