#!/usr/bin/env python3
"""Render data/topology.json as a styled, force-laid star chart.

Aesthetic ported from the Claude Design handoff ("THE LOCAL BELT of STARS");
node POSITIONS are computed by a seeded force-directed layout (Fruchterman-Reingold
+ per-polity clustering) so the map regenerates as the compendium grows — no hand
coordinates. Connectivity only; positions are NOT physical geography.

Outputs:  data/star-map.svg   (static, styled)
          data/star-map.html  (interactive: pan / zoom / drag / hover)
Run:      scripts/build-web-map.py
"""
import json, math, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
topo = json.loads((DATA / "topology.json").read_text())
random.seed(7)

W, H = 2200, 1500
pcolor = {p["id"]: p["color"] for p in topo["polities"]}
pname  = {p["id"]: p["name"]  for p in topo["polities"]}
systems = list(topo["systems"])
sid = {s["id"]: s for s in systems}
_edges = [e for e in topo["edges"] if e["from"] in sid and e["to"] in sid]
# Expand multi-hop ROUTE edges (hops>=2, unnamed intermediates) into chains of unnamed
# PLACEHOLDER systems — render-only. topology.json keeps the canonical {route, hops}; the
# placeholders are presentation ghosts (no names, never written back to the compendium).
edges = []
for e in _edges:
    h = e.get("hops"); pad = e.get("render_pad")
    known_hops = isinstance(h, int) and h >= 2          # canon hop count (names unknown)
    ghosts = (h - 1) if known_hops else (pad if isinstance(pad, int) and pad >= 1 else 0)
    inferred = bool(ghosts) and not known_hops          # padded: even the length is a guess
    if e.get("type") == "route" and ghosts:
        pa, pb = sid[e["from"]].get("polity"), sid[e["to"]].get("polity")
        rpol = pa if pa == pb else "unknown"   # same-region route → ghosts inherit the region
        chain = [e["from"]]
        for j in range(1, ghosts + 1):
            pid = f"_ph_{e['from']}_{e['to']}_{j}"
            systems.append({"id": pid, "name": "", "class": "placeholder",
                            "polity": rpol, "route": e.get("route", ""), "inferred": inferred})
            chain.append(pid)
        chain.append(e["to"])
        segs = list(zip(chain, chain[1:]))
        # parent-route id = the original endpoint pair; lets _counts_x penalise crossings
        # between segments of DIFFERENT parent routes (e.g. Yele→Nalanda chain shouldn't
        # weave through the Yele→Sankore chain even though both are same-region soft).
        rid = f"{e['from']}→{e['to']}"
        for k, (a, b) in enumerate(segs):
            seg = {"from": a, "to": b, "type": "route_seg", "region": rpol,
                   "inferred": inferred, "route_id": rid}
            if inferred and k == len(segs) // 2:   # one "route" label per inferred chain, like a stub
                seg["route_label"] = True
            edges.append(seg)
    else:
        edges.append(e)
# stubs: a known-but-unnamed-endpoint connection → a short dashed route to an unnamed,
# region-tinted placeholder. It's a leaf, so it shows the link exists without springing
# the source toward a named distant hub it may not actually reach.
for s in list(systems):
    for i, st in enumerate(s.get("stubs") or []):
        pid = f"_stub_{s['id']}_{i}"
        systems.append({"id": pid, "name": "", "class": "placeholder",
                        "polity": st.get("region", "unknown"), "route": "stub", "inferred": True})
        edges.append({"from": s["id"], "to": pid, "type": "route"})
sid = {s["id"]: s for s in systems}
# layout hints (presentation only, not topology): {id: [target ids to pull toward]}
HINT = {s["id"]: [t for t in s["layout_near"] if t in sid]
        for s in systems if s.get("layout_near")}

def x(s):  # XML-escape dynamic text/attribute content
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

# ── force-directed layout (multi-start; keep the lowest-crossing result) ──────
ANCHOR = {  # Karnos (contested hub) at centre; others loosely around it
    "contested": (1100, 750), "chaonia": (640, 640), "phene": (1560, 640),
    "hatti": (920, 560),   # conquered frontier between the Chaonian core and Karnos
    "yele_league": (660, 1050), "trinity": (950, 1080), "mishirru": (1480, 1000),
    "unknown": (1100, 750),
}
# Explicit region-label anchor: pin the polity label above this system. Checked first,
# then the capital-note heuristic, then the component centroid. Use for regions whose
# label belongs at a named eponym/seat that isn't a polity *capital* (e.g. the Hatti
# region's eponym is a frontier system, not Chaonia's capital).
REGION_LABEL_ANCHOR = {
    "hatti": "hatti",
}
# "contested" and "unknown" are per-system STATUSES, not regions — their systems are
# scattered across the map (e.g. Eel Gulf sits by its only neighbour, Yele). These
# polity values do NOT count as a shared region: they're excluded from region-hull
# shading AND from the `_counts_x` shared-polity exemption (so a hard link crossing
# a soft edge isn't given a free pass just because both touch a `contested` node).
NON_REGION = {"contested", "unknown"}
ids = [s["id"] for s in systems]
EDGES = [(e["from"], e["to"]) for e in edges]
# HARD links (confirmed beacon/knnu) must stay crossing-free; SOFT links (inferred, or any
# route/route_seg — all tentative) may be crossed freely, so the layout doesn't distort to
# route around a guess. Only hard×hard crossings (and hard edges for node clearance) count.
def _is_soft(e):
    return (e.get("status") == "inferred" or bool(e.get("inferred"))
            or e.get("type") in ("route", "route_seg"))
HARD_PAIRS = {frozenset((e["from"], e["to"])) for e in edges if not _is_soft(e)}
def _hard(a, b):
    return frozenset((a, b)) in HARD_PAIRS
ADJ = {}                                   # adjacency, for sibling/spoke spreading
for (_a, _b) in EDGES:
    ADJ.setdefault(_a, set()).add(_b); ADJ.setdefault(_b, set()).add(_a)
# spokes of a common hub should splay apart instead of stacking — collect sibling pairs
SIBS = set()
for _nb in ADJ.values():
    _nl = sorted(_nb)
    for _i in range(len(_nl)):
        for _j in range(_i + 1, len(_nl)):
            SIBS.add((_nl[_i], _nl[_j]))
