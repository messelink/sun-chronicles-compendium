# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The **public** half of the *Sun Chronicles* worldbuilding project (parent: `~/projects/sun-chronicles/`). A fan-facing compendium + topology map, intended for GitHub and GitHub Pages.

**This repo is generated, not authored here.** Its content is *derived* from the private repo (`../compendium-private/`) via that repo's publish step. They share no git history.

## Hard rules (copyright firewall)

- **Never commit the books.** No `.epub`, ever (gitignored defensively).
- **No extended verbatim quotation.** Only short fair-use snippets with citations (book + chapter). Facts and worldbuilding analysis are fine; long passages of Kate Elliott's prose are not.
- **Do not paste from the private repo by hand.** Public content must come through the publish step so trimming is consistent and reviewable. If something needs to change here, change it in private and re-publish.

## Layout

- `docs/` — the trimmed, fair-use compendium for GitHub Pages (MkDocs Material source).
  Includes `docs/data/topology.json` (served, downloadable) and the self-contained
  interactive `docs/map.html` (wrapped by `docs/map.md`).
- `mkdocs.yml` — site config (theme, nav). `.github/workflows/deploy.yml` — build + deploy.
- `README.md` — project intro for visitors.

Everything under `docs/` is **generated** by `../compendium-private/scripts/publish.py`;
edit the private source and re-publish, never hand-edit here.
