"""Tiny dependency-free SVG charts. Colours come from CSS classes so the report can theme them."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

W = 720


def _pace(v):
    s = int(round(v * 60))
    return f"{s // 60}:{s % 60:02d}"


def _num(v, unit=""):
    if unit in ("min/km",):
        return _pace(v)
    return f"{v:,.0f}" if abs(v) >= 10 else f"{v:.1f}"


def _svg(h, body, label):
    return (f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{escape(label)}" '
            f'xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def _t(x, y, s, cls="lbl", anchor="start"):
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{escape(str(s))}</text>'


def calendar(spec, label):
    vals = spec["values"]
    start = date.fromisoformat(spec["start"])
    weeks = (len(vals) + 6) // 7
    cell = min(13, (W - 40) / weeks - 2)
    vmax = max(vals) or 1
    out = []
    for i, v in enumerate(vals):
        x = 30 + (i // 7) * (cell + 2)
        y = 22 + (i % 7) * (cell + 2)
        lvl = 0 if v <= 0 else min(4, 1 + int(3.999 * v / vmax))
        d = start + timedelta(days=i)
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2" class="h{lvl}">'
                   f'<title>{d.isoformat()}: {v:.0f} min</title></rect>')
        if d.day == 1:
            out.append(_t(x, 14, d.strftime("%m/%y"), "tick"))
    return _svg(22 + 7 * (cell + 2) + 8, "".join(out), label)


def bars(spec, label):
    vals, labels = spec["values"], spec["labels"]
    n = len(vals)
    h, top, bottom, left = 260, 20, 40, 44
    vmin = 0 if spec.get("fmt") != "pace" else min(vals) * 0.95
    vmax = max(vals) * 1.05 or 1
    bw = (W - left - 10) / n
    sy = lambda v: top + (h - top - bottom) * (1 - (v - vmin) / (vmax - vmin))
    out = []
    for i, v in enumerate(vals):
        cls = "bar"
        if spec.get("flags") and spec["flags"][i]:
            cls = "bar hot"
        if spec.get("split") is not None and i >= spec["split"]:
            cls = "bar acc"
        if spec.get("best") == i:
            cls = "bar good"
        if spec.get("worst") == i:
            cls = "bar hot"
        x = left + i * bw
        y = sy(v)
        out.append(f'<rect x="{x + bw * .12:.1f}" y="{y:.1f}" width="{bw * .76:.1f}" height="{h - bottom - y:.1f}" '
                   f'rx="2" class="{cls}"><title>{escape(labels[i])}: {_num(v, spec.get("unit", ""))}</title></rect>')
    step = max(1, -(-n // 9))
    for i in range(0, n, step):
        out.append(_t(left + i * bw + bw / 2, h - bottom + 16, labels[i], "tick", "middle"))
    if spec.get("means"):
        sp = spec["split"]
        for (a, b), m in zip(((0, sp), (sp, n)), spec["means"]):
            y = sy(m)
            out.append(f'<line x1="{left + a * bw:.1f}" x2="{left + b * bw:.1f}" y1="{y:.1f}" y2="{y:.1f}" class="mean"/>')
            out.append(_t(left + b * bw - 4, y - 6, f"{m:.1f}", "tick strong", "end"))
    for v in (vmin, (vmin + vmax) / 2, vmax):
        out.append(_t(left - 6, sy(v) + 4, _num(v, spec.get("unit", "")), "tick", "end"))
    out.append(f'<line x1="{left}" x2="{W - 10}" y1="{h - bottom}" y2="{h - bottom}" class="axis"/>')
    return _svg(h, "".join(out), label)


def hbars(spec, label):
    vals, labels = spec["values"], spec["labels"]
    row, left = 44, 130
    h = row * len(vals) + 10
    lo = min(vals) * 0.9 if spec.get("fmt") == "pace" else 0
    hi = max(vals)
    out = []
    for i, (v, lab) in enumerate(zip(vals, labels)):
        y = 6 + i * row
        wbar = 40 + (W - left - 120) * (v - lo) / ((hi - lo) or 1)
        cls = "bar good" if i == spec.get("best") else "bar"
        out.append(_t(left - 12, y + 24, lab, "lbl", "end"))
        out.append(f'<rect x="{left}" y="{y + 6}" width="{wbar:.1f}" height="{row - 16}" rx="4" class="{cls}"/>')
        out.append(_t(left + wbar + 10, y + 25, _num(v, spec.get("unit", "")) + (" /km" if spec.get("fmt") == "pace" else ""),
                      "lbl strong"))
    return _svg(h, "".join(out), label)


def lines(spec, label):
    labels = spec["labels"]
    n = len(labels)
    h, top, bottom, left = 270, 24, 40, 56
    allv = [v for _, vs, _ in spec["series"] for v in vs]
    vmin, vmax = min(allv), max(allv)
    pad = (vmax - vmin) * 0.15 or 1
    vmin, vmax = vmin - pad, vmax + pad
    inv = spec.get("invert")  # lower is better: draw better values higher
    sx = lambda i: left + (W - left - 44) * (i / max(n - 1, 1))
    sy = lambda v: top + (h - top - bottom) * ((v - vmin) / (vmax - vmin) if inv else 1 - (v - vmin) / (vmax - vmin))
    out = []
    for v in (vmin + pad, (vmin + vmax) / 2, vmax - pad):
        out.append(f'<line x1="{left}" x2="{W - 20}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" class="grid"/>')
        out.append(_t(left - 8, sy(v) + 4, _num(v, spec.get("unit", "")), "tick", "end"))
    for name, vs, tone in spec["series"]:
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vs))
        out.append(f'<polyline points="{pts}" class="line {tone}"/>')
        for i, v in enumerate(vs):
            out.append(f'<circle cx="{sx(i):.1f}" cy="{sy(v):.1f}" r="3.5" class="dot {tone}">'
                       f'<title>{escape(labels[i])}: {_num(v, spec.get("unit", ""))}</title></circle>')
        out.append(_t(sx(n - 1) - 4, sy(vs[-1]) - 10, _num(vs[-1], spec.get("unit", "")), f"tick strong {tone}", "end"))
    step = max(1, n // 8)
    for i in range(0, n, step):
        out.append(_t(sx(i), h - bottom + 18, labels[i], "tick", "middle"))
    legend = "".join(f'<span class="key {tone}">{escape(name)}</span>' for name, _, tone in spec["series"])
    return f'<div class="legend">{legend}</div>' + _svg(h, "".join(out), label)


def matrix(spec, label):
    rows, cols, vals = spec["rows"], spec["cols"], spec["values"]
    left, top = 40, 22
    cw = (W - left - 10) / len(cols)
    ch = cw * 0.8
    vmax = max(max(r) for r in vals) or 1
    out = []
    for j, c in enumerate(cols):
        if j % 2 == 0:
            out.append(_t(left + j * cw + cw / 2, 14, c + "h", "tick", "middle"))
    for i, r in enumerate(rows):
        out.append(_t(left - 8, top + i * ch + ch / 2 + 4, r, "tick", "end"))
    for i in range(len(rows)):
        for j in range(len(cols)):
            v = vals[i][j]
            lvl = 0 if v == 0 else min(4, 1 + int(3.999 * v / vmax))
            best = spec.get("best") == [i, j]
            out.append(f'<rect x="{left + j * cw + 1:.1f}" y="{top + i * ch + 1:.1f}" width="{cw - 2:.1f}" '
                       f'height="{ch - 2:.1f}" rx="3" class="h{lvl}{" ring" if best else ""}">'
                       f'<title>{rows[i]} {cols[j]}h: {v}</title></rect>')
    return _svg(top + len(rows) * ch + 6, "".join(out), label)


def stack(spec, label):
    labels, series = spec["labels"], spec["series"]
    row, left = 34, 60
    h = row * len(labels) + 10
    out = []
    for i, lab in enumerate(labels):
        y = 6 + i * row
        x = left
        out.append(_t(left - 10, y + 20, lab, "lbl", "end"))
        for k, (name, vs) in enumerate(series):
            w = (W - left - 20) * vs[i]
            cls = f"seg s{k}" + (" focus" if k == spec.get("highlight") else "")
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{max(w, 0):.1f}" height="{row - 8}" class="{cls}">'
                       f'<title>{escape(name)} {lab}: {vs[i] * 100:.0f}%</title></rect>')
            if w > 44:
                out.append(_t(x + w / 2, y + 18, f"{vs[i] * 100:.0f}%", "inbar", "middle"))
            x += w
    legend = "".join(f'<span class="key s{k}{" focus" if k == spec.get("highlight") else ""}">{escape(n)}</span>'
                     for k, (n, _) in enumerate(series))
    return f'<div class="legend">{legend}</div>' + _svg(h, "".join(out), label)


RENDER = dict(calendar=calendar, bars=bars, hbars=hbars, lines=lines, matrix=matrix, stack=stack)


def render(spec, label):
    if not spec:
        return ""
    return RENDER[spec["type"]](spec, label)
