# Chess Overlay – browser extension

Chrome (Manifest V3) extension that reads the board directly from the Lichess / Chess.com page,
runs **Stockfish 19 (WebAssembly) inside the browser** and draws the best move as an arrow on the
board. No Python, no screen capture, no calibration — everything is controlled from the popup.

> Engine assistance in rated games against humans violates Lichess and Chess.com fair-play rules.
> Use this for analysis, studying and games against bots.

## Install (load unpacked)

1. Download / clone this repo.
2. Open `chrome://extensions`, turn on **Developer mode** (top right).
3. Click **Load unpacked** and select the `extension/` folder.
4. Open a board on https://lichess.org or https://www.chess.com — the arrow appears automatically.
   Click the extension icon for settings and live status.

Works in any Chromium browser (Chrome, Edge, Brave, Arc, Opera).

## What the popup controls

| Control | Meaning |
| --- | --- |
| Master toggle | Turn the overlay on/off everywhere |
| Analyze for | **Me** (the side at the bottom of the board), White, Black or Both |
| Depth | Stockfish search depth (6–30) |
| Max think time | Hard cap per position, so slow depths still answer quickly |
| Show expected reply | Draws the opponent's expected answer as a second (red) arrow |
| Show eval badge | Small badge on the board: move, evaluation (white's point of view), depth |
| Arrow colour | Colour of the best-move arrow |
| Re-analyze | Force a fresh search of the current position |

The popup also shows the detected site, side to move, the best move in SAN, the evaluation bar and
whether the position came exactly from the page or was inferred (castling / en passant).

## How it works

```
content/reader.js   DOM -> FEN   (lichess <cg-board><piece>, chess.com <wc-chess-board> .piece.square-XY)
content/bridge.js   chess.com only, MAIN world: exact FEN from the board's game API
content/overlay.js  fixed-position SVG over the board + eval badge
content/main.js     polls the board every 300 ms, sends changed FENs to the engine, draws results
background.js       service worker: routes messages, owns the offscreen document
offscreen.js        hosts Stockfish (engine/stockfish-19-lite-single.js + .wasm) in a Web Worker, speaks UCI
popup/              settings UI (chrome.storage.sync) + live status
```

Positions are read from the page, so piece sets, themes, board size and orientation do not matter.
Side to move comes from the page's FEN when available (Chess.com API, Lichess analysis board FEN box),
otherwise it is inferred from the last-move highlight.

## Engine

`engine/` contains the single-threaded "lite" build (NNUE, ~1.8 MB) from the
[stockfish.js](https://github.com/nmrugg/stockfish.js) project (GPLv3, see `engine/LICENSE-stockfish.txt`).
It runs in any Chromium browser without cross-origin isolation. Expect roughly depth 18 in 1–3 s on a
laptop; raise "Max think time" for deeper searches.

## Limitations

* Chrome/Chromium only (Firefox MV3 lacks `chrome.offscreen`).
* Chess960 castling and some variant boards are not handled.
* If Lichess or Chess.com change their board markup, `content/reader.js` is the only file to adjust.
