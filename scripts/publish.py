#!/usr/bin/env python3
"""Derive the PUBLIC compendium from the private source — the copyright firewall in code.

One command, run from the private repo. It:
  1. Refreshes derived data (build-topology.py, build-web-map.py, and the share
     images via make-images.py when rsvg-convert is available).
  2. Trims each reader-facing domain file → ../compendium-public/docs/:
       • DROPS every `>` blockquote        (the verbatim firewall)
       • STRIPS every ```topology block     (data ships as JSON instead)
       • DROPS chapter titles from citations (`— FH ch. 27 "Title"` → `— FH ch. 27`)
       • KEEPS headings, **Tier:** lines, analysis prose, cross-links, and the
         short inline fair-use quotes embedded in the analysis.
       • APPENDS the unofficial-fan-project disclaimer footer.
  3. Copies data/topology.json → public data/, and star-map.html → public docs/map.html.
  4. Mirrors the tooling (scripts/ + LICENSE + a generated README) → public scripts/.
     Code-only, no prose, MIT-licensed; read-only mirror so others can fork/reuse it.
  5. Generates docs/index.md (landing page).
  6. FIREWALL SELF-CHECK (hard fail): asserts no `>` blockquote and no ```topology
     fence survives anywhere in docs/*.md. Aborts loudly if either does.

It NEVER commits or pushes. Review the public diff, then commit/push yourself.

Usage: scripts/publish.py
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

PRIV = Path(__file__).resolve().parent.parent
PUB = PRIV.parent / "compendium-public"
SRC = PRIV / "compendium"
DATA = PRIV / "data"
PUBDOCS = PUB / "docs"
PUBDATA = PUBDOCS / "data"   # under docs_dir so MkDocs serves it (downloadable on the site)

# Reader-facing files, in nav/reading order. Internal docs are NOT published:
# CONVENTIONS.md (private format spec), README.md (private index), PROGRESS.md (metrics).
DOMAINS = [
    ("travel-tech.md", "Travel & beacon tech"),
    ("systems.md", "Systems"),
    ("polities.md", "Polities"),
    ("characters.md", "Characters"),
    ("history.md", "History"),
    ("open-questions.md", "Open questions"),
]

DISCLAIMER = (
    "*This is an unofficial fan project. It is **not approved, endorsed by, or "
    "affiliated with** Kate Elliott or her publishers. All facts are drawn from and "
    "cited to the published novels; no substantial text is reproduced. Copyright in "
    "the* Sun Chronicles *belongs to Kate Elliott.*"
)

# Scripts mirrored read-only into the public repo so others can read/fork them.
# Explicit list (not a glob) so private-workflow utilities like stats.sh / log-progress.sh
# stay private. Files travel with scripts/LICENSE (MIT) + a generated README.
MIRRORED_SCRIPTS = (
    "build-topology.py",   # parses ```topology blocks → topology.json
    "build-web-map.py",    # force-directed layout + SVG/HTML map
    "make-images.py",      # composes shareable PNGs
    "publish.py",          # this script — the copyright-firewall publish step
)

SCRIPTS_README = """# Tooling (mirrored — read-only)

These scripts are **mirrored from the private source repo** by its publish step and
are overwritten on each publish. The canonical copies live there; edits made here will
not survive a re-publish. They're mirrored so others can read and reuse them.

- `build-topology.py` — parses the structured topology blocks → `topology.json`.
- `build-web-map.py`  — force-directed layout + crossing reduction → the SVG / HTML map.
- `make-images.py`    — composes the shareable PNGs.
- `publish.py`        — the copyright-firewall publish step that derives this repo.

**Running them here:** the renderers expect a `topology.json` (in this repo it lives at
`docs/data/topology.json`, not `data/topology.json` as in the private layout), so paths
need adjustment to run standalone here. `publish.py` and `build-topology.py` need the
private compendium source and the source epubs, and so will not run against this repo
as-is — they're mirrored as reference.

