"""Piece recognition that calibrates itself from the starting position.

Every square is reduced to a foreground silhouette (pixels that differ from the
square's own background colour, estimated from its corners), hole-filled and
resized to SQ x SQ.  When the start position is on screen we learn one mean
silhouette per piece type (all 6 types appear in the start position) plus a
brightness threshold separating white and black pieces.  Afterwards each
square is classified by silhouette IoU against those 6 templates.
"""
import json
import os

import cv2
import numpy as np
import chess

SQ = 32
UNKNOWN = "?"
_TYPES = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]

_START_ROWS = {  # row index from the top when white is at the bottom -> piece types left to right
    0: [chess.ROOK, chess.KNIGHT, chess.BISHOP, chess.QUEEN, chess.KING, chess.BISHOP, chess.KNIGHT, chess.ROOK],
    1: [chess.PAWN] * 8,
    6: [chess.PAWN] * 8,
    7: [chess.ROOK, chess.KNIGHT, chess.BISHOP, chess.QUEEN, chess.KING, chess.BISHOP, chess.KNIGHT, chess.ROOK],
}


def _fill_holes(mask):
    h, w = mask.shape
    inv = (~mask).astype(np.uint8)
    ff = inv.copy()
    border = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, border, (0, 0), 0)
    cv2.floodFill(ff, border, (w - 1, 0), 0)
    cv2.floodFill(ff, border, (0, h - 1), 0)
    cv2.floodFill(ff, border, (w - 1, h - 1), 0)
    return mask | (ff > 0)


class SquareFeatures:
    __slots__ = ("mask", "raw", "known", "frac", "brightness")

    def __init__(self, mask, raw, known, frac, brightness):
        self.mask, self.raw, self.known, self.frac, self.brightness = mask, raw, known, frac, brightness

    def stacked(self):
        return np.concatenate([self.mask, self.raw], axis=0)


def square_features(crop, ignore=None, fg_thr=45):
    """crop: BGR square image. ignore: optional bool mask (same shape) of pixels to ignore."""
    img = cv2.resize(crop, (SQ, SQ), interpolation=cv2.INTER_AREA)
    if ignore is not None and ignore.any():
        known = cv2.resize(ignore.astype(np.uint8), (SQ, SQ), interpolation=cv2.INTER_AREA) == 0
    else:
        known = np.ones((SQ, SQ), bool)
    k = 4
    corners = np.concatenate([
        img[:k, :k].reshape(-1, 3), img[:k, -k:].reshape(-1, 3),
        img[-k:, :k].reshape(-1, 3), img[-k:, -k:].reshape(-1, 3)])
    ck = np.concatenate([known[:k, :k].ravel(), known[:k, -k:].ravel(),
                         known[-k:, :k].ravel(), known[-k:, -k:].ravel()])
    if ck.sum() >= 8:
        corners = corners[ck]
    bg = np.median(corners, axis=0)
    dist = np.abs(img.astype(np.int16) - bg.astype(np.int16)).sum(2)
    raw = (dist > fg_thr) & known
    fg = _fill_holes(raw)
    fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    n_known = max(1, int(known.sum()))
    frac = float(fg.sum()) / n_known
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brightness = float(np.median(gray[fg])) if fg.sum() > 4 else 0.0
    return SquareFeatures(fg, raw, known, frac, brightness)


def split_squares(board_img):
    """Yield (row, col, crop) with row 0 at the top of the image."""
    h, w = board_img.shape[:2]
    ys = np.linspace(0, h, 9)
    xs = np.linspace(0, w, 9)
    for r in range(8):
        for c in range(8):
            y0, y1 = int(round(ys[r])), int(round(ys[r + 1]))
            x0, x1 = int(round(xs[c])), int(round(xs[c + 1]))
            yield r, c, (slice(y0, y1), slice(x0, x1))


