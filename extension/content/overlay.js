// SVG arrow layer positioned over the board element + a small eval badge.

class CoOverlay {
  constructor() {
    const ns = "http://www.w3.org/2000/svg";
    this.svg = document.createElementNS(ns, "svg");
    this.svg.setAttribute("viewBox", "0 0 8 8");
    this.svg.setAttribute("preserveAspectRatio", "none");
    Object.assign(this.svg.style, {
      position: "fixed", left: "0", top: "0", width: "0", height: "0",
      pointerEvents: "none", zIndex: "2147483000", overflow: "visible",
    });
    this.badge = document.createElement("div");
    Object.assign(this.badge.style, {
      position: "fixed", zIndex: "2147483001", pointerEvents: "none",
      font: "600 12px/1 system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
      padding: "5px 8px", borderRadius: "8px", color: "#fff",
      background: "rgba(15, 23, 42, 0.85)", boxShadow: "0 2px 8px rgba(0,0,0,.35)",
      letterSpacing: "0.2px", display: "none", whiteSpace: "nowrap",
    });
    this.ns = ns;
    this.rect = null;
    this.attached = false;
  }

  attach() {
    if (this.attached) return;
    document.documentElement.appendChild(this.svg);
    document.documentElement.appendChild(this.badge);
    this.attached = true;
  }

  detach() {
    if (!this.attached) return;
    this.svg.remove();
    this.badge.remove();
    this.attached = false;
  }

  setRect(rect) {
    if (!rect) return;
    this.attach();
    const r = this.rect;
    if (r && r.left === rect.left && r.top === rect.top && r.width === rect.width && r.height === rect.height) return;
    this.rect = { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
    Object.assign(this.svg.style, {
      left: rect.left + "px", top: rect.top + "px", width: rect.width + "px", height: rect.height + "px",
    });
    Object.assign(this.badge.style, { left: rect.left + 6 + "px", top: rect.top + 6 + "px" });
  }

  // arrows: [{from:[f,r], to:[f,r], color, opacity}]
  setArrows(arrows, flipped) {
    while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
    const center = ([f, r]) => [(flipped ? 7 - f : f) + 0.5, (flipped ? r : 7 - r) + 0.5];
    for (const a of arrows) {
      const poly = document.createElementNS(this.ns, "polygon");
      poly.setAttribute("points", CoOverlay.arrowPoints(center(a.from), center(a.to)));
      poly.setAttribute("fill", a.color);
      poly.setAttribute("opacity", a.opacity != null ? a.opacity : 0.85);
      poly.setAttribute("stroke", "rgba(0,0,0,0.25)");
      poly.setAttribute("stroke-width", "0.03");
      poly.setAttribute("stroke-linejoin", "round");
      this.svg.appendChild(poly);
    }
  }

  static arrowPoints([x1, y1], [x2, y2]) {
    const dx = x2 - x1, dy = y2 - y1;
    const L = Math.hypot(dx, dy) || 1;
    const ux = dx / L, uy = dy / L, px = -uy, py = ux;
    const start = 0.3, w = 0.11, hw = 0.3, hl = 0.42;
    const sx = x1 + ux * start, sy = y1 + uy * start;
    const bx = x2 - ux * hl, by = y2 - uy * hl;
    const pts = [
      [sx + px * w, sy + py * w], [bx + px * w, by + py * w], [bx + px * hw, by + py * hw],
      [x2, y2], [bx - px * hw, by - py * hw], [bx - px * w, by - py * w], [sx - px * w, sy - py * w],
    ];
    return pts.map((p) => p.map((v) => v.toFixed(3)).join(",")).join(" ");
  }

  setBadge(text) {
    if (!text) { this.badge.style.display = "none"; return; }
    this.badge.textContent = text;
    this.badge.style.display = "block";
  }

  clear() {
    this.setArrows([], false);
    this.setBadge("");
  }
}
