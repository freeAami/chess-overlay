// Service worker: routes analysis requests from content scripts to the
// offscreen document (which hosts the Stockfish worker) and results back.

let creating = null;

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  if (!creating) {
    creating = chrome.offscreen
      .createDocument({
        url: "offscreen.html",
        reasons: ["WORKERS"],
        justification: "Run the Stockfish WebAssembly engine in a web worker",
      })
      .finally(() => (creating = null));
  }
  await creating;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;

  if (msg.target === "background") {
    if (msg.type === "engine" && msg.tabId != null) {
      chrome.tabs.sendMessage(msg.tabId, msg.payload).catch(() => {});
    }
    return;
  }

  if (msg.type === "analyze" && sender.tab) {
    ensureOffscreen()
      .then(() =>
        chrome.runtime.sendMessage({ ...msg, target: "offscreen", tabId: sender.tab.id })
      )
      .then(() => sendResponse({ ok: true }))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === "stop" && sender.tab) {
    chrome.offscreen.hasDocument().then((has) => {
      if (has) chrome.runtime.sendMessage({ target: "offscreen", type: "stop", tabId: sender.tab.id });
    });
    return;
  }

  if (msg.type === "engine-status") {
    ensureOffscreen()
      .then(() => chrome.runtime.sendMessage({ target: "offscreen", type: "status" }))
      .then((r) => sendResponse(r || { state: "unknown" }))
      .catch((e) => sendResponse({ state: "error", error: String(e) }));
    return true;
  }
});

chrome.runtime.onInstalled.addListener(() => {
  ensureOffscreen().catch(() => {});
});