SIBS = sorted(SIBS)   # sorted (not list(set)) so layout is deterministic across runs
k = math.sqrt(W * H / len(ids)) * 0.40    # smaller k = weaker repulsion + tighter edges
ITERS = 850
pos = {}                                   # global; set to the chosen layout below

def force_layout(seed):
    random.seed(seed)
    p = {}
    for s in systems:
        ax, ay = ANCHOR.get(s.get("polity"), (W / 2, H / 2))
        p[s["id"]] = [ax + random.uniform(-110, 110), ay + random.uniform(-110, 110)]
    for it in range(ITERS):
        temp = max(2.0, 55 * (1 - it / ITERS))
        disp = {i: [0.0, 0.0] for i in ids}
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                ia, ib = ids[a], ids[b]
                dx, dy = p[ia][0] - p[ib][0], p[ia][1] - p[ib][1]
                d = math.hypot(dx, dy) or 0.01
                if d > 340:               # cutoff: only nearby nodes repel → compact
                    continue
                f = k * k / d; ux, uy = dx / d, dy / d
                disp[ia][0] += ux * f; disp[ia][1] += uy * f
                disp[ib][0] -= ux * f; disp[ib][1] -= uy * f
        for e in edges:
            fr, to = e["from"], e["to"]
            dx, dy = p[fr][0] - p[to][0], p[fr][1] - p[to][1]
            d = math.hypot(dx, dy) or 0.01
            # spring by type: knnu shortest (close neighbours), route longest, beacon mid.
            # knnu = physical short-haul gaps (50–70 days, ≤ a few light-years), so they
            # should render visibly tighter than beacon edges (instantaneous wormholes).
            w = {"knnu": 9.0, "beacon": 1.0, "route": 1.0}.get(e.get("type"), 1.0)   # knnu = short hops
            f = d * d / k * w * 1.5; ux, uy = dx / d, dy / d
            disp[fr][0] -= ux * f; disp[fr][1] -= uy * f
            disp[to][0] += ux * f; disp[to][1] += uy * f
        for ia, ib in SIBS:               # extra repulsion between spokes of a shared hub
            dx, dy = p[ia][0] - p[ib][0], p[ia][1] - p[ib][1]
            d = math.hypot(dx, dy) or 0.01
            if d > 400:
                continue
            f = 1.8 * k * k / d; ux, uy = dx / d, dy / d
            disp[ia][0] += ux * f; disp[ia][1] += uy * f
            disp[ib][0] -= ux * f; disp[ib][1] -= uy * f
        for s in systems:                 # gentle polity gravity + centring
            i = s["id"]; ax, ay = ANCHOR.get(s.get("polity"), (W / 2, H / 2))
            disp[i][0] += (ax - p[i][0]) * 0.010 + (W / 2 - p[i][0]) * 0.006
            disp[i][1] += (ay - p[i][1]) * 0.010 + (H / 2 - p[i][1]) * 0.006
        for i in ids:
            dx, dy = disp[i]; d = math.hypot(dx, dy) or 0.01
            p[i][0] += dx / d * min(d, temp); p[i][1] += dy / d * min(d, temp)
            p[i][0] = min(max(p[i][0], 60), W - 60); p[i][1] = min(max(p[i][1], 90), H - 70)
        for i, targets in HINT.items():   # hard layout pin: hold near the target centroid
            tx = sum(p[t][0] for t in targets) / len(targets)
            ty = sum(p[t][1] for t in targets) / len(targets)
            p[i][0] = min(max(tx, 60), W - 60); p[i][1] = min(max(ty - 90, 90), H - 70)
    # place degree-1 leaves just outside their single neighbour, pointing away from the
    # graph centroid — so they dangle outward instead of landing on top of other edges.
    cxg = sum(p[i][0] for i in ids) / len(ids)
    cyg = sum(p[i][1] for i in ids) / len(ids)
    nbrs = {}
    for (a, b) in EDGES:
        nbrs.setdefault(a, []).append(b); nbrs.setdefault(b, []).append(a)
    # FAN OUT leaves that share a neighbour (e.g. Auger & Axiom off Anchor) so they splay
    # apart instead of stacking on the same outward ray.
    leaves_of = {}
    for i in ids:
        if len(nbrs.get(i, [])) == 1 and i not in HINT:   # hinted nodes keep their pull
            leaves_of.setdefault(nbrs[i][0], []).append(i)
    for nb, leaves in leaves_of.items():
        nx, ny = p[nb]
        others = [o for o in nbrs.get(nb, []) if o not in leaves]   # the hub's other spokes
        if others:                                        # aim leaves into the widest gap
            angs = sorted(math.atan2(p[o][1] - ny, p[o][0] - nx) for o in others)
            gaps = []
            for idx in range(len(angs)):
                a1 = angs[idx]
                a2 = angs[(idx + 1) % len(angs)] + (2 * math.pi if idx + 1 == len(angs) else 0)
                gaps.append((a2 - a1, (a1 + a2) / 2))
            base = max(gaps)[1]
        else:
            base = math.atan2(ny - cyg, nx - cxg)         # lone node: outward from the centroid
        nleaves = len(leaves); spread = math.radians(42)
        for j, i in enumerate(sorted(leaves)):
            ang = base + spread * (j - (nleaves - 1) / 2.0)
            p[i] = [min(max(nx + math.cos(ang) * 135, 60), W - 60),
                    min(max(ny + math.sin(ang) * 135, 90), H - 70)]
    return p

def _orient(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

def _cross(a, b, c, d):                    # proper segment intersection (no endpoint touch)
    A, B, C, D = pos[a], pos[b], pos[c], pos[d]
    d1, d2 = _orient(C, D, A), _orient(C, D, B)
    d3, d4 = _orient(A, B, C), _orient(A, B, D)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)

def _epol(a, b):                           # the polities an edge touches (raw)
    return {sid[a].get("polity"), sid[b].get("polity")}

def _eregion(a, b):                        # only REAL regions (statuses like 'contested' dropped)
    return _epol(a, b) - NON_REGION

def _has_ghost(a, b):                      # does this link run through an unnamed placeholder?
    return sid[a].get("class") == "placeholder" or sid[b].get("class") == "placeholder"

# Parent-route lookup for route-segments. Two segments of DIFFERENT routes shouldn't
# cross even within the same region — prevents the "arms crossing" pathology when two
# chains fan out from a shared hub (e.g. Yele→Nalanda and Yele→Sankore weaving).
ROUTE_OF = {frozenset((e["from"], e["to"])): e["route_id"]
            for e in edges if e.get("type") == "route_seg" and e.get("route_id")}

