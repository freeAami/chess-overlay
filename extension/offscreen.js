// Hosts Stockfish (WASM, single-threaded "lite" build) in a Web Worker and
// speaks UCI to it. Only the most recent analysis request is kept.

const worker = new Worker("engine/stockfish-19-lite-single.js");

let state = "loading";
let ready = false;
let current = null; // { id, tabId, fen, depth, movetime, done }
let pending = null;
let lastInfo = null;
const preReady = [];

function send(cmd) {
  if (!ready && cmd !== "uci" && cmd !== "isready" && !cmd.startsWith("setoption")) {
    preReady.push(cmd);
    return;
  }
  worker.postMessage(cmd);
}

function emit(tabId, payload) {
  if (tabId == null) return;
  chrome.runtime.sendMessage({ target: "background", type: "engine", tabId, payload }).catch(() => {});
}

function start(req) {
  current = { ...req, done: false };
  lastInfo = null;
  send(`position fen ${req.fen}`);
  const parts = [`go depth ${req.depth || 18}`];
  if (req.movetime) parts.push(`movetime ${Math.round(req.movetime)}`);
  send(parts.join(" "));
  state = "thinking";
}

function analyze(req) {
  if (current && !current.done) {
    pending = req;
    send("stop");
  } else {
    start(req);
  }
}

function parseInfo(line) {
  const tok = line.split(/\s+/);
  const info = { depth: 0, multipv: 1, score: null, pv: [] };
  for (let i = 1; i < tok.length; i++) {
    const t = tok[i];
    if (t === "depth") info.depth = +tok[++i];
    else if (t === "multipv") info.multipv = +tok[++i];
    else if (t === "score") {
      const kind = tok[++i];
      const v = +tok[++i];
      info.score = { type: kind, value: v };
    } else if (t === "pv") {
      info.pv = tok.slice(i + 1);
      break;
    }
  }
  return info;
}

worker.onmessage = (e) => {
  const line = typeof e.data === "string" ? e.data : String(e.data);
  if (line === "uciok") {
    worker.postMessage("setoption name Threads value 1");
    worker.postMessage("setoption name Hash value 32");
    worker.postMessage("isready");
    return;
  }
  if (line === "readyok") {
    if (!ready) {
      ready = true;
      state = "idle";
      for (const c of preReady.splice(0)) worker.postMessage(c);
    }
    return;
  }
  if (!current) return;
  if (line.startsWith("info ") && line.includes(" pv ")) {
    const info = parseInfo(line);
    if (info.multipv !== 1 || !info.score || !info.pv.length) return;
    lastInfo = info;
    emit(current.tabId, { type: "info", id: current.id, depth: info.depth, score: info.score, pv: info.pv.slice(0, 4) });
    return;
  }
  if (line.startsWith("bestmove")) {
    const m = line.split(/\s+/);
    current.done = true;
    state = "idle";
    emit(current.tabId, {
      type: "bestmove",
      id: current.id,
      move: m[1],
      ponder: m[3] || null,
      depth: lastInfo ? lastInfo.depth : 0,
      score: lastInfo ? lastInfo.score : null,
      pv: lastInfo ? lastInfo.pv.slice(0, 4) : [],
    });
    if (pending) {
      const p = pending;
      pending = null;
      start(p);
    }
  }
};

worker.onerror = (e) => {
  state = "error";
  console.error("Stockfish worker error", e);
};

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.target !== "offscreen") return;
  if (msg.type === "analyze") {
    analyze(msg);
    sendResponse({ ok: true });
  } else if (msg.type === "stop") {
    if (current && !current.done && current.tabId === msg.tabId) {
      pending = null;
      send("stop");
    }
    sendResponse({ ok: true });
  } else if (msg.type === "status") {
    sendResponse({ state, ready, busy: !!(current && !current.done) });
  }
});

worker.postMessage("uci");
