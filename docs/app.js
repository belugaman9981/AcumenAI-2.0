const $ = (selector) => document.querySelector(selector);
const chat = $("#chat"), statusBox = $("#status"), settings = $("#settings");
let busy = false, transcript = [], savedKnowledge = [], pendingCount = 0, sourcesShown = true;
let recentQuestions = [];
let pairedConfig = null, pairing = false;
const emptyState = $("#emptyChat").cloneNode(true);
function setStatus(text, state = "connected") {
  statusBox.textContent = text;
  statusBox.dataset.state = state;
}
function resizeComposer() {
  const input = $("#message");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  input.style.overflowY = input.scrollHeight > 180 ? "auto" : "hidden";
}
function nearLatest() { return chat.scrollHeight - chat.scrollTop - chat.clientHeight < 60; }
function updateLatest() { $("#latestMessage").hidden = nearLatest(); }
chat.addEventListener("scroll", updateLatest, {passive: true});
$("#latestMessage").onclick = () => chat.scrollTo({top: chat.scrollHeight,
  behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"});
window.addEventListener("resize", () => { resizeComposer(); updateLatest(); });

function draftKey() { return `acumen_draft:${cfg().url}`; }
function saveDraft() {
  resizeComposer();
  try {
    const value = $("#message").value;
    if (value) sessionStorage.setItem(draftKey(), value);
    else sessionStorage.removeItem(draftKey());
  } catch { /* Chat remains usable when browser storage is unavailable. */ }
}
function restoreDraft() {
  try { $("#message").value = sessionStorage.getItem(draftKey()) || ""; }
  catch { $("#message").value = ""; }
  resizeComposer();
}
function fillDraft(value) {
  $("#message").value = value;
  saveDraft();
  $("#message").focus();
}
function renderRecent() {
  const select = $("#recentQuestions");
  select.replaceChildren(new Option(recentQuestions.length ? "Choose a question to edit or send again…" : "Your questions will appear here", ""));
  recentQuestions.forEach((question, index) => select.add(new Option(question, String(index))));
  select.disabled = !recentQuestions.length;
  $("#recentRow").hidden = !recentQuestions.length;
}
function applyTheme(value) {
  const theme = ["light", "dark"].includes(value) ? value : "system";
  document.documentElement.dataset.theme = theme;
  $("#theme").value = theme;
}
try { applyTheme(localStorage.getItem("acumen_theme")); } catch { applyTheme("system"); }
$("#theme").onchange = () => {
  applyTheme($("#theme").value);
  try { localStorage.setItem("acumen_theme", $("#theme").value); } catch { /* Apply for this page only. */ }
};
$("#recentQuestions").onchange = () => {
  const index = $("#recentQuestions").value;
  if (index !== "") fillDraft(recentQuestions[Number(index)]);
  $("#recentQuestions").value = "";
};
$("#message").addEventListener("input", saveDraft);
restoreDraft();

function cfg() {
  if (pairedConfig) return pairedConfig;
  const localPage = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  const defaults = {url: localPage ? location.origin : "http://127.0.0.1:8765", token: ""};
  try {
    return {url: localStorage.getItem("acumen_bridge") || defaults.url, token: localStorage.getItem("acumen_token") || ""};
  } catch { return defaults; }
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
  document.querySelectorAll(".retry, .repeat, .delete-knowledge").forEach(button => { button.disabled = value; });
}
function add(role, text, retryQuestion = null, failed = false) {
  const follow = role === "user" || nearLatest();
  $("#emptyChat")?.remove();
  const message = document.createElement("article");
  message.className = `msg ${role}`;
  message.classList.toggle("failed", failed);
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
    retry.className = failed ? "retry" : "repeat";
    retry.textContent = failed ? "Try again" : "Ask again";
    retry.onclick = () => send(retryQuestion);
    message.append(retry);
  }
  transcript.push({role, text});
  chat.append(message);
  if (follow) chat.scrollTop = role === "user" ? chat.scrollHeight : message.offsetTop - 20;
  updateLatest();
  setBusy(busy);
}
async function api(path, options = {}, config = cfg()) {
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
  try { await refreshSession(); setStatus("Connected and paired with local Acumen"); }
  catch (error) { setStatus(error.message, "error"); pendingCount = 0; setBusy(busy); }
}
async function send(text) {
  if (busy || !text.trim()) return;
  if (!text.startsWith("/")) {
    recentQuestions = [text, ...recentQuestions.filter(question => question !== text)].slice(0, 10);
    renderRecent();
  }
  setBusy(true);
  add("user", text);
  $("#activity").hidden = false;
  try {
    const result = await api("/api/chat", {method: "POST", body: JSON.stringify({message: text})});
    add("acumen", result.reply || "No reply received.", text.startsWith("/") ? null : text);
    try { await refreshSession(); setStatus("Connected and paired with local Acumen"); }
    catch (error) { setStatus(error.message, "error"); }
  } catch (error) { add("acumen", error.message, text, true); setStatus(error.message, "error"); }
  finally {
    $("#activity").hidden = true;
    setBusy(false);
    // Do not move focus away from controls the user selected while waiting.
    if (document.activeElement === $("#sendBtn")) $("#message").focus({preventScroll: true});
  }
}
$("#form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy) return;
  const input = $("#message"), text = input.value.trim();
  if (!text) return;
  input.value = "";
  saveDraft();
  input.focus({preventScroll: true});
  send(text);
});
$("#message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("#form").requestSubmit(); }
  if (event.key === "ArrowUp" && !event.isComposing && !$("#message").value && recentQuestions.length) {
    event.preventDefault();
    fillDraft(recentQuestions[0]);
  }
});
document.querySelectorAll("[data-prompt]").forEach(button => {
  button.onclick = () => fillDraft(button.dataset.prompt);
});
$("#helpBtn").onclick = () => send("/help");
$("#showSources").onchange = async () => {
  if (busy) return;
  const wanted = $("#showSources").checked;
  setBusy(true);
  try {
    await api("/api/chat", {method: "POST", body: JSON.stringify({message: wanted ? "/show-source" : "/hide-source"})});
    sourcesShown = wanted;
    setStatus(`Sources ${wanted ? "shown" : "hidden"} for future answers.`);
  } catch (error) { $("#showSources").checked = sourcesShown; setStatus(error.message, "error"); }
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
  recentQuestions = [];
  renderRecent();
  chat.replaceChildren(emptyState.cloneNode(true));
  updateLatest();
  setBusy(false);
  $("#message").focus();
};
$("#settingsBtn").onclick = () => {
  const config = cfg();
  $("#bridgeUrl").value = config.url;
  $("#token").value = config.token;
  $("#pairError").hidden = true;
  settings.showModal();
};
settings.addEventListener("cancel", event => { if (pairing) event.preventDefault(); });
$("#settings form").addEventListener("submit", async (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  if (pairing) return;
  let candidate;
  try {
    const url = new URL($("#bridgeUrl").value.trim());
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error();
    candidate = {url: url.href.replace(/\/+$/, ""), token: $("#token").value.trim()};
  } catch {
    $("#bridgeUrl").setCustomValidity("Enter an http:// or https:// bridge URL without a username, password, query, or fragment.");
    $("#bridgeUrl").reportValidity();
    return;
  }
  pairing = true;
  $("#pairError").hidden = true;
  settings.querySelectorAll("button, input").forEach(control => { control.disabled = true; });
  $("#saveSettings").textContent = "Connecting…";
  try {
    await api("/api/session", {signal: AbortSignal.timeout(10000)}, candidate);
    pairedConfig = candidate;
    try {
      localStorage.setItem("acumen_bridge", candidate.url);
      localStorage.setItem("acumen_token", candidate.token);
    } catch { /* Pairing still works for this page when storage is unavailable. */ }
    restoreDraft();
    savedKnowledge = [];
    renderKnowledge();
    settings.close();
    await check();
    if ($("#knowledgePanel").open) await refreshKnowledge();
    $("#message").focus({preventScroll: true});
  } catch (error) {
    $("#pairError").textContent = error.message;
    $("#pairError").hidden = false;
  } finally {
    pairing = false;
    settings.querySelectorAll("button, input").forEach(control => { control.disabled = false; });
    $("#saveSettings").textContent = "Save and connect";
  }
});
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
      } catch (error) { setStatus(error.message, "error"); }
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
$("#knowledgePanel").addEventListener("toggle", () => { if ($("#knowledgePanel").open) refreshKnowledge(); });
$("#knowledgeSearch").oninput = renderKnowledge;
async function resolveLearning(action) {
  if (busy) return;
  if (action === "discard" && !confirm("Discard all new learning? Saved knowledge will stay.")) return;
  setBusy(true);
  try {
    const result = await api("/api/session/learning", {method: "POST", body: JSON.stringify({action})});
    setStatus(result.answer);
    await refreshSession();
    await refreshKnowledge();
  } catch (error) { setStatus(error.message, "error"); }
  finally { setBusy(false); }
}
$("#saveLearning").onclick = () => resolveLearning("save");
$("#discardLearning").onclick = () => resolveLearning("discard");
check();
