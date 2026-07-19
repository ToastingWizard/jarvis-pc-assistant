/* ============================================================
   NaiTRO web UI — front-end logic.
   Talks to Python through window.pywebview.api (see webview_ui.py).
   Falls back to a small in-browser mock if opened outside pywebview,
   so the UI can be previewed in a normal browser too.
   ============================================================ */

const hasApi = () => typeof window.pywebview !== "undefined" && window.pywebview.api;

const mockConfig = {
  wake_phrase: "hey naitro",
  user_title: "sir",
  allow_push: true,
  speak_responses: true,
  apps: { "Notepad": {}, "Calculator": {}, "Chrome": {}, "Spotify": {} },
  folders: { "Downloads": {}, "Desktop": {}, "Documents": {} },
  websites: { "YouTube": {}, "Google": {}, "Netflix": {}, "ChatGPT": {} },
  modes: { "Chill Mode": { desc: "2 steps" }, "Study Mode": { desc: "2 steps" } },
};

async function api(name, ...args) {
  if (hasApi()) {
    try { return await window.pywebview.api[name](...args); }
    catch (e) { console.error(name, e); return null; }
  }
  // browser preview fallback
  if (name === "get_dashboard_data") return mockConfig;
  if (name === "get_status") return { speaking: false, listening: false, conversation_active: false };
  console.log("[mock api]", name, args);
  return { ok: true, message: "(preview mode — no engine attached)" };
}

/* ---------------- clock ---------------- */
function tickClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2, "0");
  document.getElementById("clock").textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  const days = ["SUNDAY","MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY"];
  const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
  document.getElementById("dateStr").textContent =
    `${days[now.getDay()]}, ${months[now.getMonth()]} ${now.getDate()}, ${now.getFullYear()}`;
}
setInterval(tickClock, 1000);
tickClock();

/* ---------------- nav switching ---------------- */
function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`)?.classList.add("active");
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === name));
}
document.querySelectorAll("[data-view]").forEach(el => {
  el.addEventListener("click", () => showView(el.dataset.view));
});

/* ---------------- particle field ---------------- */
(function particles() {
  const canvas = document.getElementById("particles");
  const ctx = canvas.getContext("2d");
  let w, h, points;
  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
    const count = Math.floor((w * h) / 26000);
    points = Array.from({ length: count }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      r: Math.random() * 1.4 + .3,
      vx: (Math.random() - .5) * .08, vy: (Math.random() - .5) * .08,
      a: Math.random() * .5 + .15,
    }));
  }
  function frame() {
    ctx.clearRect(0, 0, w, h);
    for (const p of points) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = w; if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h; if (p.y > h) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(196,150,255,${p.a})`;
      ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  window.addEventListener("resize", resize);
  resize(); frame();
})();

/* ---------------- orb rings rotation ---------------- */
(function orbRings() {
  const outer = document.querySelector(".ring-outer");
  const mid = document.querySelector(".ring-mid");
  const inner = document.querySelector(".ring-inner");
  const listen = document.querySelector(".ring-listen");
  let a1 = 0, a2 = 0, a3 = 0, a4 = 0;
  function frame() {
    a1 += 0.06; a2 -= 0.12; a3 += 0.03; a4 += 0.25;
    outer.setAttribute("transform", `rotate(${a1})`);
    mid.setAttribute("transform", `rotate(${a2})`);
    inner.setAttribute("transform", `rotate(${a3})`);
    listen.setAttribute("transform", `rotate(${a4})`);
    requestAnimationFrame(frame);
  }
  frame();
})();

