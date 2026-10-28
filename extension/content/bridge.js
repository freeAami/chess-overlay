// Runs in the page's MAIN world on chess.com: the board web component exposes
// a game API with an exact FEN (side to move, castling rights, en passant).
// We forward it to the isolated-world content script via postMessage.
(() => {
  let last = null, lastAt = 0;
  function tick() {
    try {
      const b = document.querySelector("wc-chess-board, chess-board");
      const g = b && b.game;
      if (!g || typeof g.getFEN !== "function") return;
      const fen = g.getFEN();
      let playingAs = null;
      try { playingAs = typeof g.getPlayingAs === "function" ? g.getPlayingAs() : null; } catch (_) {}
      const key = fen + "|" + playingAs;
      const now = Date.now();
      if (key === last && now - lastAt < 2000) return;
      last = key; lastAt = now;
      window.postMessage({ source: "chess-overlay-bridge", fen, playingAs }, "*");
    } catch (_) {}
  }
  setInterval(tick, 250);
})();
