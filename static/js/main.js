// ===================================================================
// GameVault — main.js
// Theme toggle, AJAX live search, countdown timers, wishlist actions
// ===================================================================

// Global Image Fallback Handler: catch any broken images across the whole app
window.addEventListener(
  "error",
  (e) => {
    if (e.target && e.target.tagName === "IMG") {
      const img = e.target;
      if (!img.dataset.fallbackStep) {
        img.dataset.fallbackStep = "1";
        if (img.src && img.src.includes("library_600x900.jpg")) {
          img.src = img.src.replace("library_600x900.jpg", "header.jpg");
        } else {
          img.src = "/static/img/placeholder.svg";
        }
      } else if (img.dataset.fallbackStep === "1") {
        img.dataset.fallbackStep = "2";
        img.src = "/static/img/placeholder.svg";
      }
    }
  },
  true
);

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initNavSearch();
  initCountdowns();
  initWishlistButtons();
  autoDismissToasts();
});

// ---------------- Theme (dark / light) ----------------
function initTheme() {
  const root = document.documentElement;
  const saved = localStorage.getItem("gv-theme") || "dark";
  root.setAttribute("data-theme", saved);
  updateThemeIcon(saved);

  const btn = document.getElementById("themeToggleBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const current = root.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("gv-theme", next);
    updateThemeIcon(next);
  });
}

function updateThemeIcon(theme) {
  const icon = document.getElementById("themeIcon");
  if (!icon) return;
  icon.className = theme === "dark" ? "fa-solid fa-moon" : "fa-solid fa-sun";
}

// ---------------- Navbar live search ----------------
function initNavSearch() {
  const input = document.getElementById("navSearchInput");
  const results = document.getElementById("navSearchResults");
  if (!input || !results) return;

  let debounceTimer;
  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length < 2) {
      results.classList.add("d-none");
      results.innerHTML = "";
      return;
    }
    debounceTimer = setTimeout(() => runSearch(q), 250);
  });

  document.addEventListener("click", (e) => {
    if (!results.contains(e.target) && e.target !== input) {
      results.classList.add("d-none");
    }
  });

  function runSearch(q) {
    fetch(`/api/search?q=${encodeURIComponent(q)}`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.length) {
          results.innerHTML = `<div class="p-3 text-muted small">No games found.</div>`;
        } else {
          results.innerHTML = data
            .map(
              (g) => `
              <a href="/game/${g.slug}" class="search-result-item text-decoration-none">
                <img src="${g.cover_image}" alt="">
                <div>
                  <div class="fw-semibold">${g.title}</div>
                  <div class="small text-muted">${g.price}</div>
                </div>
              </a>`
            )
            .join("");
        }
        results.classList.remove("d-none");
      })
      .catch(() => {
        results.classList.add("d-none");
      });
  }
}

// ---------------- Countdown timers ----------------
function initCountdowns() {
  const boxes = document.querySelectorAll("[data-countdown]");
  if (!boxes.length) return;

  function tick() {
    boxes.forEach((box) => {
      const target = new Date(box.getAttribute("data-countdown")).getTime();
      const now = Date.now();
      const diff = target - now;

      if (diff <= 0) {
        box.innerHTML = `<span class="badge bg-secondary">Offer ended</span>`;
        return;
      }

      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
      const mins = Math.floor((diff / (1000 * 60)) % 60);
      const secs = Math.floor((diff / 1000) % 60);

      box.innerHTML = `
        <div class="countdown-unit"><span class="num">${days}</span><span class="lbl">Days</span></div>
        <div class="countdown-unit"><span class="num">${hours}</span><span class="lbl">Hrs</span></div>
        <div class="countdown-unit"><span class="num">${mins}</span><span class="lbl">Min</span></div>
        <div class="countdown-unit"><span class="num">${secs}</span><span class="lbl">Sec</span></div>
      `;
    });
  }

  tick();
  setInterval(tick, 1000);
}

// ---------------- Wishlist add (AJAX heart buttons) ----------------
function initWishlistButtons() {
  document.querySelectorAll(".wishlist-heart[data-game-id]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const gameId = btn.getAttribute("data-game-id");

      fetch(`/wishlist/add/${gameId}`, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      })
        .then((r) => {
          if (r.status === 401 || r.redirected) {
            showToast("Please log in to use the wishlist.", "warning");
            return null;
          }
          return r.json();
        })
        .then((data) => {
          if (!data) return;
          btn.classList.add("active");
          showToast(data.message, data.status === "added" ? "success" : "info");
        })
        .catch(() => showToast("Something went wrong.", "danger"));
    });
  });
}

// ---------------- Toasts ----------------
function showToast(message, type = "dark") {
  const area = document.getElementById("jsToastArea");
  if (!area) return;

  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${type} border-0 show mb-2`;
  el.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">${message}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>`;
  area.appendChild(el);

  setTimeout(() => el.remove(), 4000);
}

function autoDismissToasts() {
  document.querySelectorAll(".toast.show").forEach((toast) => {
    setTimeout(() => {
      toast.classList.remove("show");
    }, 4500);
  });
}