def _counts_x(a, b, c, d):
    # A crossing is penalised if:
    #  • both links are confirmed (hard×hard) — always avoid; or
    #  • it bridges DIFFERENT regions — a soft link may be crossed only within its own
    #    region, else the two regions' hulls overlap (e.g. a Phene beacon over a Mishirru
    #    route); or
    #  • a CONFIRMED named-system link is crossed by a GHOST route (one through unnamed
    #    intermediates) — a real beacon like Scepter↔Alabaster shouldn't be cut by a
    #    fuzzy Destiny→(unknown) segment. (A confirmed link MAY still cross an inferred
    #    route between NAMED systems, e.g. Karnos→Hellion over Hatti↔Na Iri.)
    if _hard(a, b) and _hard(c, d):
        return True
    if _eregion(a, b).isdisjoint(_eregion(c, d)):   # statuses ('contested'/'unknown') don't count as shared
        return True
    # Route-segments of DIFFERENT parent routes shouldn't cross even within the same region.
    ra = ROUTE_OF.get(frozenset((a, b))); rc = ROUTE_OF.get(frozenset((c, d)))
    if ra and rc and ra != rc:
        return True
    if (_hard(a, b) and _has_ghost(c, d)) or (_hard(c, d) and _has_ghost(a, b)):
        return True
    return False

def local_crossings(nid):
    inc = [(a, b) for (a, b) in EDGES if nid in (a, b)]
    n = 0
    for (a, b) in inc:
        for (c, d) in EDGES:
            if a in (c, d) or b in (c, d):
                continue
            if _counts_x(a, b, c, d) and _cross(a, b, c, d):
                n += 1
    return n

def total_crossings():
    n = 0
    for i in range(len(EDGES)):
        a, b = EDGES[i]
        for j in range(i + 1, len(EDGES)):
            c, d = EDGES[j]
            if len({a, b, c, d}) == 4 and _counts_x(a, b, c, d) and _cross(a, b, c, d):
                n += 1
    return n

CLEAR = 24   # min distance a node should keep from a non-incident edge

def _pt_seg(px, py, ax, ay, bx, by):       # distance from point to segment
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

def node_on_edges(nid):                    # # of non-incident edges this node sits too close to
    px, py = pos[nid]; n = 0
    npol = sid[nid].get("polity")
    for (a, b) in EDGES:
        if nid == a or nid == b:
            continue
        # clear HARD links always; clear SOFT (inferred/route) links only within the node's
        # own region — so Landfall doesn't sit on the Mishirru Destiny→Sena route, but a
        # node isn't shoved around by another region's soft links.
        if not _hard(a, b) and npol not in _epol(a, b):
            continue
        if _pt_seg(px, py, pos[a][0], pos[a][1], pos[b][0], pos[b][1]) < CLEAR:
            n += 1
    return n

def total_on_edge():
    return sum(node_on_edges(n) for n in ids)

def penalty(nid):                          # crossings dominate; node-on-edge is the tiebreak
    return local_crossings(nid) * 100 + node_on_edges(nid)

def _xnodes():
    s = set()
    for i in range(len(EDGES)):
        a, b = EDGES[i]
        for j in range(i + 1, len(EDGES)):
            c, d = EDGES[j]
            if len({a, b, c, d}) == 4 and _counts_x(a, b, c, d) and _cross(a, b, c, d):
                s.update((a, b, c, d))
    return s

def reduce_crossings():
    # greedy single-node relocation (smallest move on ties) …
    for _round in range(10):
        moved = 0
        for nid in ids:
            if nid in HINT:                 # pinned by a layout hint — don't relocate
                continue
            base = penalty(nid)
            if base == 0:
                continue
            cur = pos[nid][:]; best, bestc, bestd = cur, base, 0.0
            for ang in range(0, 360, 18):
                for rad in (45, 90, 150, 230, 330, 450):
                    cand = [min(max(cur[0] + rad * math.cos(math.radians(ang)), 60), W - 60),
                            min(max(cur[1] + rad * math.sin(math.radians(ang)), 90), H - 70)]
                    pos[nid] = cand; cc = penalty(nid)
                    disp = math.hypot(cand[0] - cur[0], cand[1] - cur[1])
                    if cc < bestc or (cc == bestc and disp < bestd):
                        best, bestc, bestd = cand[:], cc, disp
            pos[nid] = best
            if best != cur:
                moved += 1
        if moved == 0:
            break
    # … then swap positions of crossing-involved nodes (un-interleaves converging chains)
    for _ in range(5):
        xn = _xnodes()
        if not xn:
            break
        cand = set(xn)
        for (a, b) in EDGES:
            if a in xn: cand.add(b)
            if b in xn: cand.add(a)
        base, improved = total_crossings(), False
        for x in xn:
            if x in HINT:
                continue
            for y in cand:
                if x == y or y in HINT:
                    continue
                pos[x], pos[y] = pos[y][:], pos[x][:]
                if total_crossings() < base:
                    base, improved = total_crossings(), True
                else:
                    pos[x], pos[y] = pos[y][:], pos[x][:]
        if not improved:
            break

# multi-start: keep the layout with the fewest (crossings, then node-on-edge overlaps).
# (use `sc`, not `x` — `x` is the XML-escape function defined above.)
best_pos, best_score = None, (10 ** 9, 10 ** 9)
for seed in (7, 1, 2, 3, 5, 8, 13, 21, 4, 6, 9, 11, 17, 23, 42, 99):   # extra starts: the
    pos = force_layout(seed)                                          # Hatti corridor is fussy
    reduce_crossings()
    sc = (total_crossings(), total_on_edge())
    if sc < best_score:
        best_score, best_pos = sc, {i: v[:] for i, v in pos.items()}
    if sc[0] == 0 and sc[1] == 0:
        break
pos = best_pos
print(f"crossings / node-on-edge (best of seed search): {best_score}")

# fit the viewBox to the actual node bounding box (+pad for labels) so the
# composition fills the frame instead of sprawling to the rectangle edges.
xs = [p[0] for p in pos.values()]; ys = [p[1] for p in pos.values()]
PAD = 150
VBX, VBY = int(min(xs) - PAD), int(min(ys) - PAD)
VBW, VBH = int(max(xs) - min(xs) + 2 * PAD), int(max(ys) - min(ys) + 2 * PAD)


def hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def pad_hull(poly, cx, cy, pad=46):
    out = []
    for x, y in poly:
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy) or 1
        out.append((x + dx / d * pad, y + dy / d * pad))
    return out


# ── per-polity zone hulls + labels ───────────────────────────────────────
# NON_REGION (declared up top) is also the hull-exclusion set: contested/unknown
# systems are scattered, so a hull around them would invent a region that doesn't exist.
zones = []
# Within a component, members farther than HULL_OUTLIER_MULT × median distance from the
# centroid are dropped from the shaded hull (keeps one stray from ballooning it). High =
# include ~everything; lower it to trim far members. Tunable.
HULL_OUTLIER_MULT = 10.0

def _components(members):
    # connected components using ONLY same-polity-internal edges — so a region reachable
    # only THROUGH another power (e.g. the Tranquility exclave, linked to the Phene heartland
    # solely via the now-Chaonian Karnos caravan corridor) forms its OWN hull rather than a
    # misleading arm bridged across enemy space.
    mset = set(members); adj = {m: set() for m in members}
    for (a, b) in EDGES:
        if a in mset and b in mset:
            adj[a].add(b); adj[b].add(a)
    seen, comps = set(), []
    for m in members:
        if m in seen:
            continue
        stack, comp = [m], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x); stack.extend(adj[x] - seen)
        comps.append(comp)
    return comps

