#!/usr/bin/env python3
"""Activity report: Strava / Garmin / GPX / TCX / FIT / any CSV -> one self-contained HTML report.

Usage:
  python report.py <file-or-folder> [--tz 7] [--lang vi|en] [--out report.html] [--limit 12]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charts  # noqa: E402
import insights  # noqa: E402
import load  # noqa: E402

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--ink:#16181d;--mute:#6b7080;--line:#e4e2dc;--acc:#e07a4f;--acc2:#2bb5a5;
--hot:#e5484d;--good:#2bb5a5;--h0:#ecebe6;--h1:#f6d3c2;--h2:#eea98a;--h3:#e07a4f;--h4:#b4532c}
@media (prefers-color-scheme:dark){:root{--bg:#0b0d12;--card:#141821;--ink:#f2f4f8;--mute:#8a93a6;--line:#232937;
--h0:#1b202b;--h1:#4a2c22;--h2:#7a412b;--h3:#b85a36;--h4:#f08a5d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 "Be Vietnam Pro",system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:820px;margin:0 auto;padding:32px 16px 64px}
header .kicker{color:var(--acc);font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:13px}
h1{font-size:34px;line-height:1.15;margin:8px 0 6px}header p{color:var(--mute);margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 22px 18px;margin-top:18px}
.card .n{color:var(--acc);font-weight:700;font-size:13px;letter-spacing:.08em;text-transform:uppercase}
.card h2{font-size:23px;line-height:1.25;margin:6px 0 6px}.card p{color:var(--mute);margin:0 0 12px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:8px 0 14px}
.kpi{border:1px solid var(--line);border-radius:12px;padding:10px 12px}.kpi b{display:block;font-size:24px}
.kpi span{color:var(--mute);font-size:13px}
svg{width:100%;height:auto;display:block}
.lbl{fill:var(--ink);font-size:14px}.tick{fill:var(--mute);font-size:11.5px}.strong{font-weight:700;fill:var(--ink)}
.inbar{fill:#fff;font-size:12px;font-weight:600}
.bar{fill:var(--h2)}.bar.acc{fill:var(--acc)}.bar.hot{fill:var(--hot)}.bar.good{fill:var(--good)}
.axis,.grid{stroke:var(--line)}.mean{stroke:var(--ink);stroke-dasharray:5 4;stroke-width:1.5}
.line{fill:none;stroke-width:3}.line.accent{stroke:var(--acc)}.line.muted{stroke:var(--mute);stroke-dasharray:6 5}
.dot.accent{fill:var(--acc)}.dot.muted{fill:var(--mute)}.tick.accent{fill:var(--acc)}
.h0{fill:var(--h0)}.h1{fill:var(--h1)}.h2{fill:var(--h2)}.h3{fill:var(--h3)}.h4{fill:var(--h4)}
.ring{stroke:var(--ink);stroke-width:2.5}
.seg{fill:var(--h0)}.s0{fill:#c9c5bb}.s1{fill:#a9b4c2}.s2{fill:#d7c08a}.s3{fill:#9fc7b8}.s4{fill:#c6a9c9}.seg.focus{fill:var(--acc)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 8px;font-size:13px;color:var(--mute)}
.key:before{content:"";display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;background:var(--mute)}
.key.accent:before,.key.focus:before{background:var(--acc)}.key.s0:before{background:#c9c5bb}.key.s1:before{background:#a9b4c2}
.key.s2:before{background:#d7c08a}.key.s3:before{background:#9fc7b8}.key.s4:before{background:#c6a9c9}
footer{color:var(--mute);font-size:13px;margin-top:28px;text-align:center}
"""


def build_html(df, items, lang, title=None):
    f = insights.Fmt(lang)
    span = f"{df.start.min():%m/%Y} – {df.start.max():%m/%Y}"
    title = title or f.t("Báo cáo vận động của bạn", "Your activity report")
    cards = []
    for i, it in enumerate(items):
        kpis = "".join(f'<div class="kpi"><b>{escape(v)}</b><span>{escape(k)}</span></div>' for v, k in it.get("kpis", []))
        cards.append(
            f'<section class="card" id="{it["id"]}"><div class="n">{i:02d} · {escape(it["title"])}</div>'
            f'<h2>{escape(it["headline"])}</h2><p>{escape(it["detail"])}</p>'
            f'{f"<div class=kpis>{kpis}</div>" if kpis else ""}{charts.render(it.get("chart"), it["headline"])}</section>')
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><main>
<header><div class="kicker">Activity Report</div><h1>{escape(title)}</h1>
<p>{escape(span)} · {f.n(len(df))} {f.t("hoạt động", "activities")} · {f.t("tạo lúc", "made")} {datetime.now():%d/%m/%Y}</p></header>
{''.join(cards)}
<footer>{f.t("Tạo bằng skill activity-report, miễn phí và mã nguồn mở", "Made with the free, open-source activity-report skill")}</footer></main></body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="activities.csv, an export folder, or GPX/TCX/FIT files")
    ap.add_argument("--tz", type=float, default=0, help="hours to add to UTC timestamps (Vietnam: 7)")
    ap.add_argument("--lang", default="en", choices=["vi", "en"])
    ap.add_argument("--out", default="activity-report.html")
    ap.add_argument("--limit", type=int, default=12, help="max insights in the report")
    ap.add_argument("--title")
    a = ap.parse_args(argv)

    df = load.load(a.path, a.tz)
    items = insights.find_all(df, a.lang, a.limit)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(build_html(df, items, a.lang, a.title))
    with open(os.path.splitext(a.out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1, default=str)

    print(f"# {len(df)} activities, {df.start.min():%Y-%m-%d} to {df.start.max():%Y-%m-%d}")
    print("sports: " + ", ".join(f"{k} {v}" for k, v in df.sport.value_counts().items()))
    for it in items:
        print(f"- [{it['id']}] {it['headline']}")
    print(f"report: {os.path.abspath(a.out)}")


if __name__ == "__main__":
    main()
