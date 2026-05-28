#!/usr/bin/env python3
"""Generate topology JSON from the normalized ```topology blocks in compendium/*.md.

The compendium markdown is the single source of truth. Each block is YAML and is one
of three kinds:
  • system block      — has `system:` (id). Carries node attrs + a `links:` list.
  • convergence block — has `convergence:`. Lists `members:` (ids).
  • route block       — has `route:` + `ordered:` (ids). Emits edges between consecutive
                        members of `link_type` (default beacon).
A block may also be a YAML *list* of such mappings (several systems in one block).

Unrecognized keys are PASSED THROUGH onto the node/edge unchanged — normalization never
silently drops data. Writes data/topology.json (the canonical derived graph; the map
generators read it).

Usage: scripts/build-topology.py
"""
import yaml, re, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMP, DATA = ROOT / "compendium", ROOT / "data"

# Polity palette — the single source of truth for region colour. The web-map reads these
# (pcolor) for node fills + region hulls AND generates its legend from them, so the legend
# can never drift from what's drawn. Tuned for legibility on the dark star-chart ground.
POLITIES = [
    {"id": "chaonia", "name": "Republic of Chaonia", "color": "#6cd6ff"},
    {"id": "hatti", "name": "Hatti region (Chaonia-held)", "color": "#d9854f"},
    {"id": "phene", "name": "Phene Empire", "color": "#ff7080"},
    {"id": "yele_league", "name": "Yele League", "color": "#ffc35a"},
    {"id": "trinity", "name": "Trinity Coalition", "color": "#c089ff"},
    {"id": "mishirru", "name": "Mishirru Province (Phene-administered)", "color": "#82dca0"},
    {"id": "contested", "name": "Contested / frontier", "color": "#f4f0e2"},
    {"id": "unknown", "name": "Unknown / unaligned", "color": "#BDC3C7"},
]
NODE_KNOWN = {"system", "name", "class", "beacons", "polity", "role", "note", "links"}
EDGE_KNOWN = {"to", "type", "status", "hops", "via", "name", "note"}

systems, edges, convergences, routes, warns = {}, [], [], [], []


def node(nid, **kw):
    n = systems.setdefault(nid, {"id": nid})
    for k, v in kw.items():
        if v is None:
            continue
        if k not in n or n.get(k) in (None, "unknown"):
            n[k] = v
    return n


def add_edge(a, b, etype="beacon", extra=None):
    if not a or not b or a == b:
        return
    e = {"from": a, "to": b, "type": etype}
    if extra:
        e.update({k: v for k, v in extra.items() if v is not None})
    edges.append(e)
    node(a); node(b)


def handle(item, src):
    if not isinstance(item, dict):
        warns.append(f"{src}: non-mapping block item skipped")
        return
    if "system" in item:
        nid = item["system"]
        b = item.get("beacons") or {}
        n = node(nid, name=item.get("name"), **{"class": item.get("class")},
                 polity=item.get("polity"), role=item.get("role"), note=item.get("note"))
        if isinstance(b, dict):
            for key in ("total", "functional", "dead"):
                if b.get(key) is not None:
                    n[f"beacons_{key}"] = b[key]
        for k, v in item.items():            # pass through anything unrecognized
            if k not in NODE_KNOWN:
                n[k] = v
        for link in item.get("links") or []:
            if not isinstance(link, dict):
                continue
            if link.get("to"):
                add_edge(nid, link["to"], link.get("type", "beacon"),
                         {k: v for k, v in link.items() if k not in ("to", "type")})
            # links without `to` (dead/unpaired beacon, anchor-only) are node detail; skip edge
    elif "convergence" in item:
        convergences.append({k: v for k, v in item.items()})
    elif "route" in item:
        seq = item.get("ordered") or []
        lt = item.get("link_type", "beacon")
        extra = {"route": item["route"]}
        for k in ("status", "note"):
            if item.get(k) is not None:
                extra[k] = item[k]
        for a, b in zip(seq, seq[1:]):
            add_edge(a, b, lt, extra)
        routes.append({k: v for k, v in item.items()})
    else:
        warns.append(f"{src}: block has no system/convergence/route key — skipped")


SKIP = {"CONVENTIONS.md", "README.md", "PROGRESS.md"}  # docs, not data
for f in sorted(COMP.glob("*.md")):
    if f.name in SKIP:
        continue
    for m in re.finditer(r"```topology\n(.*?)```", f.read_text(), re.S):
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError as e:
            warns.append(f"{f.name}: YAML error: {str(e).splitlines()[0]}")
            continue
        for it in (data if isinstance(data, list) else [data]):
            handle(it, f.name)

# dedupe undirected edges by (pair, type); merge attrs
merged = {}
for e in edges:
    key = (frozenset((e["from"], e["to"])), e["type"])
    if key in merged:
        for k, v in e.items():
            merged[key].setdefault(k, v)
    else:
        merged[key] = dict(e)
edges_out = list(merged.values())

# stub names for any node lacking one
for nid, n in systems.items():
    n.setdefault("name", nid.replace("_", " ").title())
    n.setdefault("class", "unknown")
    n.setdefault("polity", "unknown")

out = {
    "meta": {"title": "Sun Chronicles beacon-network topology",
             "provenance": "GENERATED from the ```topology blocks in compendium/*.md by "
                           "scripts/build-topology.py. Do not hand-edit. The compendium is "
                           "the source of truth.",
             "counts": {"systems": len(systems), "edges": len(edges_out),
                        "convergences": len(convergences)}},
    "polities": POLITIES,
    "systems": sorted(systems.values(), key=lambda s: s["id"]),
    "edges": edges_out,
    "convergences": convergences,
    "routes": routes,
}
(DATA / "topology.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
print(f"systems={len(systems)} edges={len(edges_out)} convergences={len(convergences)} "
      f"routes={len(routes)} warnings={len(warns)}")
for w in warns:
    print("  WARN", w)
