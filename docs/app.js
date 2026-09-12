const $ = (selector) => document.querySelector(selector);
const chat = $("#chat"), statusBox = $("#status"), settings = $("#settings");
let busy = false, transcript = [], savedKnowledge = [], pendingCount = 0, sourcesShown = true;

function cfg() {
  return {url: localStorage.getItem("acumen_bridge") || "http://127.0.0.1:8765", token: localStorage.getItem("acumen_token") || ""};
}
function setBusy(value) {
  busy = value;
  $("#sendBtn").disabled = value;
  $("#sendBtn").textContent = value ? "Working…" : "Send";
  chat.setAttribute("aria-busy", String(value));
  $("#showSources").disabled = $("#settingsBtn").disabled = value;
  $("#clearChat").disabled = value || !transcript.length;
  $("#exportChat").disabled = !transcript.length;
  $("#saveLearning").disabled = $("#discardLearning").disabled = value || !pendingCount;
  document.querySelectorAll(".retry, .delete-knowledge").forEach(button => { button.disabled = value; });
}
function add(role, text, retryQuestion = null) {
  $("#emptyChat")?.remove();
  const message = document.createElement("article");
  message.className = `msg ${role}`;
  const heading = document.createElement("strong"), content = document.createElement("div");
  heading.textContent = role === "user" ? "You" : "Acumen";
  content.className = "message-text";
  content.textContent = text;
  message.append(heading, content);
  if (role !== "user") {
    const copy = document.createElement("button");
    copy.textContent = "Copy";
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(text); copy.textContent = "Copied"; }
      catch { copy.textContent = "Select text to copy"; }
    };
    message.append(copy);
  }
  if (retryQuestion) {
    const retry = document.createElement("button");
    retry.className = "retry";
    retry.textContent = "Try again";
    retry.onclick = () => send(retryQuestion);
    message.append(retry);
  }
  transcript.push({role, text});
  chat.append(message);
  message.scrollIntoView({behavior: "smooth", block: "nearest"});
  setBusy(busy);
}
async function api(path, options = {}) {
  const config = cfg();
  let response;
  try {
    response = await fetch(config.url.replace(/\/+$/, "") + path, {...options,
      headers: {"X-Acumen-Token": config.token, "Content-Type": "application/json", ...options.headers}});
  } catch { throw new Error("Could not reach Acumen. Start the local bridge, then check your Pair settings."); }
  if (response.status === 401) throw new Error("Pairing token not accepted. Open Pair and check your token.");
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.error || "Acumen could not complete that action. Please try again.");
  }
  return response.json();
}
async function refreshSession() {
  const session = await api("/api/session"), items = session.candidates || [];
  pendingCount = items.length;
  sourcesShown = session.show_sources;
  $("#showSources").checked = sourcesShown;
  $("#learningCount").textContent = `(${items.length})`;
  const box = $("#learning");
  box.replaceChildren();
  if (!items.length) box.textContent = "No new learning waiting. Ask a question to get started.";
  for (const item of items) {
    const row = document.createElement("div"), question = document.createElement("strong"), answer = document.createElement("p");
    row.className = "knowledge-item";
    question.textContent = item.query;
    answer.textContent = item.answer;
    row.append(question, answer);
    for (const source of item.sources || []) {
      try {
        const url = new URL(source.url);
        if (!["http:", "https:"].includes(url.protocol)) continue;
        const link = document.createElement("a");
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.title || url.hostname;
        row.append(link, document.createTextNode(" "));
      } catch { /* Skip unusable source links. */ }
    }
    box.append(row);
  }
  setBusy(busy);
}
async function check() {
  try { await refreshSession(); statusBox.textContent = "Connected and paired with local Acumen"; }
  catch (error) { statusBox.textContent = error.message; pendingCount = 0; setBusy(busy); }
}
async function send(text) {
  if (busy || !text.trim()) return;
  setBusy(true);
  add("user", text);
  try {
    const result = await api("/api/chat", {method: "POST", body: JSON.stringify({message: text})});
    add("acumen", result.reply || "No reply received.");
    try { await refreshSession(); statusBox.textContent = "Connected and paired with local Acumen"; }
    catch (error) { statusBox.textContent = error.message; }
  } catch (error) { add("acumen", error.message, text); statusBox.textContent = error.message; }
  finally { setBusy(false); $("#message").focus(); }
}
$("#form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy) return;
  const input = $("#message"), text = input.value.trim();
  if (!text) return;
  input.value = "";
  send(text);
});
$("#message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("#form").requestSubmit(); }
});
document.querySelectorAll("[data-prompt]").forEach(button => {
  button.onclick = () => { $("#message").value = button.dataset.prompt; $("#message").focus(); };
});
$("#helpBtn").onclick = () => send("/help");
$("#showSources").onchange = async () => {
  if (busy) return;
  const wanted = $("#showSources").checked;
  setBusy(true);
  try {
    await api("/api/chat", {method: "POST", body: JSON.stringify({message: wanted ? "/show-source" : "/hide-source"})});
    sourcesShown = wanted;
    statusBox.textContent = `Sources ${wanted ? "shown" : "hidden"} for future answers.`;
  } catch (error) { $("#showSources").checked = sourcesShown; statusBox.textContent = error.message; }
  finally { setBusy(false); }
};
$("#exportChat").onclick = () => {
  const text = transcript.map(item => `${item.role === "user" ? "You" : "Acumen"}: ${item.text}`).join("\n\n");
  const url = URL.createObjectURL(new Blob([text], {type: "text/plain;charset=utf-8"})), link = document.createElement("a");
  link.href = url;
  link.download = "acumen-chat.txt";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$("#clearChat").onclick = () => {
  if (busy || !confirm("Clear the chat display? Export first if you want a copy. Saved and pending learning will stay.")) return;
  transcript = [];
  chat.replaceChildren();
  setBusy(false);
  $("#message").focus();
};
$("#settingsBtn").onclick = () => {
  const config = cfg();
  $("#bridgeUrl").value = config.url;
  $("#token").value = config.token;
  settings.showModal();
};
$("#saveSettings").onclick = (event) => {
  try {
    const url = new URL($("#bridgeUrl").value.trim());
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) throw new Error();
    localStorage.setItem("acumen_bridge", url.href.replace(/\/+$/, ""));
    localStorage.setItem("acumen_token", $("#token").value);
    savedKnowledge = [];
    renderKnowledge();
    check();
  } catch {
    event.preventDefault();
    $("#bridgeUrl").setCustomValidity("Enter an http:// or https:// bridge URL without a username or password.");
    $("#bridgeUrl").reportValidity();
  }
};
$("#bridgeUrl").oninput = () => $("#bridgeUrl").setCustomValidity("");
function renderKnowledge() {
  const query = $("#knowledgeSearch").value.toLocaleLowerCase();
  const items = savedKnowledge.filter(item => `${item.query} ${item.answer}`.toLocaleLowerCase().includes(query));
  const box = $("#knowledge");
  box.replaceChildren();
  if (!items.length) box.textContent = query ? "No matching saved knowledge." : "No saved knowledge yet.";
  for (const item of items) {
    const row = document.createElement("div"), content = document.createElement("p"), button = document.createElement("button");
    row.className = "knowledge-item";
    content.textContent = `${item.query} → ${item.answer}`;
    button.className = "delete-knowledge";
    button.textContent = "Delete";
    button.disabled = busy;
    button.onclick = async () => {
      if (busy || !confirm(`Delete saved knowledge for “${item.query}”?`)) return;
      setBusy(true);
      try {
        await api(`/api/knowledge/${encodeURIComponent(item.id)}`, {method: "DELETE"});
        savedKnowledge = savedKnowledge.filter(saved => saved.id !== item.id);
        renderKnowledge();
      } catch (error) { statusBox.textContent = error.message; }
      finally { setBusy(false); }
    };
    row.append(content, button);
    box.append(row);
  }
}
async function refreshKnowledge() {
  $("#knowledge").textContent = "Loading…";
  try { const result = await api("/api/knowledge"); savedKnowledge = result.items || []; renderKnowledge(); }
  catch (error) { $("#knowledge").textContent = error.message; }
}
$("#refreshKnowledge").onclick = refreshKnowledge;
$("#knowledgeSearch").oninput = renderKnowledge;
async function resolveLearning(action) {
  if (busy) return;
  if (action === "discard" && !confirm("Discard all new learning? Saved knowledge will stay.")) return;
  setBusy(true);
  try {
    const result = await api("/api/session/learning", {method: "POST", body: JSON.stringify({action})});
    statusBox.textContent = result.answer;
    await refreshSession();
    await refreshKnowledge();
  } catch (error) { statusBox.textContent = error.message; }
  finally { setBusy(false); }
}
$("#saveLearning").onclick = () => resolveLearning("save");
$("#discardLearning").onclick = () => resolveLearning("discard");
check();