/* ---------------- icon palette for generated tiles ---------------- */
const PALETTE = ["#a855f7","#7c3aed","#c026d3","#8b5cf6","#6d28d9","#9333ea","#a21caf","#7e22ce"];
function colorFor(name) {
  let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
function initialsFor(name) {
  const parts = name.trim().split(/\s+/);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase();
}

function makeTile(name, kind) {
  const el = document.createElement("button");
  el.className = "tile";
  el.innerHTML = `
    <div class="tile-icon" style="background:linear-gradient(135deg, ${colorFor(name)}, #1a1024)">${initialsFor(name)}</div>
    <div class="tile-name">${name}</div>`;
  el.addEventListener("click", () => runTile(kind, name, el));
  return el;
}

async function runTile(kind, name, el) {
  el.style.transform = "scale(.94)";
  setTimeout(() => (el.style.transform = ""), 150);
  // The engine announces what it's doing via respond(), which arrives
  // through window.naitroLog — no need to push a message here too.
  await api("run_action", kind, name);
}

function makeModeCard(name, desc) {
  const el = document.createElement("button");
  el.className = "mode-card";
  el.innerHTML = `
    <div class="mode-icon">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/></svg>
    </div>
    <div>
      <div class="mode-title">${name}</div>
      <div class="mode-desc">${desc || "Run mode"}</div>
    </div>
    <div class="live-dot" style="display:none"></div>`;
  el.addEventListener("click", async () => {
    const dot = el.querySelector(".live-dot");
    dot.style.display = "block";
    await api("run_action", "mode", name);
    setTimeout(() => (dot.style.display = "none"), 1600);
  });
  return el;
}

/* ---------------- populate dashboard from config ---------------- */
async function loadDashboard() {
  const cfg = await api("get_dashboard_data");
  if (!cfg) return;

  const fill = (id, kind, entries, full) => {
    const el = document.getElementById(id);
    el.innerHTML = "";
    const names = Object.keys(entries || {});
    if (!names.length) {
      el.innerHTML = `<div class="empty-hint">Nothing here yet — add one from Settings or your config file.</div>`;
      return;
    }
    const shown = full ? names : names.slice(0, 6);
    shown.forEach(n => el.appendChild(makeTile(n, kind)));
  };

  fill("dashApps", "app", cfg.apps, false);
  fill("dashFolders", "folder", cfg.folders, false);
  fill("dashWebsites", "website", cfg.websites, false);
  fill("appsFull", "app", cfg.apps, true);
  fill("foldersFull", "folder", cfg.folders, true);
  fill("websitesFull", "website", cfg.websites, true);

  const modeWrap = document.getElementById("dashModes");
  const modeWrapFull = document.getElementById("modesFull");
  modeWrap.innerHTML = ""; modeWrapFull.innerHTML = "";
  const modeNames = Object.keys(cfg.modes || {});
  if (!modeNames.length) {
    modeWrap.innerHTML = `<div class="empty-hint">No modes configured yet.</div>`;
  } else {
    modeNames.forEach(n => {
      modeWrap.appendChild(makeModeCard(n, cfg.modes[n]?.desc));
      modeWrapFull.appendChild(makeModeCard(n, cfg.modes[n]?.desc));
    });
  }

  document.getElementById("wakePhraseSub").textContent = cfg.wake_phrase || "hey naitro";
  setToggle("toggleAllowPush", !!cfg.allow_push);
  setToggle("toggleSpeak", !!cfg.speak_responses);
}

/* ---------------- log feed ---------------- */
function pushLog(who, text) {
  const feed = document.getElementById("logFeed");
  const line = document.createElement("div");
  line.className = "log-line";
  line.innerHTML = `<span class="who">${who}:</span> ${text}`;
  feed.appendChild(line);
  while (feed.children.length > 6) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
  document.getElementById("heroStatus").textContent = text.length > 46 ? text.slice(0, 46) + "…" : text;
}

/* ---------------- command bar ---------------- */
const cmdInput = document.getElementById("cmdInput");
const cmdSend = document.getElementById("cmdSend");
async function sendCommand() {
  const text = cmdInput.value.trim();
  if (!text) return;
  cmdInput.value = "";
  // engine.run_command() logs both "YOU: ..." and "NaiTRO: ..." lines
  // itself, which stream in through window.naitroLog — see below.
  await api("send_command", text);
}
cmdSend.addEventListener("click", sendCommand);
cmdInput.addEventListener("keydown", e => { if (e.key === "Enter") sendCommand(); });

/* ---------------- voice toggle ---------------- */
let voiceOn = false;
function setToggle(id, on) {
  document.getElementById(id).classList.toggle("on", !!on);
}
async function setVoice(on) {
  voiceOn = on;
  document.getElementById("voicePanel").classList.toggle("listening", on);
  document.getElementById("voiceState").textContent = on ? "LISTENING…" : "OFF";
  document.getElementById("micBtn").classList.toggle("active", on);
  setToggle("toggleVoice", on);
  await api("toggle_voice", on);
}
document.getElementById("voicePanel").addEventListener("click", () => setVoice(!voiceOn));
document.getElementById("micBtn").addEventListener("click", () => setVoice(!voiceOn));
document.getElementById("toggleVoice").addEventListener("click", () => setVoice(!voiceOn));
document.getElementById("toggleSpeak").addEventListener("click", async (e) => {
  const on = !e.currentTarget.classList.contains("on");
  setToggle("toggleSpeak", on);
  await api("set_setting", "speak_responses", on);
});
document.getElementById("toggleAllowPush").addEventListener("click", async (e) => {
  const on = !e.currentTarget.classList.contains("on");
  setToggle("toggleAllowPush", on);
  await api("set_setting", "allow_push", on);
});

/* ---------------- add tile buttons (simple prompt-based add) ---------------- */
function wireAdd(btnId, kind, label) {
  document.getElementById(btnId).addEventListener("click", async () => {
    const name = prompt(`Name for the new ${label}:`);
    if (!name) return;
    const target = prompt(`Target for "${name}" (path, URL, or command):`);
    if (target === null) return;
    const res = await api("add_item", kind, name, target);
    if (res && res.message) pushLog("NaiTRO", res.message);
    loadDashboard();
  });
}
wireAdd("addAppBtn", "app", "app");
wireAdd("addFolderBtn", "folder", "folder");
wireAdd("addWebsiteBtn", "website", "website");

/* ---------------- window controls ---------------- */
document.getElementById("minBtn").addEventListener("click", () => api("minimize"));
document.getElementById("closeBtn").addEventListener("click", () => api("close"));

/* ---------------- live status polling (speaking / listening) ---------------- */
const orb = document.getElementById("orb");
setInterval(async () => {
  const s = await api("get_status");
  if (!s) return;
  orb.classList.toggle("speaking", !!s.speaking);
  orb.classList.toggle("listening", !!s.conversation_active);
  if (s.speaking) document.getElementById("heroStatus").textContent = "SPEAKING…";
  else if (s.conversation_active) document.getElementById("heroStatus").textContent = "LISTENING…";
  else if (document.getElementById("heroStatus").textContent.startsWith("SPEAKING") ||
           document.getElementById("heroStatus").textContent.startsWith("LISTENING"))
    document.getElementById("heroStatus").textContent = "IDLE";
}, 350);

/* ---------------- bridge callback: Python -> JS log push ----------------
   engine.log() emits plain strings like "YOU: open chrome" or
   "NaiTRO: Opening chrome, sir." — split on the first ": " so they land
   in the feed with proper styling. Anything without that shape (stray
   status/debug lines) is shown attributed to NaiTRO. */
window.naitroLog = function (line) {
  const idx = line.indexOf(": ");
  if (idx === -1) { pushLog("NaiTRO", line); return; }
  const who = line.slice(0, idx);
  const text = line.slice(idx + 2);
  pushLog(who === "YOU" ? "You" : who, text);
};

/* ---------------- boot ---------------- */
loadDashboard();
