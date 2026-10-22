"""Find the 8x8 board on a screenshot.

Strategy: adjacent squares of a chess board always differ in colour, so the 7
interior grid lines (plus the 2 borders) show up as long, evenly spaced edge
lines. We score every (offset, spacing) pair against 1-D edge profiles, keep
the best candidates and verify them in 2-D with a checkerboard-colour test.
"""
from dataclasses import dataclass, asdict

import cv2
import numpy as np
from scipy.ndimage import maximum_filter1d


@dataclass
class Grid:
    x0: float
    y0: float
    size: float  # square size in pixels

    @property
    def length(self):
        return self.size * 8

    def region(self):
        return (int(round(self.x0)), int(round(self.y0)),
                int(round(self.length)), int(round(self.length)))

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        return Grid(float(d["x0"]), float(d["y0"]), float(d["size"]))


def _edge_maps(gray, thr=10):
    g = gray.astype(np.int16)
    vx = np.abs(np.diff(g, axis=1)) > thr  # H x (W-1): vertical edge between col c and c+1
    hy = np.abs(np.diff(g, axis=0)) > thr  # (H-1) x W
    return vx, hy


def _square_bg_colors(img, grid):
    """Median colour of a small patch near the top-left corner of each square (8x8x3)."""
    s = grid.size
    out = np.zeros((8, 8, 3), np.float32)
    k = max(2, int(s * 0.08))
    for r in range(8):
        for c in range(8):
            x = int(round(grid.x0 + c * s + s * 0.05))
            y = int(round(grid.y0 + r * s + s * 0.05))
            patch = img[y:y + k, x:x + k].reshape(-1, 3)
            if patch.size == 0:
                return None
            out[r, c] = np.median(patch, axis=0)
    return out


def checker_score(img, grid):
    """How much the square backgrounds look like a 2-colour checkerboard (0..1), and colour gap."""
    cols = _square_bg_colors(img, grid)
    if cols is None:
        return 0.0, 0.0
    rr, cc = np.mgrid[0:8, 0:8]
    a = cols[(rr + cc) % 2 == 0]
    b = cols[(rr + cc) % 2 == 1]
    ma, mb = np.median(a, axis=0), np.median(b, axis=0)
    gap = float(np.abs(ma - mb).sum())
    within = float(np.median(np.abs(a - ma).sum(1)) + np.median(np.abs(b - mb).sum(1)))
    score = gap / (gap + within + 1e-6)
    return score, gap


def line_score(vx, hy, grid):
    """Fraction of the board extent covered by edges along the 7 interior grid lines."""
    s = grid.size
    L = int(round(grid.length))
    y0, x0 = int(round(grid.y0)), int(round(grid.x0))
    H, W = hy.shape[0], vx.shape[1]
    if y0 < 0 or x0 < 0 or y0 + L > H + 1 or x0 + L > W + 1:
        return 0.0
    vals = []
    for k in range(1, 8):
        x = int(round(grid.x0 + k * s)) - 1
        lo, hi = max(0, x - 2), min(W, x + 2)
        vals.append(vx[y0:y0 + L, lo:hi].any(axis=1).mean() if hi > lo else 0.0)
        y = int(round(grid.y0 + k * s)) - 1
        lo, hi = max(0, y - 2), min(H, y + 2)
        vals.append(hy[lo:hi, x0:x0 + L].any(axis=0).mean() if hi > lo else 0.0)
    return float(np.mean(vals))


def find_board(img, min_size=160, debug=False):
    """Return a Grid (in `img` pixel coordinates) or None."""
    h, w = img.shape[:2]
    scale = min(1.0, 520.0 / max(h, w))
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    vx, hy = _edge_maps(gray)
    H, W = gray.shape
    vxd = maximum_filter1d(vx.astype(np.uint8), 3, axis=1).astype(np.int32)
    hyd = maximum_filter1d(hy.astype(np.uint8), 3, axis=0).astype(np.int32)
    C = np.zeros((H + 1, W - 1), np.int32)
    C[1:] = np.cumsum(vxd, axis=0)          # C[i, x] = edges in column x above row i
    R = np.zeros((H - 1, W + 1), np.int32)
    R[:, 1:] = np.cumsum(hyd, axis=1)       # R[y, j] = edges in row y left of column j

    smin = max(int(min_size * scale / 8), 6)
    smax = min(H, W) // 8
    cands = []
    for s in range(smin, smax + 1):
        L = 8 * s
        nx, ny = W - 1 - L, H - 1 - L
        if nx <= 0 or ny <= 0:
            break
        score = np.zeros((ny, nx), np.int32)
        for k in range(1, 8):
            x = k * s - 1
            score += C[L:L + ny, x:x + nx] - C[0:ny, x:x + nx]
            score += R[x:x + ny, L:L + nx] - R[x:x + ny, 0:nx]
        flat = score.ravel()
        top = np.argpartition(flat, -3)[-3:] if flat.size > 3 else np.arange(flat.size)
        for i in top:
            y0, x0 = divmod(int(i), nx)
            cands.append((flat[i] / (14.0 * L), Grid(float(x0), float(y0), float(s))))
    if not cands:
        return None
    cands.sort(key=lambda t: -t[0])
    best, best_score = None, 0.0
    for ls, g in cands[:30]:
        if ls < 0.45:
            break
        cs, gap = checker_score(small, g)
        if gap < 20:
            continue
        score = 0.5 * min(ls, 1.0) + 0.5 * cs
        if debug:
            print(f"cand {g} line={ls:.2f} checker={cs:.2f} gap={gap:.0f} -> {score:.2f}")
        if score > best_score:
            best, best_score = g, score
    if best is None or best_score < 0.6:
        return None
    full = Grid(best.x0 / scale, best.y0 / scale, best.size / scale)
    return refine_grid(img, full, search_frac=0.3)


def refine_grid(img, grid, search_frac=0.2):
    """Snap an approximate grid onto the real square boundaries (sub-pixel, least squares)."""
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    vx, hy = _edge_maps(gray)
    H, W = gray.shape
    s = grid.size
    rad = max(2, int(s * search_frac))
    L = int(round(grid.length))

    def fit(prof_fn, start, n):
        ks, pos = [], []
        for k in range(1, 8):
            c = int(round(start + k * s))
            lo, hi = max(1, c - rad), min(n - 1, c + rad)
            if hi <= lo:
                continue
            seg = prof_fn(lo, hi)
            if seg.max() <= 0:
                continue
            ks.append(k)
            pos.append(lo + int(seg.argmax()))
        if len(ks) < 4:
            return start, s
        A = np.vstack([np.ones(len(ks)), ks]).T
        b0, step = np.linalg.lstsq(A, np.array(pos, float), rcond=None)[0]
        return b0, step

    y0i, x0i = int(round(grid.y0)), int(round(grid.x0))
    ya, yb = max(0, y0i), min(H, y0i + L)
    xa, xb = max(0, x0i), min(W, x0i + L)
    nx0, sx = fit(lambda lo, hi: vx[ya:yb, lo - 1:hi - 1].sum(0), grid.x0, W)
    ny0, sy = fit(lambda lo, hi: hy[lo - 1:hi - 1, xa:xb].sum(1), grid.y0, H)
    size = (sx + sy) / 2.0
    if abs(sx - sy) > 0.08 * s:  # inconsistent refinement; keep original
        return grid
    return Grid(nx0, ny0, size)
