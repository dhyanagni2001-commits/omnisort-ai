const API = "http://127.0.0.1:8000";
const WS = "ws://127.0.0.1:8000/ws";

let ws;

function categoryBadge(cat) {
  const cls = (cat || "other").toLowerCase();
  return `<span class="badge ${cls}">${cat || "Other"}</span>`;
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function statusBadge(row) {
  if (row.is_sensitive) return `<span class="badge sensitive">Sensitive</span>`;
  if (row.is_duplicate) return `<span class="badge duplicate">Duplicate</span>`;
  return `<span class="badge">Clean</span>`;
}

function feedIcon(event) {
  if (event.type === "error") return "⚠️";
  if (event.is_sensitive) return "🔴";
  if (event.is_duplicate) return "🟡";
  return "✅";
}

function addFeedItem(event) {
  const list = document.getElementById("feedList");
  const empty = list.querySelector(".empty");
  if (empty) empty.remove();

  const tag = event.is_sensitive
    ? `<span class="feed-tag sensitive">Sensitive</span>`
    : event.is_duplicate
    ? `<span class="feed-tag duplicate">Duplicate</span>`
    : `<span class="feed-tag">${event.category || "Other"}</span>`;

  const item = document.createElement("div");
  item.className = "feed-item";
  item.innerHTML = `
    <span class="feed-icon">${feedIcon(event)}</span>
    <span class="feed-name">${event.filename}</span>
    ${tag}
  `;
  list.insertBefore(item, list.firstChild);

  // Keep max 50 items in feed
  while (list.children.length > 50) list.removeChild(list.lastChild);
}

async function loadStats() {
  try {
    const res = await fetch(`${API}/api/stats`);
    const data = await res.json();
    document.getElementById("statTotal").textContent = data.total ?? 0;
    document.getElementById("statDuplicates").textContent = data.duplicates ?? 0;
    document.getElementById("statSensitive").textContent = data.sensitive ?? 0;
  } catch (e) {
    console.warn("Stats fetch failed:", e);
  }
}

async function loadFiles() {
  try {
    const res = await fetch(`${API}/api/files?limit=100`);
    const files = await res.json();
    const tbody = document.getElementById("filesBody");

    if (!files.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:32px;color:#475569;">No files yet</td></tr>`;
      return;
    }

    tbody.innerHTML = files.map(f => `
      <tr>
        <td title="${f.filename}">${f.filename}</td>
        <td>${categoryBadge(f.category)}</td>
        <td>${statusBadge(f)}</td>
        <td>${formatDate(f.processed_at)}</td>
      </tr>
    `).join("");
  } catch (e) {
    console.warn("Files fetch failed:", e);
  }
}

function connectWebSocket() {
  ws = new WebSocket(WS);

  ws.onopen = () => {
    document.getElementById("statusDot").style.background = "#22c55e";
  };

  ws.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    addFeedItem(event);
    loadStats();
    loadFiles();
  };

  ws.onclose = () => {
    document.getElementById("statusDot").style.background = "#ef4444";
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = () => ws.close();
}

function openOutputFolder() {
  const { shell } = require("electron");
  const os = require("os");
  shell.openPath(`${os.homedir()}/Downloads/OmniSort`);
}

// Init
loadStats();
loadFiles();
connectWebSocket();
setInterval(() => { loadStats(); loadFiles(); }, 10000);
