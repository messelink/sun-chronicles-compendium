# Tooling (mirrored — read-only)

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
