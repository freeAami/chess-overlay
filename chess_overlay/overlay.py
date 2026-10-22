"""Transparent, click-through, always-on-top window drawing an arrow over the board."""
import math

import cv2
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

LABEL_H = 26  # logical px strip above the board for the eval label


def arrow_polygon(a, b, square):
    """Polygon (N x 2 float array) for an arrow from point a to point b, sized by square size."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return np.zeros((0, 2))
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    shaft = square * 0.17
    head_len = min(square * 0.42, length * 0.5)
    head_w = square * 0.40
    start = square * 0.18
    sx, sy = ax + ux * start, ay + uy * start
    hx, hy = bx - ux * head_len, by - uy * head_len
    pts = [
        (sx + px * shaft / 2, sy + py * shaft / 2),
        (hx + px * shaft / 2, hy + py * shaft / 2),
        (hx + px * head_w / 2, hy + py * head_w / 2),
        (bx, by),
        (hx - px * head_w / 2, hy - py * head_w / 2),
        (hx - px * shaft / 2, hy - py * shaft / 2),
        (sx - px * shaft / 2, sy - py * shaft / 2),
    ]
    return np.array(pts, float)


class Overlay(QtWidgets.QWidget):
    def __init__(self, region, dpr=1.0):
        super().__init__(None, QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
                         | QtCore.Qt.Tool | QtCore.Qt.WindowTransparentForInput
                         | QtCore.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.dpr = dpr
        self.region = None
        self.arrows = []  # list of (poly physical coords, QColor)
        self.label = ""
        self.set_region(region)

    def set_region(self, region):
        self.region = tuple(region)
        x, y, w, h = region
        self.setGeometry(int(x / self.dpr), int(y / self.dpr) - LABEL_H,
                         int(math.ceil(w / self.dpr)), int(math.ceil(h / self.dpr)) + LABEL_H)

    def square_size(self):
        return self.region[2] / 8.0

    def _center(self, row, col):
        s = self.square_size()
        return ((col + 0.5) * s, (row + 0.5) * s)

    def set_arrow(self, from_rc, to_rc, label="", color=(40, 200, 90, 200), extra=None):
        s = self.square_size()
        self.arrows = [(arrow_polygon(self._center(*from_rc), self._center(*to_rc), s), QtGui.QColor(*color))]
        for (f, t, c) in (extra or []):
            self.arrows.append((arrow_polygon(self._center(*f), self._center(*t), s), QtGui.QColor(*c)))
        self.label = label
        self.update()

    def set_label(self, label):
        self.label = label
        self.update()

    def clear(self):
        self.arrows = []
        self.label = ""
        self.update()

    @property
    def has_arrow(self):
        return bool(self.arrows)

    def capture_mask(self):
        """Bool mask (board physical pixels) of what we draw over the board, or None."""
        if not self.arrows:
            return None
        w, h = int(round(self.region[2])), int(round(self.region[3]))
        m = np.zeros((h, w), np.uint8)
        for poly, _ in self.arrows:
            cv2.fillPoly(m, [np.round(poly).astype(np.int32)], 1)
        m = cv2.dilate(m, np.ones((5, 5), np.uint8))
        return m > 0

    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.translate(0, LABEL_H)
        p.scale(1 / self.dpr, 1 / self.dpr)
        for poly, color in self.arrows:
            path = QtGui.QPainterPath()
            path.moveTo(poly[0][0], poly[0][1])
            for x, y in poly[1:]:
                path.lineTo(x, y)
            path.closeSubpath()
            p.fillPath(path, QtGui.QBrush(color))
            pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 120))
            pen.setWidthF(self.square_size() * 0.02)
            p.setPen(pen)
            p.drawPath(path)
        p.resetTransform()
        if self.label:
            font = QtGui.QFont("Sans", 11, QtGui.QFont.Bold)
            p.setFont(font)
            fm = QtGui.QFontMetrics(font)
            tw = fm.horizontalAdvance(self.label) + 12
            p.setBrush(QtGui.QColor(0, 0, 0, 170))
            p.setPen(QtCore.Qt.NoPen)
            p.drawRoundedRect(0, 2, tw, LABEL_H - 4, 5, 5)
            p.setPen(QtGui.QColor(255, 255, 255))
            p.drawText(6, LABEL_H - 8, self.label)
        p.end()
