import numpy as np


class Screen:
    """Screen grabber. Uses mss when it works, else Pillow's ImageGrab.

    All coordinates are physical pixels on the virtual desktop.
    """

    def __init__(self):
        self._sct = None
        self._pil = None
        try:
            import mss
            sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
            sct.grab(sct.monitors[0])  # probe; some X servers reject XShm/XGetImage
            self._sct = sct
        except Exception:  # noqa: BLE001
            from PIL import ImageGrab
            self._pil = ImageGrab
            probe = ImageGrab.grab(all_screens=True) if _supports_all_screens() else ImageGrab.grab()
            self._pil_size = probe.size

    @property
    def virtual_monitor(self):
        if self._sct is not None:
            return self._sct.monitors[0]
        w, h = self._pil_size
        return {"left": 0, "top": 0, "width": w, "height": h}

    def grab(self, region=None):
        if region is None:
            m = self.virtual_monitor
            region = (m["left"], m["top"], m["width"], m["height"])
        x, y, w, h = (int(round(v)) for v in region)
        if self._sct is not None:
            shot = self._sct.grab({"left": x, "top": y, "width": w, "height": h})
            img = np.asarray(shot)[:, :, :3]  # BGRA -> BGR
            return np.ascontiguousarray(img)
        kw = {"all_screens": True} if _supports_all_screens() else {}
        im = self._pil.grab(bbox=(x, y, x + w, y + h), **kw).convert("RGB")
        return np.ascontiguousarray(np.asarray(im)[:, :, ::-1])

    def close(self):
        if self._sct is not None:
            self._sct.close()


def _supports_all_screens():
    import sys
    return sys.platform.startswith("win")
