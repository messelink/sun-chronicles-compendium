#!/usr/bin/env python3
"""Generate shareable PNGs from the live star-map.svg into compendium-public/docs/img/.

Produces three chrome-free assets (for Reddit / social, etc.):
  hero-graph.png  — the graph at native ~square aspect (no UI chrome)
  hero-16x9.png   — the graph fitted into a 16:9 frame (feed-thumbnail friendly)
  poster.png      — title + graph + legend composed from vector parts

Needs rsvg-convert. Run after build-web-map.py; legend colours come from topology.json
so they always match the map. publish.py calls this automatically (when rsvg-convert is
present) so docs/img/ never goes stale; you can also run it standalone. The output dir
is not wiped by publish.py.

Usage: scripts/make-images.py
"""
import json
import re
import subprocess
from pathlib import Path

PRIV = Path(__file__).resolve().parent.parent
OUT = PRIV.parent / "compendium-public" / "docs" / "img"
BG = "#07091d"

svg = (PRIV / "data/star-map.svg").read_text()
inner = svg[svg.index(">") + 1: svg.rindex("</svg>")]            # strip outer <svg> wrapper
pc = {p["id"]: p["color"] for p in json.loads((PRIV / "data/topology.json").read_text())["polities"]}
OUT.mkdir(parents=True, exist_ok=True)


def render(svg_path, png_path, zoom=2):
    subprocess.run(["rsvg-convert", "-z", str(zoom), "-b", BG, str(svg_path), "-o", str(png_path)],
                   check=True)


# ── 1. hero-graph (native) ────────────────────────────────────────────────────
render(PRIV / "data/star-map.svg", OUT / "hero-graph.png")

# ── 2. hero-16x9 (fit graph into a 16:9 frame; never crops a node) ─────────────
xs, ys = [], []
for m in re.finditer(r'class="node"[^>]*transform="translate\(([-\d.]+),([-\d.]+)\)"', svg):
    xs.append(float(m.group(1))); ys.append(float(m.group(2)))
x0, x1, y0, y1 = min(xs) - 120, max(xs) + 120, min(ys) - 70, max(ys) + 55
cw, ch = x1 - x0, y1 - y0
ar = 16 / 9
bw = max(cw, ch * ar); bh = bw / ar
bx, by = x0 - (bw - cw) / 2, y0 - (bh - ch) / 2
crop = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw:.0f}" height="{bh:.0f}" '
        f'viewBox="{bx:.0f} {by:.0f} {bw:.0f} {bh:.0f}"><rect x="{bx:.0f}" y="{by:.0f}" '
        f'width="{bw:.0f}" height="{bh:.0f}" fill="{BG}"/>{inner}</svg>')
(OUT / "_hero-16x9.svg").write_text(crop)
render(OUT / "_hero-16x9.svg", OUT / "hero-16x9.png")
(OUT / "_hero-16x9.svg").unlink()

# ── 3. poster (title + graph + legend) ─────────────────────────────────────────
INK, MUT, FAINT = "#e8e5d6", "#b9b6a6", "#6f7494"
GW, GH = 1778, 1640
MX, TITLE_H = 70, 210
W = GW + 2 * MX
GY = TITLE_H
LEG_Y = GY + GH + 46
H = LEG_Y + 360
S = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     f'font-family="EB Garamond, Georgia, serif"><rect width="{W}" height="{H}" fill="{BG}"/>']
S.append(f'<text x="{MX}" y="64" fill="{MUT}" font-size="17" letter-spacing="3" '
         f'font-family="IBM Plex Mono, monospace">FIELD REFERENCE CHART · SUN CHRONICLES · '
         f'K. ELLIOTT · VERIFIED COMPENDIUM</text>')
S.append(f'<text x="{MX}" y="132" fill="{INK}" font-size="58" letter-spacing="6" '
         f'font-family="Cinzel, Georgia, serif">THE LOCAL BELT '
         f'<tspan fill="{pc["yele_league"]}" font-style="italic" font-size="40">of</tspan> STARS</text>')
S.append(f'<text x="{MX}" y="172" fill="{MUT}" font-size="20">A topological survey of the '
         f'post-collapse beacon network, knnu corridors, and political regions in '
         f'Unconquerable Sun &amp; Furious Heaven.</text>')
S.append(f'<text x="{MX}" y="200" fill="{FAINT}" font-size="16">Positions are force-laid, not '
         f'physical — the novels give no coordinates, only the relational topology. Lines are '
         f'paired connections, not distances.</text>')
S.append(f'<svg x="{MX}" y="{GY}" width="{GW}" height="{GH}" viewBox="316 -60 1778 1640">{inner}</svg>')

cols = [MX, MX + 452, MX + 904, MX + 1356]
ROW = 38


def heading(x, y, txt):
    return (f'<text x="{x}" y="{y}" fill="{INK}" font-size="18" letter-spacing="3" '
            f'font-family="Cinzel, Georgia, serif">{txt}</text>'
            f'<line x1="{x}" y1="{y+10}" x2="{x+400}" y2="{y+10}" stroke="#1a1f3a"/>')