Licensed under **MIT** — see `LICENSE`. The compendium *content* (everything under
`../docs/`) is an unofficial fan project derived from Kate Elliott's *Sun Chronicles*
and is **not** openly licensed; see the site disclaimer.
"""

CITATION = re.compile(r"^\*\s*—\s*(.*?)\s*\*\s*$")        # *— US ch. 42 "Title"*
TOPO_OPEN = re.compile(r"^\s*```topology\s*$")
FENCE = re.compile(r"^\s*```\s*$")


def strip_citation_title(inner: str) -> str:
    """`US ch. 42 "The Heat…" (search: "x")` -> `US ch. 42` (keep book + chapter only)."""
    inner = re.sub(r'\s*".*$', "", inner)          # drop the quoted chapter title
    inner = re.sub(r"\s*\(search:.*$", "", inner)  # drop any re-find hint
    return inner.strip()


def transform(text: str) -> str:
    """Apply the firewall transform to one domain file's markdown."""
    lines = text.splitlines()
    out, i = [], 0

    # Keep the H1 title; drop the private intro boilerplate (it references CONVENTIONS.md
    # and 'verbatim only in blockquotes', neither of which exists/applies in public).
    if lines and lines[0].startswith("# "):
        out.append(lines[0])
        out.append("")
        i = 1
        while i < len(lines) and not lines[i].lstrip().startswith("##"):
            i += 1

    while i < len(lines):
        ln = lines[i]
        if TOPO_OPEN.match(ln):                    # drop ```topology … ``` whole
            i += 1
            while i < len(lines) and not FENCE.match(lines[i]):
                i += 1
            i += 1                                  # skip the closing fence
            continue
        if ln.lstrip().startswith(">"):             # drop blockquote lines (incl. empty >)
            i += 1
            continue
        m = CITATION.match(ln)
        if m and " ch. " in m.group(1):             # citation line → strip chapter title
            out.append(f"*— {strip_citation_title(m.group(1))}*")
            i += 1
            continue
        out.append(ln)
        i += 1

    body = "\n".join(out)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()   # collapse gaps left by drops
    return f"{body}\n\n---\n\n{DISCLAIMER}\n"


def firewall_check(docs: Path) -> list[str]:
    """Hard guarantee: no surviving blockquote or topology fence in any published page."""
    violations = []
    for f in sorted(docs.glob("*.md")):
        for n, ln in enumerate(f.read_text().splitlines(), 1):
            if ln.lstrip().startswith(">"):
                violations.append(f"{f.name}:{n}  surviving blockquote: {ln.strip()[:60]}")
            if TOPO_OPEN.match(ln):
                violations.append(f"{f.name}:{n}  surviving ```topology fence")
    return violations


