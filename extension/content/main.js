// Content script main loop: poll the board, send changed positions to the
// engine, draw the best move, answer status queries from the popup.

(() => {
  const DEFAULTS = {
    enabled: true, depth: 18, movetime: 3, side: "me",
    showReply: true, showEval: true, arrowColor: "#22c55e", replyColor: "#ef4444",
  };
  const site = coDetectSite();
  if (!site) return;

  const overlay = new CoOverlay();
  let settings = { ...DEFAULTS };
  let bridgeFen = null, bridgeAt = 0;
  let pos = null;
  let lastKey = null;
  let reqId = 0;
  let result = null; // { id, move, ponder, depth, score, pv, final }
  let engineError = null;

  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || e.data.source !== "chess-overlay-bridge") return;
    bridgeFen = e.data.fen;
    bridgeAt = Date.now();
  });

  function analyzeSide() {
    if (!pos) return false;
    const me = pos.flipped ? "b" : "w";
    switch (settings.side) {
      case "both": return true;
      case "white": return pos.turn === "w";
      case "black": return pos.turn === "b";
      default: return pos.turn === me;
    }
  }

  function requestAnalysis() {
    reqId++;
    result = null;
    chrome.runtime.sendMessage({
      type: "analyze", id: reqId, fen: pos.fen,
      depth: +settings.depth || 18, movetime: Math.round((+settings.movetime || 0) * 1000),
    }).then((r) => { engineError = r && r.ok ? null : (r && r.error) || "no response"; })
      .catch((e) => { engineError = String(e); });
  }

  function evalText() {
    if (!result || !result.score) return "";
    const s = result.score;
    const sign = pos && pos.turn === "b" ? -1 : 1;
    if (s.type === "mate") {
      const m = s.value * sign;
      return (m > 0 ? "+M" : "-M") + Math.abs(m);
    }
    const v = (s.value * sign) / 100;
    return (v > 0 ? "+" : "") + v.toFixed(2);
  }

  function draw() {
    if (!settings.enabled || !pos) { overlay.clear(); overlay.detach(); return; }
    overlay.setRect(pos.rect);
    if (!result || !result.move || result.move === "(none)") {
      overlay.setArrows([], pos.flipped);
      overlay.setBadge(settings.showEval && analyzeSide() ? (engineError ? "engine: " + engineError : "thinking…") : "");
      return;
    }
    const arrows = [{
      from: coParseSquare(result.move.slice(0, 2)), to: coParseSquare(result.move.slice(2, 4)),
      color: settings.arrowColor, opacity: result.final ? 0.9 : 0.6,
    }];
    const reply = result.ponder || (result.pv && result.pv[1]);
    if (settings.showReply && reply && reply.length >= 4) {
      arrows.push({ from: coParseSquare(reply.slice(0, 2)), to: coParseSquare(reply.slice(2, 4)), color: settings.replyColor, opacity: 0.55 });
    }
    overlay.setArrows(arrows, pos.flipped);
    if (settings.showEval) {
      overlay.setBadge(`${coSan(pos.grid, result.move)}  ${evalText()}  d${result.depth || 0}`);
    } else overlay.setBadge("");
  }

  function tick() {
    const fresh = Date.now() - bridgeAt < 3000 ? bridgeFen : null;
    const p = coReadPosition(site, fresh);
    if (!p) {
      if (pos && !coBoardElement(site)) { pos = null; lastKey = null; result = null; overlay.clear(); overlay.detach(); }
      return;
    }
    pos = p;
    const key = p.fen.split(" ").slice(0, 4).join(" ") + "|" + (settings.enabled && analyzeSide() ? 1 : 0) + "|" + settings.depth + "|" + settings.movetime;
    if (key !== lastKey) {
      lastKey = key;
      result = null;
      if (settings.enabled && analyzeSide()) requestAnalysis();
      else chrome.runtime.sendMessage({ type: "stop" }).catch(() => {});
    }
    draw();
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "info" || msg.type === "bestmove") {
      if (msg.id !== reqId) return;
      result = {
        id: msg.id, move: msg.type === "bestmove" ? msg.move : msg.pv[0], ponder: msg.ponder || null,
        depth: msg.depth, score: msg.score, pv: msg.pv || [], final: msg.type === "bestmove",
      };
      draw();
      return;
    }
    if (msg.type === "get-status") {
      sendResponse({
        site, found: !!pos, fen: pos && pos.fen, turn: pos && pos.turn, flipped: !!(pos && pos.flipped),
        exact: !!(pos && pos.exact), analyzing: !!(pos && settings.enabled && analyzeSide()),
        engineError,
        result: result && pos ? {
          move: result.move, san: coSan(pos.grid, result.move), reply: result.ponder || (result.pv && result.pv[1]) || null,
          eval: evalText(), depth: result.depth, final: result.final, pv: result.pv,
        } : null,
      });
      return;
    }
    if (msg.type === "reanalyze") { lastKey = null; tick(); sendResponse({ ok: true }); }
  });

  chrome.storage.sync.get(DEFAULTS, (s) => {
    settings = { ...DEFAULTS, ...s };
    setInterval(tick, 300);
    tick();
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    for (const k in changes) settings[k] = changes[k].newValue;
    draw();
    tick();
  });
  window.addEventListener("scroll", () => pos && overlay.setRect(coBoardElement(site)?.getBoundingClientRect()), true);
  window.addEventListener("resize", () => pos && overlay.setRect(coBoardElement(site)?.getBoundingClientRect()));
})();