for pol in pname:
    if pol in NON_REGION:
        continue
    # same-region route ghosts are polity-tagged too, so they fall into the right component.
    members = [s["id"] for s in systems if s.get("polity") == pol]
    if not members:
        continue
    col = pcolor[pol]
    comps = _components(members)
    # Shade per connected component, BUT fold lone (disconnected) members into the region's
    # main cluster — a node with no known links (e.g. Maras Shantiya) belongs to its region's
    # hull, not its own. Genuine multi-node sub-clusters (the Tranquility exclave) stay separate.
    clusters = sorted((c for c in comps if len(c) >= 2), key=len, reverse=True)
    lone = [n for c in comps if len(c) == 1 for n in c]
    groups = ([clusters[0] + lone] + clusters[1:]) if clusters else ([lone] if lone else [])
    for comp in groups:
        pts = [tuple(pos[i]) for i in comp]
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        # within a component, still drop a far outlier so a spread cluster stays tight
        dists = sorted(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
        thr = max(dists[len(dists) // 2] * HULL_OUTLIER_MULT, 260) if dists else 260
        core = [p for p in pts if math.hypot(p[0] - cx, p[1] - cy) <= thr] or pts
        ccx = sum(p[0] for p in core) / len(core); ccy = sum(p[1] for p in core) / len(core)
        if len(core) >= 3:                         # only shade a real cluster (≥3 nodes)
            poly = pad_hull(hull(core), ccx, ccy)
            d = "M " + " L ".join(f"{x:.0f},{y:.0f}" for x, y in poly) + " Z"
            zones.append(f'<path d="{d}" fill="{col}" opacity="0.05"/>')
        # 1–2-node components (e.g. a lone frontier system reachable only via enemy space)
        # get no hull — just their coloured node(s)
    # one region label, anchored (in order): an explicit REGION_LABEL_ANCHOR pin →
    # a system whose note says "capital" → biggest-component centroid as a last resort.
    anchor_id = REGION_LABEL_ANCHOR.get(pol)
    caps = [i for i in members if "capital" in (sid[i].get("note") or "").lower()]
    if anchor_id and anchor_id in pos:
        lx, ly = pos[anchor_id][0], pos[anchor_id][1] - 52
    elif caps:
        lx, ly = pos[caps[0]][0], pos[caps[0]][1] - 52
    else:
        big = max(comps, key=len); bp = [pos[i] for i in big]
        lx = sum(p[0] for p in bp) / len(bp)
        ly = min(max(min(p[1] for p in bp) - 58, 46), H - 30)
    lbl = pname[pol].split(" (")[0].upper()       # drop parentheticals (e.g. "(Phene-administered)")
    lw = len(lbl) * 11.5 + 22                      # approx width incl. letter-spacing
    zones.append(f'<rect x="{lx-lw/2:.0f}" y="{ly-16:.0f}" width="{lw:.0f}" height="23" '
                 f'rx="4" fill="#07091d" opacity="0.66"/>')        # backing chip for legibility
    zones.append(f'<text x="{lx:.0f}" y="{ly:.0f}" text-anchor="middle" '
                 f'font-family="Cinzel, serif" letter-spacing="0.22em" font-size="15" '
                 f'fill="{col}" opacity="0.95">{lbl}</text>')

# ── edges ────────────────────────────────────────────────────────────────
def edge_style(e):
    t, st = e.get("type"), e.get("status", "working")
    if t == "beacon":
        if st == "inferred":
            return 'stroke:#6f7494;stroke-width:1.5;stroke-dasharray:3 5;opacity:0.8'
        return 'stroke:#cfd6ea;stroke-width:2;opacity:0.9'
    if t == "knnu":
        if st == "severed":   # PHYSICAL state: the link is cut/destroyed (not mere disuse)
            return 'stroke:#b06a6a;stroke-width:1.6;stroke-dasharray:6 5;opacity:0.5'
        return 'stroke:#d6a85a;stroke-width:1.7;stroke-dasharray:6 5;opacity:0.8'  # type look (superseded folds in)
    if t == "route":
        return 'stroke:#cfd6ea;stroke-width:1.7;stroke-dasharray:14 6;opacity:0.6'
    if t == "route_seg":   # a hop of an expanded multi-hop route (through ghost nodes)
        if e.get("inferred"):   # length-unknown → identical to a 'route'/stub: grey long-dash
            return 'stroke:#cfd6ea;stroke-width:1.7;stroke-dasharray:14 6;opacity:0.6'
        rg = e.get("region")    # canon hop count, names unknown → solid region tint
        c = pcolor.get(rg, "#8d96b8") if rg and rg != "unknown" else "#8d96b8"
        return f'stroke:{c};stroke-width:1.5;opacity:0.7'
    return 'stroke:#6f7494;stroke-width:1;opacity:0.5'

edge_svg = []
for e in edges:
    x1, y1 = pos[e["from"]]; x2, y2 = pos[e["to"]]
    lab = ""
    if e.get("type") == "route" or e.get("route_label"):   # stubs + (mid-segment of) inferred chains
        txt = f'{e["hops"]} hops' if e.get("hops") else "route"
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        lab = (f'<text class="elabel" x="{mx:.0f}" y="{my-4:.0f}" text-anchor="middle" '
               f'font-family="IBM Plex Mono, monospace" font-size="10" fill="#9aa6c8" '
               f'opacity="0.8">{txt}</text>')
    elif e.get("status") == "severed":   # physically cut — keep this state visible
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        lab = (f'<text class="elabel" x="{mx:.0f}" y="{my-4:.0f}" text-anchor="middle" '
               f'font-family="IBM Plex Mono, monospace" font-size="9" fill="#b06a6a">severed</text>')
    edge_svg.append(
        f'<line class="edge" data-from="{e["from"]}" data-to="{e["to"]}" '
        f'x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" style="{edge_style(e)}"/>' + lab)

# ── nodes ────────────────────────────────────────────────────────────────
R = {"eleven-beacon": 13, "hydra": 9, "scylla": 9, "cerberus": 8, "janus": 7,
     "terminus": 6, "station": 6, "off-grid": 7, "waypoint": 4}
WAYPOINT_COLOR = "#6dd6c1"   # brown-dwarf knnu waypoints — a distinct teal node type
GREEK = {"terminus": "terminus", "janus": "janus", "cerberus": "cerberus",
         "scylla": "scylla", "hydra": "hydra", "eleven-beacon": "11-beacon"}

def sublabel(s):
    parts = []
    t = s.get("beacons_total")
    cls = s.get("class", "")
    if t is not None:
        parts.append(f"{t}β")
    if cls and cls not in ("unknown",):
        parts.append(GREEK.get(cls, cls))
    base = " · ".join(parts)
    d = s.get("beacons_dead")
    if d:
        base += f" · {s.get('beacons_functional','?')}+{d}†"
    return base

node_svg = []
for s in systems:
    px, py = pos[s["id"]]
    pol = s.get("polity", "unknown"); col = pcolor.get(pol, "#BDC3C7")
    cls = s.get("class", "unknown")
    if cls == "placeholder":   # unnamed intermediate on an expanded route
        if not s.get("inferred"):   # canon hop count, just unnamed → solid hollow ring
            gcol = pcolor.get(pol, "#6b7088") if pol != "unknown" else "#6b7088"
            node_svg.append(f'<circle cx="{px:.0f}" cy="{py:.0f}" r="3.5" fill="#0a0c16" '
                            f'stroke="{gcol}" stroke-width="1.1"/>')
        # inferred ghosts are layout-only anchors — not drawn; the grey long-dash conveys the route
        continue
    if cls == "waypoint":
        col = WAYPOINT_COLOR
    note = (s.get("note") or "").lower()
    is_cap = "capital" in note
    is_hub = cls in ("hydra", "eleven-beacon") or is_cap
    r = max(R.get(cls, 6), 12 if is_cap else 0)
    flt = "softglow" if is_hub else "glow"
    g = [f'<g class="node" data-id="{s["id"]}" transform="translate({px:.0f},{py:.0f})" '
         f'data-polity="{x(pname.get(pol,pol))}" data-class="{x(GREEK.get(cls,cls))}" '
         f'data-note="{x(s.get("note") or "")}">']
    if cls == "off-grid":
        g.append(f'<circle r="{r}" fill="none" stroke="{col}" stroke-width="1.3" stroke-dasharray="3 3" opacity="0.85"/>')
        g.append(f'<text y="3" font-size="11" fill="{col}" font-weight="600" text-anchor="middle">?</text>')
    else:
        g.append(f'<circle r="{r}" fill="{col}" filter="url(#{flt})"/>')
    if is_hub:
        g.append(f'<circle r="{r+5}" fill="none" stroke="{col}" stroke-width="0.8" opacity="0.5"/>')
        g.append(f'<circle r="{r+10}" fill="none" stroke="{col}" stroke-width="0.4" opacity="0.3"/>')
    glyph = "★" if is_cap else ("⚑" if pol == "contested" and is_hub else "")
    if glyph:
        g.append(f'<text y="4" font-size="11" fill="#0a0c16" font-weight="600" text-anchor="middle">{glyph}</text>')
    nm = s["name"].upper() if is_cap else s["name"]
    fs = 19 if is_cap else (16 if r >= 8 else 13)
    g.append(f'<text class="nlabel" y="{-(r+10):.0f}" font-size="{fs}" fill="#e8e5d6" '
             f'font-family="EB Garamond, serif" text-anchor="middle" '
             f'letter-spacing="{0.06 if is_cap else 0}em">{x(nm)}</text>')
    sub = sublabel(s)
    if sub:
        g.append(f'<text class="nlabel" y="{r+18:.0f}" font-size="9.5" '
                 f'fill="{col}" opacity="0.92" font-family="IBM Plex Mono, monospace" '
                 f'letter-spacing="0.1em" text-anchor="middle">{x(sub)}</text>')
    g.append('</g>')
    node_svg.append("".join(g))

# ── "unmapped beacon" stubs ─────────────────────────────────────────────────
# A system's known functional-beacon count says how many active beacons it has; those whose
# destination the books don't give are drawn as short faint stubs, each fanned into the
# midpoint of the widest angular GAP between the node's real links (and the stubs already
# placed) — so they fill empty space evenly instead of crowding the real links to one side.
known_beacons = {}
for _e in topo["edges"]:
    if _e["type"] in ("beacon", "route"):      # beacon-network links to a named destination
        known_beacons[_e["from"]] = known_beacons.get(_e["from"], 0) + 1
        known_beacons[_e["to"]] = known_beacons.get(_e["to"], 0) + 1
stub_svg = []
for s in systems:
    if s.get("class") == "placeholder":
        continue
    F = s.get("beacons_functional") or s.get("beacons_total")
    if not F:
        continue
    n = s["id"]; unknown = F - known_beacons.get(n, 0)
    if unknown <= 0:
        continue
    ox, oy = pos[n]
    occ = sorted(math.atan2(pos[b][1] - oy, pos[b][0] - ox) if a == n
                 else math.atan2(pos[a][1] - oy, pos[a][0] - ox)
                 for (a, b) in EDGES if n in (a, b))
    for _ in range(unknown):
        if occ:
            bg, ang = -1.0, 0.0
            for i in range(len(occ)):
                a1 = occ[i]
                a2 = occ[(i + 1) % len(occ)] + (2 * math.pi if i + 1 == len(occ) else 0)
                if a2 - a1 > bg:
                    bg, ang = a2 - a1, (a1 + a2) / 2
        else:
            ang = len(occ) * (2 * math.pi / unknown)
        occ.append(((ang + math.pi) % (2 * math.pi)) - math.pi); occ.sort()
        x1, y1 = ox + math.cos(ang) * 9, oy + math.sin(ang) * 9
        x2, y2 = ox + math.cos(ang) * 62, oy + math.sin(ang) * 62
        stub_svg.append(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="#8d96b8" '
            f'stroke-width="1" stroke-dasharray="2 4" opacity="0.4"/>'
            f'<circle cx="{x2:.0f}" cy="{y2:.0f}" r="2.2" fill="#0a0c16" stroke="#8d96b8" '
            f'stroke-width="0.9" opacity="0.45"/>')

# ── assemble SVG ───────────────────────────────────────────────────────────
DEFS = '''<defs>
  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="softglow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <pattern id="stars" x="0" y="0" width="130" height="130" patternUnits="userSpaceOnUse">
    <circle cx="14" cy="22" r="0.6" fill="#a0a8c8" opacity="0.45"/><circle cx="58" cy="86" r="0.4" fill="#a0a8c8" opacity="0.3"/>
    <circle cx="102" cy="14" r="0.5" fill="#a0a8c8" opacity="0.4"/><circle cx="110" cy="108" r="0.4" fill="#a0a8c8" opacity="0.3"/>
    <circle cx="40" cy="56" r="0.3" fill="#a0a8c8" opacity="0.25"/><circle cx="84" cy="46" r="0.7" fill="#cfd6ea" opacity="0.5"/>
  </pattern>
</defs>'''

svg_inner = (f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#stars)" opacity="0.7"/>'
             + "\n".join(zones)
             + '\n<g id="stubs">' + "\n".join(stub_svg) + '</g>'
             + '\n<g id="edges">' + "\n".join(edge_svg) + '</g>'
             + '\n<g id="nodes">' + "\n".join(node_svg) + '</g>')

svg_static = (f'<svg class="map" viewBox="{VBX} {VBY} {VBW} {VBH}" xmlns="http://www.w3.org/2000/svg" '
              f'style="background:#07091d">{DEFS}{svg_inner}</svg>')
(DATA / "star-map.svg").write_text(svg_static)

# ── interactive HTML ──────────────────────────────────────────────────────
CSS = """
*,*::before,*::after{box-sizing:border-box}
html,body{margin:0;background:#060818;color:#e8e5d6;font-family:'EB Garamond',serif}
body{padding:30px clamp(18px,4vw,52px) 60px;background:
  radial-gradient(ellipse 80% 60% at 30% 0%,#0e1340 0,transparent 60%),
  radial-gradient(ellipse 60% 50% at 85% 100%,#1a0a26 0,transparent 70%),#060818}
.wrap{max-width:1680px;margin:0 auto}
.eyebrow{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#8a8a9a;letter-spacing:.24em;text-transform:uppercase}
h1{font-family:'Cinzel',serif;font-weight:600;letter-spacing:.14em;font-size:clamp(26px,3.4vw,38px);margin:6px 0 4px}
h1 .amp{color:#4f526a;font-weight:400;margin:0 .3em}
.subhead{font-style:italic;color:#b9b6a6;font-size:17px;margin:0 0 12px}
.lede{max-width:1040px;font-size:16px;line-height:1.55}
.lede em{color:#8a8a9a;font-style:italic}
.meta{font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:#4f526a;letter-spacing:.16em;text-transform:uppercase;margin-top:12px;display:flex;flex-wrap:wrap;gap:18px}
.map-frame{border:1px solid #1a1f3a;border-radius:2px;margin-top:20px;overflow:hidden;position:relative;background:
  radial-gradient(ellipse 60% 50% at 50% 18%,rgba(60,70,130,.18),transparent 70%),#07091d;cursor:grab}
.map-frame.grabbing{cursor:grabbing}
svg.map{display:block;width:100%;height:auto;touch-action:none}
.hint{position:absolute;top:10px;right:14px;font-family:'IBM Plex Mono',monospace;font-size:10px;color:#5e6280;letter-spacing:.12em}
.node{cursor:pointer}
.dim{opacity:.12;transition:opacity .15s}
.edge.dim{opacity:.05}
#tip{position:fixed;pointer-events:none;z-index:9;background:#0c1130;border:1px solid #2a2f4a;border-radius:3px;
  padding:8px 11px;font-family:'IBM Plex Mono',monospace;font-size:11px;color:#cfd6ea;max-width:280px;display:none;line-height:1.5;box-shadow:0 4px 18px rgba(0,0,0,.5)}
#tip b{font-family:'EB Garamond',serif;font-size:14px;color:#e8e5d6}
#tip .p{color:#8a8a9a}
.legend{margin-top:24px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px;font-family:'IBM Plex Mono',monospace;font-size:11px;color:#b9b6a6;line-height:1.7}
.legend h3{font-family:'Cinzel',serif;font-weight:600;font-size:11px;letter-spacing:.22em;color:#e8e5d6;margin:0 0 10px;border-bottom:1px solid #1a1f3a;padding-bottom:6px}
.legend ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:7px}
.legend li{display:flex;align-items:center;gap:10px}
.legend .note{color:#4f526a;font-size:10px}
.sw{width:11px;height:11px;border-radius:999px;flex-shrink:0;box-shadow:0 0 8px currentColor}
.legend p{color:#8a8a9a;font-size:11px;line-height:1.5;margin:8px 0 0}
footer{margin-top:32px;border-top:1px solid #1a1f3a;padding-top:16px;font-family:'IBM Plex Mono',monospace;font-size:10.5px;line-height:1.7;color:#4f526a;letter-spacing:.05em}
footer .ct{color:#b9b6a6;letter-spacing:.18em;text-transform:uppercase;margin-bottom:6px}
@media(max-width:900px){.legend{grid-template-columns:repeat(2,1fr)}}
"""

JS = """
const frame=document.querySelector('.map-frame'), svg=document.querySelector('svg.map');
const VB={x:%d,y:%d,w:%d,h:%d}; const MAX_W=%d;
function apply(){svg.setAttribute('viewBox',`${VB.x} ${VB.y} ${VB.w} ${VB.h}`);}
function zoomAt(cx,cy,f){
 const r=svg.getBoundingClientRect();
 const mx=VB.x+(cx-r.left)/r.width*VB.w, my=VB.y+(cy-r.top)/r.height*VB.h;
 const nw=Math.min(Math.max(VB.w*f,260),MAX_W); const s=nw/VB.w;
 VB.w=nw; VB.h*=s; VB.x=mx-(mx-VB.x)*s; VB.y=my-(my-VB.y)*s; apply();
}
// wheel zoom (mouse / trackpad)
frame.addEventListener('wheel',e=>{e.preventDefault(); zoomAt(e.clientX,e.clientY, e.deltaY<0?0.88:1.14);},{passive:false});

// node helpers (used by drag + the highlight tooltip)
function nodeXY(g){const t=g.getAttribute('transform');const m=/translate\\(([-\\d.]+),([-\\d.]+)\\)/.exec(t);return[+m[1],+m[2]];}
function moveNode(g,x,y){g.setAttribute('transform',`translate(${x},${y})`);const id=g.dataset.id;
 document.querySelectorAll('.edge').forEach(L=>{if(L.dataset.from===id){L.setAttribute('x1',x);L.setAttribute('y1',y);}
  if(L.dataset.to===id){L.setAttribute('x2',x);L.setAttribute('y2',y);}});}

// Unified pan / pinch-zoom / node-drag via Pointer Events (mouse + touch + pen).
// Single pointer on background = pan; single pointer on .node = drag; two pointers = pinch-zoom.
const ptrs=new Map();
let pan=null, drag=null, pinchD=null;
frame.addEventListener('pointerdown',e=>{
 ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY});
 try{frame.setPointerCapture(e.pointerId);}catch(_){}
 if(ptrs.size===1){
  const node=e.target.closest('.node');
  if(node){const[x,y]=nodeXY(node); const r=svg.getBoundingClientRect();
   drag={id:e.pointerId,g:node,ox:e.clientX,oy:e.clientY,sx:x,sy:y,sc:VB.w/r.width};}
  else{pan={id:e.pointerId,x:e.clientX,y:e.clientY}; frame.classList.add('grabbing');}
 }else if(ptrs.size===2){
  pan=null; drag=null;
  const [a,b]=[...ptrs.values()]; pinchD=Math.hypot(a.x-b.x,a.y-b.y);
 }
});
frame.addEventListener('pointermove',e=>{
 if(!ptrs.has(e.pointerId))return;
 ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY});
 if(ptrs.size===2){
  const [a,b]=[...ptrs.values()]; const d=Math.hypot(a.x-b.x,a.y-b.y);
  if(pinchD && d>0){zoomAt((a.x+b.x)/2,(a.y+b.y)/2, pinchD/d);}
  pinchD=d; return;
 }
 if(drag && drag.id===e.pointerId){
  moveNode(drag.g, drag.sx+(e.clientX-drag.ox)*drag.sc, drag.sy+(e.clientY-drag.oy)*drag.sc);
 }else if(pan && pan.id===e.pointerId){
  const r=svg.getBoundingClientRect();
  VB.x-=(e.clientX-pan.x)/r.width*VB.w; VB.y-=(e.clientY-pan.y)/r.height*VB.h;
  pan={id:pan.id,x:e.clientX,y:e.clientY}; apply();
 }
});
function endPointer(e){
 ptrs.delete(e.pointerId);
 if(ptrs.size<2)pinchD=null;
 if(drag && drag.id===e.pointerId)drag=null;
 if(pan && pan.id===e.pointerId){pan=null; frame.classList.remove('grabbing');}
}
frame.addEventListener('pointerup',endPointer);
frame.addEventListener('pointercancel',endPointer);

// Hover / tooltip (mouse only — touch has no hover; tap-to-tooltip would conflict with drag).
const tip=document.getElementById('tip');
document.querySelectorAll('.node').forEach(g=>{
 g.addEventListener('mouseenter',()=>highlight(g));
 g.addEventListener('mouseleave',()=>{clearHi();tip.style.display='none';});
 g.addEventListener('mousemove',e=>{tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+14)+'px';
  tip.innerHTML=`<b>${g.querySelector('.nlabel').textContent}</b><br><span class="p">${g.dataset.polity} · ${g.dataset.class}</span>`+(g.dataset.note?`<br>${g.dataset.note}`:'');});
});
function highlight(g){const id=g.dataset.id;const nbr=new Set([id]);
 document.querySelectorAll('.edge').forEach(L=>{if(L.dataset.from===id)nbr.add(L.dataset.to);if(L.dataset.to===id)nbr.add(L.dataset.from);});
 document.querySelectorAll('.node').forEach(n=>n.classList.toggle('dim',!nbr.has(n.dataset.id)));
 document.querySelectorAll('.edge').forEach(L=>L.classList.toggle('dim',!(L.dataset.from===id||L.dataset.to===id)));}
function clearHi(){document.querySelectorAll('.dim').forEach(n=>n.classList.remove('dim'));}
"""  % (VBX, VBY, VBW, VBH, int(VBW * 1.6))

HEADER = '''<header>
<div class="eyebrow">Field Reference Chart · Sun Chronicles · K. Elliott · verified compendium</div>
<h1>THE LOCAL BELT <span class="amp">of</span> STARS</h1>
<div class="subhead">A topological survey of the post-collapse beacon network, knnu corridors, and political regions in <em>Unconquerable Sun</em> &amp; <em>Furious Heaven</em>.</div>
<p class="lede">Positions are <em>force-laid</em>, not physical — the novels give no coordinates, only the relational topology of beacon pairings and the knnu gaps that bridge them. Lines are <strong>paired connections</strong>, not distances. Generated from the verified <code>topology.json</code>; re-laid automatically as the compendium grows.</p>
<div class="meta"><span>Force-directed layout</span><span>Drag nodes · scroll or pinch to zoom · drag/swipe to pan · hover for detail</span><span>Dead beacons noted in node labels (†)</span></div>
</header>'''

# Region swatches are GENERATED from pcolor (the same palette the nodes + hulls use), so
# the legend can never drift from what's drawn. Order/labels fixed for presentation.
LEGEND_REGIONS = [("chaonia", "Chaonian Republic"), ("hatti", "Hatti region (Chaonia-held)"),
                  ("phene", "Phene Empire"), ("yele_league", "Yele League"),
                  ("mishirru", "Mishirru Province"), ("trinity", "Trinity Coalition"),
                  ("contested", "Contested / frontier")]
region_li = "".join(
    f'<li><span class="sw" style="color:{pcolor[i]};background:{pcolor[i]}"></span>{lbl}</li>'
    for i, lbl in LEGEND_REGIONS)
# "severed" = a physically cut link; show the key only if one actually exists (none today —
# Eel Gulf was a loss of chokepoint access, not a cut link).
has_severed = any(e.get("status") == "severed" for e in edges)
severed_li = ('<li><svg width="34" height="6"><line x1="0" y1="3" x2="34" y2="3" '
              'stroke="#b06a6a" stroke-width="1.6" stroke-dasharray="6 5"/></svg>'
              'Severed (physically cut) link</li>') if has_severed else ''
severed_clause = " and physical state (red = severed/cut)" if has_severed else ""
LEGEND = f'''<section class="legend">
<div><h3>Connections</h3><ul>
<li><svg width="34" height="6"><line x1="0" y1="3" x2="34" y2="3" stroke="#cfd6ea" stroke-width="2"/></svg>Confirmed beacon</li>
<li><svg width="34" height="6"><line x1="0" y1="3" x2="34" y2="3" stroke="#6f7494" stroke-width="1.4" stroke-dasharray="3 5"/></svg>Inferred beacon</li>
<li><svg width="34" height="6"><line x1="0" y1="3" x2="34" y2="3" stroke="#d6a85a" stroke-width="1.8" stroke-dasharray="6 5"/></svg>Knnu (non-beacon link)</li>
<li><svg width="34" height="10"><line x1="0" y1="5" x2="13" y2="5" stroke="#8d96b8" stroke-width="1.5"/><circle cx="17" cy="5" r="3" fill="#0a0c16" stroke="#6b7088"/><line x1="21" y1="5" x2="34" y2="5" stroke="#8d96b8" stroke-width="1.5"/></svg>Multi-hop route <span class="note">○ = unnamed intermediate (dashed = inferred)</span></li>
<li><svg width="34" height="6"><line x1="0" y1="3" x2="34" y2="3" stroke="#cfd6ea" stroke-width="1.7" stroke-dasharray="14 6" opacity="0.6"/></svg>Route, length unknown / inferred</li>
{severed_li}
</ul><p>Line style marks the link <em>type</em> (beacon · knnu · route){severed_clause}; how often a link is travelled is not styled. Faint grey dashes mark inferred or length-unknown routes.</p></div>
<div><h3>Systems</h3><ul>
<li><span class="sw" style="color:#cfd6ea;background:#cfd6ea"></span>Major hub / capital <span class="note">★ + ring · colour = polity</span></li>
<li><span class="sw" style="color:#cfd6ea;background:#cfd6ea;width:7px;height:7px"></span>Standard system <span class="note">colour = polity</span></li>
<li><span class="sw" style="color:#82dca0;background:transparent;border:1.4px dashed #82dca0;box-shadow:none"></span>Off-grid (the Gyre)</li>
<li><span class="sw" style="color:#6dd6c1;background:#6dd6c1;width:7px;height:7px"></span>Brown-dwarf knnu waypoint</li>
</ul><p><strong style="color:#e8e5d6">Beacon-count nicknames</strong> follow the prime rule: 1 terminus · 2 janus · 3 cerberus · 5 scylla · 7 hydra · 11 (unnamed). Label format: <em>11β · 8+3†</em> = 11 total, 8 functional, 3 dead.</p></div>
<div><h3>Political Regions</h3><ul>
{region_li}
</ul></div>
<div><h3>Reading the Chart</h3>
<p><strong style="color:#e8e5d6">Topology, not geography.</strong> Position implies relational role (hub, periphery, frontier), not distance.</p>
<p><strong style="color:#e8e5d6">TEC</strong> — Tinker-Evers-Chance Convergence, a rare three-way mutual beacon link. <strong>Two confirmed</strong> (Chaonian core and Trinity Coalition); the books call TECs &ldquo;rare&rdquo;, not &ldquo;only two&rdquo;.</p>
<p><strong style="color:#e8e5d6">Karnos</strong> is the load-bearing junction — the one hub wiring Chaonia, Phene, the Trinity back door, and the outer rim together.</p></div>
</section>'''

FOOTER = '''<footer><div class="ct">Provenance &amp; caveats</div>
<div>· Every node and edge traces to the verified, source-cited compendium; the map is generated from <code>data/topology.json</code>, which <code>build-topology.py</code> derives automatically from the compendium's topology blocks.</div>
<div>· Many <strong>route</strong> edges have unnamed intermediates (Yele→Chaonia 3 hops, Harahuvati→Destiny 3 drops); these are drawn as small hollow placeholder nodes strung along the route, not asserted as named systems.</div>
<div>· The unnamed 8th Mishirru core system, Karnos's dead 7th-beacon pair, and the destinations of most Yele/Anchor beacons remain open questions — absent here by design.</div>
<div>· The Gyre lies off the beacon grid (shown as an off-grid node); the Apsaras homeworld ("She Who Bore Them All"), the collapsed hub, is lost and not graphed at all.</div>
<div style="margin-top:8px;color:#3a3c52">Sourced only from <em>Unconquerable Sun</em> (2020) and <em>Furious Heaven</em> (2023). <em>Lady Chaos</em> (forthcoming) may revise sections.</div></footer>'''

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" '
         'href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/'
         'css2?family=Cinzel:wght@400;600&family=EB+Garamond:ital@0;1&family=IBM+Plex+Mono:wght@300;400&display=swap" rel="stylesheet">')

html = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Sun Chronicles — The Local Belt of Stars</title>{FONTS}'
        f'<style>{CSS}</style></head><body><div class="wrap">{HEADER}'
        f'<div class="map-frame"><div class="hint">drag · zoom · pan</div>{svg_static}</div>'
        f'{LEGEND}{FOOTER}</div><div id="tip"></div><script>{JS}</script></body></html>')
(DATA / "star-map.html").write_text(html)

print(f"wrote data/star-map.svg and data/star-map.html  (nodes={len(systems)} edges={len(edges)})")