def counts() -> dict:
    """Pull live fact counts from stats.sh --progress (date entries canon inf open resolved)."""
    out = subprocess.run(
        ["bash", str(PRIV / "scripts" / "stats.sh"), "--progress"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    keys = ["date", "entries", "canon", "inf", "open", "resolved"]
    return dict(zip(keys, out))


def make_index(c: dict, n_systems: int) -> str:
    return f"""# The Sun Chronicles — Compendium & Topology Map

A fan-made, **verified** reference for the worldbuilding of Kate Elliott's *Sun
Chronicles* — *Unconquerable Sun*, *Furious Heaven*, and the forthcoming *Lady Chaos*:
the interstellar beacon-network topology, stellar geography, political entities, travel
technology, and key strategic situations.

Every fact is drawn from the published novels and **cited** (book + chapter), and tiered
**canon** (stated in the text), **inference** (reasoned, labelled), or **open** (the
books are silent). Currently **{c['entries']} entries** ({c['canon']} canon) across
**{n_systems} catalogued systems**.

## Start here

- **[Interactive topology map](map.md)** — the beacon network as a force-directed graph.
- **[Systems](systems.md)** — beacon counts, classes, links, control.
- **[Polities](polities.md)** · **[Characters](characters.md)** ·
  **[Travel & beacon tech](travel-tech.md)** · **[History](history.md)**
- **[Open questions](open-questions.md)** — what the books leave unresolved.
- **[Topology data (JSON)](data/topology.json)** — the raw beacon-network graph.

---

{DISCLAIMER}
"""


def main() -> int:
    print("=== refreshing derived data ===")
    for script in ("build-topology.py", "build-web-map.py"):
        subprocess.run([sys.executable, str(PRIV / "scripts" / script)], check=True)
    # share images (docs/img/) — refresh so they never go stale. Needs rsvg-convert;
    # skip gracefully if it's absent rather than aborting the publish.
    if shutil.which("rsvg-convert"):
        subprocess.run([sys.executable, str(PRIV / "scripts" / "make-images.py")], check=True)
    else:
        print("  WARN rsvg-convert not found — skipped make-images.py (docs/img/ left as-is)")

    PUBDOCS.mkdir(parents=True, exist_ok=True)
    PUBDATA.mkdir(parents=True, exist_ok=True)
    for stale in PUBDOCS.glob("*.md"):              # clear generated pages so deletions propagate
        stale.unlink()

    print("\n=== trimming domain files ===")
    for fname, _ in DOMAINS:
        src = SRC / fname
        if not src.exists():
            print(f"  WARN missing {fname}, skipped")
            continue
        (PUBDOCS / fname).write_text(transform(src.read_text()))
        print(f"  {fname}")

    # data + map artifacts: the self-contained map ships as map.html; map.md wraps it
    # in an iframe so it lives inside the themed site nav.
    shutil.copy2(DATA / "topology.json", PUBDATA / "topology.json")
    shutil.copy2(DATA / "star-map.html", PUBDOCS / "map.html")
    (PUBDOCS / "map.md").write_text(
        "# Topology map\n\n"
        "The beacon network as a force-directed graph — links typed beacon / knnu / "
        "route, nodes coloured by polity. Unnamed intermediate hops appear as small "
        "hollow placeholder nodes.\n\n"
        # The iframe is raw HTML — MkDocs does NOT rewrite its src, so it needs the
        # runtime-correct path: directory-URLs serve this page at /map/, so ../map.html
        # reaches the root-level self-contained map. The markdown link below uses the
        # source-relative 'map.html' (same dir as map.md); MkDocs rewrites + validates it.
        '<iframe src="../map.html" style="width:100%;height:82vh;border:0;" '
        'title="Sun Chronicles topology map"></iframe>\n\n'
        '[Open the map full-screen](map.html){target="_blank" rel="noopener"}\n\n'
        f"---\n\n{DISCLAIMER}\n"
    )
    import json
    n_systems = len(json.loads((DATA / "topology.json").read_text())["systems"])
    (PUBDOCS / "index.md").write_text(make_index(counts(), n_systems))
    print("  index.md, map.md, map.html, data/topology.json")

    # --- mirror the tooling (code only — contains no prose, so no firewall concern) ---
    # Read-only mirror so others can read/fork it; clobbered each publish so the private
    # copy stays the single source of truth. NOT under docs/ — MkDocs ignores it; it's
    # there for repo browsers, not as served site pages.
    print("\n=== mirroring tooling (scripts/) ===")
    PUBSCRIPTS = PUB / "scripts"
    if PUBSCRIPTS.exists():
        shutil.rmtree(PUBSCRIPTS)
    PUBSCRIPTS.mkdir(parents=True)
    for name in MIRRORED_SCRIPTS:
        shutil.copy2(PRIV / "scripts" / name, PUBSCRIPTS / name)
    shutil.copy2(PRIV / "scripts" / "LICENSE", PUBSCRIPTS / "LICENSE")
    (PUBSCRIPTS / "README.md").write_text(SCRIPTS_README)
    print(f"  {len(MIRRORED_SCRIPTS)} scripts + LICENSE + README.md")

    print("\n=== firewall self-check ===")
    violations = firewall_check(PUBDOCS)
    if violations:
        print("  FAIL — verbatim/topology leaked into public docs:")
        for v in violations:
            print("   ", v)
        return 1
    print(f"  PASS — no blockquotes, no topology blocks in {len(list(PUBDOCS.glob('*.md')))} pages")
    print("\nDone. Review the public diff, then commit/push from compendium-public.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
