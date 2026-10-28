// Reads the current position from the page DOM.
//   Lichess:   <cg-board><piece class="white knight" style="transform: translate(x, y)">
//   Chess.com: <wc-chess-board><div class="piece wn square-71">
// Produces { grid, fen, turn, flipped, site, lastMove } or null when no stable board.

const CO_FILES = "abcdefgh";
const CO_TYPES = { pawn: "p", knight: "n", bishop: "b", rook: "r", queen: "q", king: "k" };

function coDetectSite() {
  const h = location.hostname;
  if (h.endsWith("lichess.org")) return "lichess";
  if (h.endsWith("chess.com")) return "chesscom";
  return null;
}

function coBoardElement(site) {
  if (site === "lichess") return document.querySelector(".cg-wrap cg-board, cg-board");
  if (site === "chesscom") return document.querySelector("wc-chess-board, chess-board");
  return null;
}

function coEmptyGrid() {
  return Array.from({ length: 8 }, () => Array(8).fill(null));
}

function coTranslate(el) {
  const s = el.style.transform || el.getAttribute("style") || "";
  const m = /translate\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)px/.exec(s);
  return m ? [parseFloat(m[1]), parseFloat(m[2])] : null;
}

function coReadLichess(board) {
  const wrap = board.closest(".cg-wrap");
  const flipped = !!(wrap && wrap.classList.contains("orientation-black"));
  const rect = board.getBoundingClientRect();
  const sq = rect.width / 8;
  if (sq < 4) return null;
  const toSquare = (x, y) => {
    const cx = Math.round(x / sq), cy = Math.round(y / sq);
    if (cx < 0 || cx > 7 || cy < 0 || cy > 7) return null;
    return flipped ? [7 - cx, cy] : [cx, 7 - cy];
  };
  const grid = coEmptyGrid();
  let n = 0;
  for (const p of board.querySelectorAll("piece")) {
    if (p.classList.contains("ghost") || p.classList.contains("fading")) continue;
    if (p.classList.contains("dragging")) return null;
    const t = coTranslate(p);
    if (!t) continue;
    const fr = toSquare(t[0], t[1]);
    if (!fr) continue;
    const color = p.classList.contains("white") ? "w" : p.classList.contains("black") ? "b" : null;
    let type = null;
    for (const k in CO_TYPES) if (p.classList.contains(k)) type = CO_TYPES[k];
    if (!color || !type) continue;
    grid[fr[1]][fr[0]] = color === "w" ? type.toUpperCase() : type;
    n++;
  }
  if (n < 2) return null;
  const lastMove = [];
  for (const s of board.querySelectorAll("square.last-move")) {
    const t = coTranslate(s);
    const fr = t && toSquare(t[0], t[1]);
    if (fr) lastMove.push(fr);
  }
  let fenHint = null;
  const inp = document.querySelector(".analyse__underboard input.copyable, .copyables input.copyable");
  if (inp && /^[rnbqkpRNBQKP1-8/]+ [wb] /.test(inp.value)) fenHint = inp.value;
  return { grid, flipped, lastMove, fenHint, rect, site: "lichess" };
}

function coReadChesscom(board) {
  const flipped = board.classList.contains("flipped");
  const grid = coEmptyGrid();
  let n = 0;
  for (const p of board.querySelectorAll(".piece")) {
    const cls = p.className;
    if (typeof cls !== "string") continue;
    if (/\bdragging\b/.test(cls)) return null;
    const m = /square-(\d)(\d)/.exec(cls);
    const pm = /\b([wb])([pnbrqk])\b/.exec(cls);
    if (!m || !pm) continue;
    const file = +m[1] - 1, rank = +m[2] - 1;
    if (file < 0 || file > 7 || rank < 0 || rank > 7) continue;
    grid[rank][file] = pm[1] === "w" ? pm[2].toUpperCase() : pm[2];
    n++;
  }
  if (n < 2) return null;
  const lastMove = [];
  for (const h of board.querySelectorAll(".highlight")) {
    const m = /square-(\d)(\d)/.exec(h.className);
    if (m) lastMove.push([+m[1] - 1, +m[2] - 1]);
  }
  return { grid, flipped, lastMove, fenHint: null, rect: board.getBoundingClientRect(), site: "chesscom" };
}

function coPlacement(grid) {
  const rows = [];
  for (let r = 7; r >= 0; r--) {
    let row = "", empty = 0;
    for (let f = 0; f < 8; f++) {
      const p = grid[r][f];
      if (p) { if (empty) { row += empty; empty = 0; } row += p; }
      else empty++;
    }
    if (empty) row += empty;
    rows.push(row);
  }
  return rows.join("/");
}

function coCastling(grid) {
  let s = "";
  if (grid[0][4] === "K") { if (grid[0][7] === "R") s += "K"; if (grid[0][0] === "R") s += "Q"; }
  if (grid[7][4] === "k") { if (grid[7][7] === "r") s += "k"; if (grid[7][0] === "r") s += "q"; }
  return s || "-";
}

function coInferTurn(grid, lastMove) {
  for (const [f, r] of lastMove) {
    const p = grid[r][f];
    if (p) return p === p.toUpperCase() ? "b" : "w";
  }
  return null;
}

function coValid(grid) {
  let K = 0, k = 0, n = 0;
  for (const row of grid) for (const p of row) {
    if (!p) continue;
    n++;
    if (p === "K") K++;
    if (p === "k") k++;
  }
  return K === 1 && k === 1 && n <= 32;
}

function coSquareName(f, r) {
  return CO_FILES[f] + (r + 1);
}

function coParseSquare(s) {
  return [CO_FILES.indexOf(s[0]), +s[1] - 1];
}

// Build a FEN from the DOM reading, preferring an exact FEN hint (chess.com bridge
// or lichess analysis FEN box) when its placement matches what we see.
function coReadPosition(site, bridgeFen) {
  const board = coBoardElement(site);
  if (!board) return null;
  const raw = site === "lichess" ? coReadLichess(board) : coReadChesscom(board);
  if (!raw || !coValid(raw.grid)) return null;
  const placement = coPlacement(raw.grid);
  const hint = raw.fenHint || bridgeFen;
  let turn = null, castling = null, ep = "-";
  if (hint && hint.split(" ")[0] === placement) {
    const parts = hint.split(" ");
    turn = parts[1];
    castling = parts[2] || "-";
    ep = parts[3] || "-";
  }
  if (!turn) turn = coInferTurn(raw.grid, raw.lastMove) || "w";
  if (!castling) castling = coCastling(raw.grid);
  const fen = `${placement} ${turn} ${castling} ${ep} 0 1`;
  return { ...raw, board, placement, turn, fen, exact: !!(hint && hint.split(" ")[0] === placement) };
}

// Minimal SAN for display (no check/disambiguation symbols).
function coSan(grid, uci) {
  if (!uci || uci.length < 4) return uci || "";
  const [ff, fr] = coParseSquare(uci.slice(0, 2));
  const [tf, tr] = coParseSquare(uci.slice(2, 4));
  const piece = grid[fr] && grid[fr][ff];
  if (!piece) return uci;
  const type = piece.toLowerCase();
  if (type === "k" && Math.abs(tf - ff) === 2) return tf > ff ? "O-O" : "O-O-O";
  const target = grid[tr][tf];
  const capture = !!target || (type === "p" && tf !== ff);
  let s = "";
  if (type === "p") { if (capture) s += CO_FILES[ff] + "x"; }
  else s += type.toUpperCase() + (capture ? "x" : "");
  s += coSquareName(tf, tr);
  if (uci.length > 4) s += "=" + uci[4].toUpperCase();
  return s;
}
