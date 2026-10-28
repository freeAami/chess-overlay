const DEFAULTS = {
  enabled: true, depth: 18, movetime: 3, side: "me",
  showReply: true, showEval: true, arrowColor: "#22c55e", replyColor: "#ef4444",
};
const $ = (id) => document.getElementById(id);
let settings = { ...DEFAULTS };

function save(patch) {
  Object.assign(settings, patch);
  chrome.storage.sync.set(patch);
  render();
}

function render() {
  document.body.classList.toggle("off", !settings.enabled);
  $("enabled").checked = !!settings.enabled;
  $("depth").value = settings.depth; $("depthVal").textContent = settings.depth;
  $("movetime").value = settings.movetime; $("movetimeVal").textContent = (+settings.movetime).toFixed(1) + " s";
  $("showReply").checked = !!settings.showReply;
  $("showEval").checked = !!settings.showEval;
  $("arrowColor").value = settings.arrowColor;
  for (const b of $("side").querySelectorAll("button")) b.classList.toggle("on", b.dataset.v === settings.side);
}

function evalToWidth(txt) {
  if (!txt) return 50;
  if (txt.includes("M")) return txt.startsWith("-") ? 2 : 98;
  const v = Math.max(-6, Math.min(6, parseFloat(txt) || 0));
  return 50 + (v / 6) * 45;
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function pollStatus() {
  const tab = await activeTab();
  let st = null;
  if (tab) {
    try { st = await chrome.tabs.sendMessage(tab.id, { type: "get-status" }); } catch (_) { st = null; }
  }
  const site = $("site"), best = $("bestMove"), hint = $("hint");
  if (!st) {
    site.textContent = "No board"; site.classList.remove("on");
    best.textContent = "—"; best.classList.add("pending");
    $("evalText").textContent = ""; $("depthText").textContent = ""; $("turnText").textContent = "";
    $("evalFill").style.width = "50%";
    hint.textContent = "Open a game or analysis board on Lichess or Chess.com (reload the page if one is already open).";
    return;
  }
  site.textContent = (st.site === "lichess" ? "Lichess" : "Chess.com") + (st.found ? " · board found" : " · no board");
  site.classList.toggle("on", !!st.found);
  $("turnText").textContent = st.found ? `${st.turn === "w" ? "White" : "Black"} to move · you are ${st.flipped ? "Black" : "White"}` : "";
  if (!settings.enabled) { best.textContent = "Off"; best.classList.add("pending"); hint.textContent = "Overlay disabled."; }
  else if (!st.found) { best.textContent = "—"; best.classList.add("pending"); hint.textContent = "Waiting for a board…"; }
  else if (!st.analyzing) { best.textContent = "Waiting"; best.classList.add("pending"); hint.textContent = "Not analyzing this side (see “Analyze for”)."; }
  else if (st.engineError) { best.textContent = "Error"; best.classList.add("pending"); hint.textContent = "Engine: " + st.engineError; }
  else if (!st.result) { best.textContent = "Thinking…"; best.classList.add("pending"); hint.textContent = "Stockfish is calculating."; }
  else {
    best.textContent = st.result.san || st.result.move; best.classList.remove("pending");
    hint.textContent = (st.result.reply ? `Expected reply: ${st.result.reply}. ` : "") + (st.exact ? "Exact position from page." : "Castling/en passant inferred from the board.");
  }
  $("evalText").textContent = st.result ? st.result.eval : "";
  $("depthText").textContent = st.result ? `depth ${st.result.depth}${st.result.final ? "" : " (searching)"}` : "";
  $("evalFill").style.width = evalToWidth(st.result && st.result.eval) + "%";
}

async function pollEngine() {
  try {
    const r = await chrome.runtime.sendMessage({ type: "engine-status" });
    const s = r && r.state;
    $("engineState").textContent = "Stockfish 19 · " + (s === "thinking" ? "thinking" : s === "idle" ? "ready" : s === "error" ? "error" : "loading…");
  } catch (_) { $("engineState").textContent = "Stockfish 19 · starting…"; }
}

$("enabled").addEventListener("change", (e) => save({ enabled: e.target.checked }));
$("depth").addEventListener("input", (e) => { $("depthVal").textContent = e.target.value; });
$("depth").addEventListener("change", (e) => save({ depth: +e.target.value }));
$("movetime").addEventListener("input", (e) => { $("movetimeVal").textContent = (+e.target.value).toFixed(1) + " s"; });
$("movetime").addEventListener("change", (e) => save({ movetime: +e.target.value }));
$("showReply").addEventListener("change", (e) => save({ showReply: e.target.checked }));
$("showEval").addEventListener("change", (e) => save({ showEval: e.target.checked }));
$("arrowColor").addEventListener("change", (e) => save({ arrowColor: e.target.value }));
$("side").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) save({ side: b.dataset.v }); });
$("reanalyze").addEventListener("click", async () => {
  const tab = await activeTab();
  if (tab) chrome.tabs.sendMessage(tab.id, { type: "reanalyze" }).catch(() => {});
});

chrome.storage.sync.get(DEFAULTS, (s) => { settings = { ...DEFAULTS, ...s }; render(); pollStatus(); });
pollEngine();
setInterval(pollStatus, 600);
setInterval(pollEngine, 1500);
