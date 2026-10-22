"""Best-move calculation: local Stockfish (preferred) with Lichess cloud-eval fallback."""
import json
import os
import platform
import shutil
import threading
import queue
import urllib.parse
import urllib.request

import chess
import chess.engine

_CANDIDATES = [
    "/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish", "C:\\stockfish\\stockfish.exe",
]


def find_stockfish(explicit=None):
    for p in [explicit, os.environ.get("STOCKFISH_PATH"), shutil.which("stockfish")] + _CANDIDATES:
        if p and os.path.isfile(p):
            return p
    return None


class Result:
    def __init__(self, board, move, score, depth, pv, source):
        self.board, self.move, self.score, self.depth, self.pv, self.source = board, move, score, depth, pv, source

    def score_str(self):
        if self.score is None:
            return "?"
        s = self.score.pov(self.board.turn)
        if s.is_mate():
            return f"M{s.mate()}"
        return f"{s.score() / 100:+.2f}"


def cloud_eval(board, multipv=1, timeout=4.0):
    url = "https://lichess.org/api/cloud-eval?" + urllib.parse.urlencode(
        {"fen": board.fen(), "multiPv": multipv})
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.load(r)
    pv = data["pvs"][0]
    moves = [chess.Move.from_uci(u) for u in pv["moves"].split()]
    if "mate" in pv:
        score = chess.engine.PovScore(chess.engine.Mate(pv["mate"]), chess.WHITE)
    else:
        score = chess.engine.PovScore(chess.engine.Cp(pv["cp"]), chess.WHITE)
    return Result(board, moves[0], score, data.get("depth"), moves, "lichess-cloud")


class Analyzer:
    """Background analyser. Call request(board); poll results() for finished analyses.

    Only the most recently requested position is analysed; stale requests are dropped.
    """

    def __init__(self, engine_path=None, depth=None, movetime=1.0, threads=None, hash_mb=128,
                 cloud=True, log=print):
        self.log = log
        self.depth, self.movetime, self.cloud = depth, movetime, cloud
        self._q = queue.Queue()
        self._out = queue.Queue()
        self._stop = threading.Event()
        path = find_stockfish(engine_path)
        self.engine = None
        if path:
            try:
                self.engine = chess.engine.SimpleEngine.popen_uci(path)
                opts = {"Hash": hash_mb}
                if threads:
                    opts["Threads"] = threads
                self.engine.configure(opts)
                self.log(f"[engine] Stockfish: {path}")
            except Exception as e:  # noqa: BLE001
                self.log(f"[engine] failed to start {path}: {e}")
        if self.engine is None:
            self.log("[engine] no local Stockfish found" + (" - using Lichess cloud eval" if cloud else ""))
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request(self, board):
        self._q.put(board.copy())

    def results(self):
        out = []
        while True:
            try:
                out.append(self._out.get_nowait())
            except queue.Empty:
                return out

    def _latest(self):
        board = self._q.get()
        while True:
            try:
                board = self._q.get_nowait()
            except queue.Empty:
                return board

    def _run(self):
        while not self._stop.is_set():
            board = self._latest()
            if board is None:
                return
            if board.is_game_over():
                continue
            res = None
            if self.engine is not None:
                try:
                    limit = chess.engine.Limit(depth=self.depth) if self.depth else chess.engine.Limit(time=self.movetime)
                    info = self.engine.analyse(board, limit)
                    pv = info.get("pv") or []
                    if pv:
                        res = Result(board, pv[0], info.get("score"), info.get("depth"), pv, "stockfish")
                except Exception as e:  # noqa: BLE001
                    self.log(f"[engine] analyse failed: {e}")
            if res is None and self.cloud:
                try:
                    res = cloud_eval(board)
                except Exception as e:  # noqa: BLE001
                    self.log(f"[engine] cloud eval failed: {e}")
            if res is not None:
                self._out.put(res)

    def close(self):
        self._stop.set()
        self._q.put(None)
        if self.engine is not None:
            try:
                self.engine.quit()
            except Exception:  # noqa: BLE001
                pass