class PieceRecognizer:
    EMPTY_FRAC = 0.06
    NOISE_FRAC = 0.14
    MIN_IOU = 0.45

    def __init__(self):
        self.templates = None      # {piece_type: float mask SQxSQ}
        self.color_thr = 128.0     # foreground brightness above -> white piece
        self.white_bottom = True

    # ---------- persistence ----------
    def save(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {"color_thr": self.color_thr, "white_bottom": self.white_bottom,
                "templates": {k: m.tolist() for k, m in self.templates.items()}}
        with open(path, "w") as f:
            json.dump(data, f)

    def load(self, path):
        if not os.path.exists(path):
            return False
        with open(path) as f:
            data = json.load(f)
        self.color_thr = data["color_thr"]
        self.white_bottom = data["white_bottom"]
        self.templates = {k: np.array(m, np.float32) for k, m in data["templates"].items()}
        return True

    @property
    def calibrated(self):
        return self.templates is not None

    # ---------- calibration ----------
    def features(self, board_img, ignore=None):
        feats = {}
        for r, c, sl in split_squares(board_img):
            ig = ignore[sl] if ignore is not None else None
            feats[(r, c)] = square_features(board_img[sl], ig)
        return feats

    def looks_like_start(self, feats):
        for (r, c), f in feats.items():
            if f.known.mean() < 0.95:
                return False
            if r in (0, 1, 6, 7) and f.frac < 0.08:
                return False
            if r in (2, 3, 4, 5) and f.frac > self.EMPTY_FRAC:
                return False
        top = np.median([feats[(r, c)].brightness for r in (0, 1) for c in range(8)])
        bot = np.median([feats[(r, c)].brightness for r in (6, 7) for c in range(8)])
        return abs(top - bot) > 40

    def learn_from_start(self, board_img):
        feats = self.features(board_img)
        if not self.looks_like_start(feats):
            return False
        top = np.median([feats[(r, c)].brightness for r in (0, 1) for c in range(8)])
        bot = np.median([feats[(r, c)].brightness for r in (6, 7) for c in range(8)])
        self.white_bottom = bool(bot > top)
        self.color_thr = float((top + bot) / 2)
        acc = {}
        for r, types in _START_ROWS.items():
            color = chess.BLACK if (r <= 1) == self.white_bottom else chess.WHITE
            for c, t in enumerate(types):
                # if black is at the bottom the back rank is mirrored (K/Q swap); handle via column flip
                cc = c if self.white_bottom else 7 - c
                key = chess.Piece(t, color).symbol()
                acc.setdefault(key, []).append(feats[(r, cc)].stacked().astype(np.float32))
        self.templates = {k: np.mean(ms, axis=0) for k, ms in acc.items()}
        return True

    # ---------- classification ----------
    def classify_square(self, f):
        if f.known.mean() < 0.3:
            return UNKNOWN
        if f.frac < self.EMPTY_FRAC:
            return None
        color = chess.WHITE if f.brightness > self.color_thr else chess.BLACK
        stacked = f.stacked()
        known = np.concatenate([f.known, f.known], axis=0)
        best_p, best_iou = None, 0.0
        for key, tmpl in self.templates.items():
            p = chess.Piece.from_symbol(key)
            if p.color != color:
                continue
            tb = tmpl > 0.5
            inter = (stacked & tb & known).sum()
            union = ((stacked | tb) & known).sum()
            iou = inter / union if union else 0.0
            if iou > best_iou:
                best_p, best_iou = p, iou
        if best_iou < self.MIN_IOU:
            return None if f.frac < self.NOISE_FRAC else UNKNOWN
        return best_p

    def to_square(self, r, c):
        if self.white_bottom:
            return chess.square(c, 7 - r)
        return chess.square(7 - c, r)

    def classify(self, board_img, ignore=None):
        """Return {chess.Square: Piece | None | UNKNOWN}."""
        feats = self.features(board_img, ignore)
        return {self.to_square(r, c): self.classify_square(f) for (r, c), f in feats.items()}

    def flipped(self):
        other = PieceRecognizer()
        other.templates, other.color_thr = self.templates, self.color_thr
        other.white_bottom = not self.white_bottom
        return other


def placement_str(placement):
    rows = []
    for rank in range(7, -1, -1):
        row = ""
        for file in range(8):
            p = placement.get(chess.square(file, rank))
            row += "." if p is None else (UNKNOWN if p == UNKNOWN else p.symbol())
        rows.append(row)
    return "\n".join(rows)
