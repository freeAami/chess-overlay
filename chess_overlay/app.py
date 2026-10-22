"""CLI entry points: `calibrate` (pick/confirm the board region) and `run` (live overlay)."""
import argparse
import json
import os
import sys
import time

import chess
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .capture import Screen
from .engine import Analyzer
from .locate import Grid, find_board, refine_grid
from .overlay import Overlay
from .recognize import PieceRecognizer, UNKNOWN, placement_str
from .state import GameTracker

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".chess_overlay")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
TEMPLATES_PATH = os.path.join(CONFIG_DIR, "templates.json")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def np_to_qimage(img_bgr):
    h, w = img_bgr.shape[:2]
    rgb = np.ascontiguousarray(img_bgr[:, :, ::-1])
    return QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()


class RegionPicker(QtWidgets.QWidget):
    """Full-screen screenshot; drag a rectangle around the board (or Enter to accept the suggestion)."""

    def __init__(self, shot, suggestion, dpr):
        super().__init__(None, QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.shot = np_to_qimage(shot)
        self.dpr = dpr
        self.rect = None
        if suggestion is not None:
            x, y, w, h = suggestion
            self.rect = QtCore.QRectF(x / dpr, y / dpr, w / dpr, h / dpr)
        self.drag_start = None
        self.result = None
        self.setCursor(QtCore.Qt.CrossCursor)
        geo = QtWidgets.QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(geo)
        self.showFullScreen()

    def paintEvent(self, _e):
        p = QtGui.QPainter(self)
        p.drawImage(self.rect_logical(), self.shot)
        p.fillRect(self.rect_logical(), QtGui.QColor(0, 0, 0, 90))
        if self.rect is not None:
            p.drawImage(self.rect, self.shot, QtCore.QRectF(self.rect.x() * self.dpr, self.rect.y() * self.dpr,
                                                            self.rect.width() * self.dpr, self.rect.height() * self.dpr))
            pen = QtGui.QPen(QtGui.QColor(0, 220, 80), 3)
            p.setPen(pen)
            p.drawRect(self.rect)
        p.setPen(QtGui.QColor(255, 255, 255))
        p.setFont(QtGui.QFont("Sans", 14, QtGui.QFont.Bold))
        msg = ("Drag a box around the chess board.  Enter = accept green box,  Esc = cancel"
               if self.rect is not None else "Drag a box around the chess board.  Esc = cancel")
        p.fillRect(0, 0, self.width(), 40, QtGui.QColor(0, 0, 0, 180))
        p.drawText(12, 28, msg)
        p.end()

    def rect_logical(self):
        return QtCore.QRectF(0, 0, self.shot.width() / self.dpr, self.shot.height() / self.dpr)

    def mousePressEvent(self, e):
        self.drag_start = e.position()
        self.rect = QtCore.QRectF(self.drag_start, self.drag_start)
        self.update()

    def mouseMoveEvent(self, e):
        if self.drag_start is not None:
            self.rect = QtCore.QRectF(self.drag_start, e.position()).normalized()
            self.update()

    def mouseReleaseEvent(self, e):
        if self.drag_start is not None:
            self.rect = QtCore.QRectF(self.drag_start, e.position()).normalized()
            self.drag_start = None
            self.update()

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and self.rect is not None and self.rect.width() > 20:
            r = self.rect
            self.result = (r.x() * self.dpr, r.y() * self.dpr, r.width() * self.dpr, r.height() * self.dpr)
            self.close()
        elif e.key() == QtCore.Qt.Key_Escape:
            self.close()


def _dpr(app):
    return float(app.primaryScreen().devicePixelRatio())


def _region_to_grid(shot, region):
    x, y, w, h = region
    s = min(w, h) / 8.0
    return refine_grid(shot, Grid(x, y, s))


def cmd_calibrate(args):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    screen = Screen()
    shot = screen.grab()
    origin = (screen.virtual_monitor["left"], screen.virtual_monitor["top"])
    grid = find_board(shot, debug=args.debug)
    suggestion = grid.region() if grid else None
    log("auto-detected board:" if grid else "no board auto-detected;", grid or "drag one manually")
    picker = RegionPicker(shot, suggestion, _dpr(app))
    while picker.isVisible():
        app.processEvents()
        time.sleep(0.01)
    if picker.result is None:
        log("cancelled")
        return 1
    grid = _region_to_grid(shot, picker.result)
    region = grid.region()
    cfg = load_config()
    cfg["region"] = [region[0] + origin[0], region[1] + origin[1], region[2], region[3]]
    save_config(cfg)
    log("saved board region", cfg["region"], "->", CONFIG_PATH)
    rec = PieceRecognizer()
    if rec.learn_from_start(screen.grab(cfg["region"])):
        rec.save(TEMPLATES_PATH)
        log(f"learned piece templates from start position (white at {'bottom' if rec.white_bottom else 'top'})")
    else:
        log("start position not on screen; templates will be learned automatically when a new game starts")
    return 0


class Runner:
    def __init__(self, args):
        self.args = args
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.screen = Screen()
        cfg = load_config()
        if args.region:
            region = [int(v) for v in args.region.split(",")]
        elif "region" in cfg:
            region = cfg["region"]
        else:
            shot = self.screen.grab()
            grid = find_board(shot)
            if grid is None:
                log("no board found on screen. Run `python -m chess_overlay calibrate` first.")
                sys.exit(1)
            o = self.screen.virtual_monitor
            r = grid.region()
            region = [r[0] + o["left"], r[1] + o["top"], r[2], r[3]]
            log("auto-detected board at", region)
        self.region = tuple(region)
        self.rec = PieceRecognizer()
        if not args.recalibrate and self.rec.load(TEMPLATES_PATH):
            log("loaded piece templates")
        self.tracker = GameTracker()
        self.overlay = Overlay(self.region, _dpr(self.app))
        self.overlay.show()
        self.analyzer = Analyzer(engine_path=args.engine, depth=args.depth, movetime=args.time,
                                 threads=args.threads, cloud=not args.no_cloud, log=log)
        self.prev_placement = None
        self.ref_img = None  # clean board image from when the current arrow was drawn
        self.stable = 0
        self.last_result = None
        self.user_color = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / args.fps))

    # ----- helpers -----
    def rc(self, square):
        f, r = chess.square_file(square), chess.square_rank(square)
        if self.rec.white_bottom:
            return (7 - r, f)
        return (r, 7 - f)

    def side_to_show(self):
        if self.args.side == "white":
            return chess.WHITE
        if self.args.side == "black":
            return chess.BLACK
        return chess.WHITE if self.rec.white_bottom else chess.BLACK

    def clean_grab(self):
        """Grab the board with our own arrow hidden."""
        if not self.overlay.has_arrow:
            return self.screen.grab(self.region)
        self.overlay.hide()
        self.app.processEvents()
        time.sleep(0.05)
        img = self.screen.grab(self.region)
        self.overlay.show()
        self.app.processEvents()
        return img

    def board_changed_under_arrow(self, img):
        """Pixels outside our arrow differ from when the arrow was drawn -> something is moving."""
        if self.ref_img is None or self.ref_img.shape != img.shape:
            return False
        mask = self.overlay.capture_mask()
        diff = np.abs(img.astype(np.int16) - self.ref_img.astype(np.int16)).sum(2)
        if mask is not None:
            diff[mask] = 0
        return (diff > 60).mean() > 0.002

    def request_analysis(self):
        b = self.tracker.board
        self.overlay.clear()
        if b.is_game_over():
            self.overlay.set_label("game over")
            return
        if self.args.both or b.turn == self.side_to_show():
            self.overlay.set_label("thinking...")
            self.analyzer.request(b)

    # ----- main loop -----
    def tick(self):
        try:
            self._tick()
        except Exception as e:  # noqa: BLE001
            log("tick error:", repr(e))

    def _tick(self):
        img = self.screen.grab(self.region)
        if not self.rec.calibrated:
            if self.rec.learn_from_start(img):
                self.rec.save(TEMPLATES_PATH)
                self.tracker.reset()
                log(f"learned piece templates (white at {'bottom' if self.rec.white_bottom else 'top'})")
                self.request_analysis()
            else:
                self.overlay.set_label("waiting for start position to calibrate...")
            return

        if self.overlay.has_arrow and self.board_changed_under_arrow(img):
            img = self.clean_grab()
            self.ref_img = img
            placement = self.rec.classify(img)
        else:
            placement = self.rec.classify(img, self.overlay.capture_mask())
        self.last_img = img
        if placement == self.prev_placement:
            self.stable += 1
        else:
            self.stable = 0
        self.prev_placement = placement
        if self.stable < 1:
            return

        from .state import matches
        if matches(self.tracker.board, placement):
            self._poll_engine()
            return

        if self.overlay.has_arrow:  # something moved under our arrow: re-read without it
            placement = self.rec.classify(self.clean_grab())
            if matches(self.tracker.board, placement):
                return

        # board may have been flipped (new game as the other colour)
        flipped = self.rec.flipped()
        if flipped.looks_like_start(flipped.features(img)) and not self.rec.looks_like_start(self.rec.features(img)):
            self.rec = flipped
            self.rec.save(TEMPLATES_PATH)
            log("board orientation flipped; now white at", "bottom" if self.rec.white_bottom else "top")
            placement = self.rec.classify(img)

        before = self.tracker.board.fen()
        changed = self.tracker.update(placement, prefer_turn=self.side_to_show())
        if changed and self.tracker.board.fen() != before:
            b = self.tracker.board
            if self.tracker.uncertain:
                log("resynced from screen (turn guessed):", b.fen())
            else:
                log(f"move {b.fullmove_number}: {b.peek().uci() if b.move_stack else '-'}  fen={b.fen()}")
            if self.args.debug:
                log("\n" + placement_str(placement))
            self.request_analysis()
        self._poll_engine()

    def _poll_engine(self):
        for res in self.analyzer.results():
            if res.board.fen() != self.tracker.board.fen():
                continue
            mv = res.move
            label = f"{mv.uci()}  {res.score_str()}  d{res.depth}  ({res.source})"
            extra = []
            if self.args.show_reply and len(res.pv) > 1:
                extra.append((self.rc(res.pv[1].from_square), self.rc(res.pv[1].to_square), (230, 80, 80, 150)))
            self.ref_img = self.clean_grab()
            self.overlay.set_arrow(self.rc(mv.from_square), self.rc(mv.to_square), label, extra=extra)
            log("best:", self.tracker.board.san(mv), label)

    def run(self):
        try:
            return self.app.exec()
        finally:
            self.analyzer.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chess_overlay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate", help="pick the board region on screen (auto-detect + manual drag)")
    c.add_argument("--debug", action="store_true")
    r = sub.add_parser("run", help="watch the board and draw the best move")
    r.add_argument("--region", help="x,y,w,h in physical pixels (skips saved calibration)")
    r.add_argument("--engine", help="path to a Stockfish binary")
    r.add_argument("--depth", type=int, help="fixed search depth (default: time-limited)")
    r.add_argument("--time", type=float, default=1.0, help="seconds per analysis (default 1.0)")
    r.add_argument("--threads", type=int)
    r.add_argument("--side", choices=["auto", "white", "black"], default="auto",
                   help="which side to suggest moves for (auto = the side at the bottom)")
    r.add_argument("--both", action="store_true", help="suggest for both sides")
    r.add_argument("--show-reply", action="store_true", help="also draw the expected reply in red")
    r.add_argument("--fps", type=float, default=6.0)
    r.add_argument("--no-cloud", action="store_true", help="never use Lichess cloud eval")
    r.add_argument("--recalibrate", action="store_true", help="ignore saved piece templates")
    r.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "calibrate":
        return cmd_calibrate(args)
    return Runner(args).run()
