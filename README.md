# chess-overlay

Watches a chess board on your screen (Chess.com / Lichess in a browser), recognises
the position, asks Stockfish for the best move and draws it as an arrow directly
over the board in a transparent, click-through window.

## Browser extension (recommended)

The `extension/` folder contains a Chrome extension that does the same job without screen capture:
it reads the position from the Lichess / Chess.com page, runs Stockfish (WASM) in the browser and
draws the arrow on the board, with a popup UI for all settings. See [extension/README.md](extension/README.md).

The Python app below is the screen-capture version (works with any window, needs calibration).


> **Fair play.** Using engine assistance in rated/online games against humans
> violates the Chess.com and Lichess terms of service and gets accounts banned.
> Use this for analysing positions, studying, or playing against bots.

## How it works

```
screen capture  ->  board locator  ->  piece recogniser  ->  move tracker  ->  Stockfish  ->  arrow overlay
   (mss/Pillow)      (edge grid +        (self-calibrating     (python-chess,      (local UCI or       (PySide6, always-on-top,
                      checker test)       silhouettes)          legal-move sync)    Lichess cloud)      click-through)
```

* **Board locator** – finds the 8x8 grid by looking for 7 evenly spaced edge
  lines in both directions plus a two-colour checkerboard test, then snaps to
  the exact square boundaries. Works on any board theme/size. You can also drag
  a box manually.
* **Piece recogniser** – needs no training data. When the start position is on
  screen it learns one silhouette per piece (all 12 appear in the start
  position) and a white/black brightness threshold. From then on each square is
  classified by silhouette overlap. Highlighted squares, move-hint dots and
  half-dragged pieces are handled (unknown squares are treated as wildcards).
* **Move tracker** – keeps a `chess.Board` in sync by finding the legal move
  (or two) that turns the previous position into the recognised one, so castling
  rights, en-passant and side-to-move are always correct. If it loses sync it
  rebuilds the position from the screen.
* **Engine** – local Stockfish via `python-chess`. If no binary is found it
  falls back to the Lichess cloud-eval API (`--no-cloud` disables that).
* **Overlay** – transparent, click-through, always-on-top Qt window exactly over
  the board. Draws the best move (green), optionally the expected reply (red),
  and the evaluation above the board. The overlay is hidden for ~50 ms whenever
  the capture needs a clean look at the board, so our own arrow never confuses
  recognition.

## Install

```bash
pip install -r requirements.txt
# Stockfish:
#   Ubuntu/Debian: sudo apt install stockfish
#   macOS:         brew install stockfish
#   Windows:       download from https://stockfishchess.org/download/ and either put
#                  stockfish.exe on PATH, set STOCKFISH_PATH, or pass --engine PATH
```

Python 3.9+. Linux needs X11 (Wayland does not allow click-through overlays or
unrestricted screen capture).

## Use

1. Open Chess.com or Lichess with a board showing the **starting position**.
2. Calibrate once (auto-detects the board; drag a box if it guesses wrong, Enter to accept):

   ```bash
   python -m chess_overlay calibrate
   ```

3. Run:

   ```bash
   python -m chess_overlay run
   ```

   The arrow appears whenever it is your turn (your side = the side at the bottom
   of the board). Ctrl+C to quit.

Options for `run`:

| flag | meaning |
|---|---|
| `--time 1.0` | seconds of Stockfish thinking per position (default 1.0) |
| `--depth N` | fixed search depth instead of time |
| `--threads N` | engine threads |
| `--engine PATH` | Stockfish binary |
| `--side white\|black\|auto` | whose moves to suggest (default: bottom side) |
| `--both` | suggest for both sides (analysis mode) |
| `--show-reply` | also draw the expected reply in red |
| `--fps 6` | capture rate |
| `--region x,y,w,h` | board region in physical pixels, skips calibration |
| `--recalibrate` | re-learn piece silhouettes from the next start position |
| `--no-cloud` | never query Lichess cloud eval |
| `--debug` | print the recognised board after every move |

If the board moves or you resize the browser, run `calibrate` again. Piece
silhouettes are re-learned automatically when a new game's start position
appears (and when the board is flipped to play the other colour).

Config and templates live in `~/.chess_overlay/`.

## Limitations

* Piece templates are learned per piece set; switching the site's piece theme
  mid-game needs `--recalibrate`.
* Sync starts from the start position. Joining a game mid-way works, but
  castling rights / side to move are guessed until the next move confirms them.
* macOS: grant Screen Recording and Accessibility permission to the terminal/Python.