def label(x, y, txt, note=""):
    t = f'<text x="{x+58}" y="{y+5}" fill="{MUT}" font-size="18">{txt}'
    if note:
        t += f' <tspan fill="{FAINT}" font-size="14">{note}</tspan>'
    return t + "</text>"


def line_sample(x, y, color, dash=None, w=2):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x}" y1="{y}" x2="{x+40}" y2="{y}" stroke="{color}" stroke-width="{w}"{d}/>'


x, y = cols[0], LEG_Y
S.append(heading(x, y, "CONNECTIONS")); y += 34
_legend_edges = [
    ("#cfd6ea", None, 2, "Confirmed beacon", ""), ("#6f7494", "3 5", 1.5, "Inferred beacon", ""),
    ("#d6a85a", "6 5", 1.8, "Knnu (non-beacon link)", ""), (None, None, 0, "Multi-hop route", "○ = unnamed hop"),
    ("#cfd6ea", "14 6", 1.7, "Route, length unknown / inferred", "")]
if any(e.get("status") == "severed" for e in json.loads((PRIV / "data/topology.json").read_text())["edges"]):
    _legend_edges.append(("#b06a6a", "6 5", 1.6, "Severed (cut) link", ""))   # only if one exists
for color, dash, w, txt, note in _legend_edges:
    if color is None:
        S.append(f'<line x1="{x}" y1="{y}" x2="{x+15}" y2="{y}" stroke="#8d96b8" stroke-width="1.5"/>'
                 f'<circle cx="{x+20}" cy="{y}" r="3.5" fill="{BG}" stroke="#6b7088"/>'
                 f'<line x1="{x+25}" y1="{y}" x2="{x+40}" y2="{y}" stroke="#8d96b8" stroke-width="1.5"/>')
    else:
        S.append(line_sample(x, y, color, dash, w))
    S.append(label(x, y, txt, note)); y += ROW

x, y = cols[1], LEG_Y
S.append(heading(x, y, "SYSTEMS")); y += 34
S.append(f'<circle cx="{x+20}" cy="{y}" r="11" fill="none" stroke="#cfd6ea" stroke-width="1.2" '
         f'stroke-dasharray="3 3" opacity="0.8"/><circle cx="{x+20}" cy="{y}" r="5.5" fill="#cfd6ea"/>'
         f'<text x="{x+34}" y="{y-7}" fill="#cfd6ea" font-size="13">★</text>')
S.append(label(x, y, "Major hub / capital", "colour = polity")); y += ROW
S.append(f'<circle cx="{x+20}" cy="{y}" r="6" fill="#cfd6ea"/>')
S.append(label(x, y, "Standard system", "colour = polity")); y += ROW
S.append(f'<circle cx="{x+20}" cy="{y}" r="7" fill="none" stroke="{pc["mishirru"]}" '
         f'stroke-width="1.4" stroke-dasharray="3 3"/>')
S.append(label(x, y, "Off-grid (the Gyre)", "")); y += ROW
S.append(f'<circle cx="{x+20}" cy="{y}" r="4.5" fill="#6dd6c1"/>')
S.append(label(x, y, "Brown-dwarf knnu waypoint", "")); y += ROW

x, y = cols[2], LEG_Y
S.append(heading(x, y, "POLITICAL REGIONS")); y += 34
for pid, name in [("chaonia", "Chaonian Republic"), ("phene", "Phene Empire"),
                  ("yele_league", "Yele League"), ("mishirru", "Mishirru Province"),
                  ("trinity", "Trinity Coalition"), ("contested", "Contested / frontier")]:
    S.append(f'<circle cx="{x+20}" cy="{y}" r="8" fill="{pc[pid]}"/>')
    S.append(label(x, y, name)); y += ROW

x, y = cols[3], LEG_Y
S.append(heading(x, y, "READING THE CHART")); y += 36
for strong, rest in [("Topology, not geography.", "Position implies relational role,"),
                     ("", "hub / periphery / frontier — not distance."), ("TEC", "— a rare three-way mutual beacon"),
                     ("", "link (Chaonian core; Trinity)."), ("Karnos", "— the load-bearing junction wiring"),
                     ("", "the regions together.")]:
    if strong:
        S.append(f'<text x="{x}" y="{y}" font-size="16"><tspan fill="{INK}">{strong}</tspan> '
                 f'<tspan fill="{MUT}">{rest}</tspan></text>')
    else:
        S.append(f'<text x="{x}" y="{y}" fill="{MUT}" font-size="16">{rest}</text>')
    y += 26

S.append(f'<text x="{MX}" y="{H-22}" fill="{FAINT}" font-size="14">Unofficial fan project · not '
         f'approved by or affiliated with Kate Elliott or her publishers · facts cited to the '
         f'novels, no substantial text reproduced · sourced from Unconquerable Sun (2020) &amp; '
         f'Furious Heaven (2023).</text>')
S.append("</svg>")
(OUT / "_poster.svg").write_text("".join(S))
render(OUT / "_poster.svg", OUT / "poster.png", zoom=1.6)
(OUT / "_poster.svg").unlink()

for f in ("hero-graph.png", "hero-16x9.png", "poster.png"):
    print(f"  wrote {(OUT / f).relative_to(PRIV.parent)}")
