const $ = (s) => document.querySelector(s);
const chat = $("#chat");
const statusBox = $("#status");
const settings = $("#settings");

function cfg() {
  return {
    url: localStorage.getItem("acumen_bridge") || "http://127.0.0.1:8765",
    token: localStorage.getItem("acumen_token") || ""
  };
}

function add(role, text) {
  const d = document.createElement("div");
  d.className = `msg ${role}`;
  d.textContent = text;
  chat.appendChild(d);
  d.scrollIntoView({behavior:"smooth"});
}

async function api(path, options={}) {
  const c = cfg();
  const headers = Object.assign(
    {"X-Acumen-Token": c.token, "Content-Type":"application/json"},
    options.headers || {}
  );
  return fetch(c.url + path, Object.assign({}, options, {headers}));
}

async function check() {
  try {
    const r = await fetch(cfg().url + "/health");
    const j = await r.json();
    statusBox.textContent = j.ok ? "Connected to local Acumen" : "Not connected";
  } catch {
    statusBox.textContent = "Local bridge unavailable";
  }
}

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#message");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  add("user", text);
  try {
    const r = await api("/api/chat", {
      method:"POST",
      body:JSON.stringify({message:text})
    });
    const j = await r.json();
    add("acumen", j.reply || j.error || "No reply");
  } catch (err) {
    add("acumen", "Could not reach the local Acumen bridge.");
  }
});

$("#settingsBtn").onclick = () => {
  const c = cfg();
  $("#bridgeUrl").value = c.url;
  $("#token").value = c.token;
  settings.showModal();
};

$("#saveSettings").onclick = () => {
  localStorage.setItem("acumen_bridge", $("#bridgeUrl").value.trim());
  localStorage.setItem("acumen_token", $("#token").value);
  setTimeout(check, 100);
};

$("#refreshKnowledge").onclick = async () => {
  const box = $("#knowledge");
  box.textContent = "Loading…";
  try {
    const r = await api("/api/knowledge");
    const j = await r.json();
    box.innerHTML = "";
    for (const item of (j.items || [])) {
      const d = document.createElement("div");
      d.className = "knowledge-item";
      const p = document.createElement("p");
      p.textContent = `${item.query} → ${item.answer}`;
      const b = document.createElement("button");
      b.textContent = "Delete";
      b.onclick = async () => {
        await api(`/api/knowledge/${encodeURIComponent(item.id)}`, {method:"DELETE"});
        $("#refreshKnowledge").click();
      };
      d.append(p, b);
      box.appendChild(d);
    }
  } catch {
    box.textContent = "Could not load local knowledge.";
  }
};

check();
